from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .base import asset_path_for_storage, detect_languages, make_document, normalize_text
from ..schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedSegment, new_image_id

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
REL_EMBED_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
REL_ID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
STEP_RE = re.compile(r"^(?:step\s+)?(?:\d+|[a-zA-Z])[\).:-]\s+")


class DocxParser:
    parser_name = "docx_parser"

    def __init__(self, extracted_images_dir: Path, root_dir: Path | None = None) -> None:
        self.extracted_images_dir = extracted_images_dir
        self.root_dir = root_dir

    def parse(self, path: Path, relative_path: str):
        document = make_document(path, relative_path, "docx", parser_used=self.parser_name)
        segments: list[NormalizedSegment] = []
        blocks: list[BlockRecord] = []
        images: list[ImageContext] = []
        asset_dir = self.extracted_images_dir / document.document_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        heading_stack: list[tuple[int, str]] = []

        with zipfile.ZipFile(path) as archive:
            xml = ET.fromstring(archive.read("word/document.xml"))
            rel_map = _relationship_map(archive)
            order_index = 0
            segment_index = 0
            for paragraph in xml.findall(".//w:body/w:p", WORD_NS):
                texts = [node.text for node in paragraph.findall(".//w:t", WORD_NS) if node.text]
                text = normalize_text("".join(texts))
                style_name = _paragraph_style(paragraph)
                heading_level = _heading_level(style_name)

                if heading_level is not None and text:
                    while heading_stack and heading_stack[-1][0] >= heading_level:
                        heading_stack.pop()
                    heading_stack.append((heading_level, text))
                    section_path = _section_path(document.title, heading_stack)
                    source_label = " > ".join(section_path)
                    blocks.append(
                        BlockRecord(
                            block_id=f"{document.document_id}-block-{order_index}",
                            block_type="heading",
                            text=text,
                            order_index=order_index,
                            title=section_path[-1],
                            section_path=section_path,
                            citation_anchor=CitationAnchor(source_label=source_label),
                            heading_level=heading_level,
                            metadata={"style_name": style_name, "section_depth": len(section_path) - 1},
                        )
                    )
                    order_index += 1
                    continue

                section_path = _section_path(document.title, heading_stack)
                section_label = section_path[-1]
                source_label = " > ".join(section_path)
                image_contexts: list[ImageContext] = []
                for target in _paragraph_image_targets(paragraph, rel_map):
                    blob = archive.read(f"word/{target}")
                    image_name = f"{new_image_id()}-{Path(target).name}"
                    image_path = asset_dir / image_name
                    image_path.write_bytes(blob)
                    rel_path = asset_path_for_storage(image_path, self.root_dir)
                    image_context = ImageContext(
                        image_id=new_image_id(),
                        image_path=rel_path,
                        related_section_path=" > ".join(section_path[1:]) or document.title,
                    )
                    images.append(image_context)
                    image_contexts.append(image_context)

                block_type = _paragraph_block_type(style_name, text, image_contexts)
                if not text and not image_contexts:
                    continue
                blocks.append(
                    BlockRecord(
                        block_id=f"{document.document_id}-block-{order_index}",
                        block_type=block_type,
                        text=text,
                        order_index=order_index,
                        title=section_label,
                        section_path=section_path,
                        citation_anchor=CitationAnchor(source_label=source_label),
                        image_contexts=image_contexts,
                        step_number=_step_number(text) if block_type == "step" else "",
                        metadata={"style_name": style_name, "section_depth": len(section_path) - 1},
                    )
                )
                order_index += 1
                segments.append(
                    NormalizedSegment(
                        segment_id=f"{document.document_id}-seg-{segment_index}",
                        segment_type=_segment_type_for_block(block_type),
                        text=text or section_label,
                        title=section_label,
                        section_path=section_path,
                        citation_anchor=CitationAnchor(source_label=source_label),
                        image_contexts=image_contexts,
                        metadata={"style_name": style_name, "section_depth": len(section_path) - 1},
                    )
                )
                segment_index += 1

        document.images = images
        document.blocks = blocks
        document.segments = segments
        document.metadata = {
            **document.metadata,
            "document_structure": "hierarchical_sections",
            "chunking_hints": _build_chunking_hints(document),
        }
        language_tags = detect_languages(block.text or block.title for block in blocks if block.text or block.title)
        document.language_tags = language_tags
        for block in document.blocks:
            block.language_tags = language_tags
        for segment in document.segments:
            segment.language_tags = language_tags
        return document


def _relationship_map(archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        xml = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}
    result = {}
    for rel in xml.findall(".//rel:Relationship", REL_NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target and target.startswith("media/"):
            result[rel_id] = target
    return result


def _paragraph_image_targets(paragraph: ET.Element, rel_map: dict[str, str]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for node in paragraph.iter():
        rel_id = node.attrib.get(REL_EMBED_ATTR) or node.attrib.get(REL_ID_ATTR)
        if not rel_id:
            continue
        target = rel_map.get(rel_id)
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def _paragraph_style(paragraph: ET.Element) -> str:
    node = paragraph.find(".//w:pStyle", WORD_NS)
    return node.attrib.get(f"{{{WORD_NS['w']}}}val", "") if node is not None else ""


def _heading_level(style_name: str) -> int | None:
    if not style_name.startswith("Heading"):
        return None
    suffix = style_name.removeprefix("Heading")
    return int(suffix) if suffix.isdigit() else 1


def _paragraph_block_type(style_name: str, text: str, image_contexts: list[ImageContext]) -> str:
    if not text and image_contexts:
        return "figure"
    lowered = text.lower()
    if style_name.startswith("Caption") or lowered.startswith("figure"):
        return "caption"
    if STEP_RE.match(text):
        return "step"
    if style_name.startswith("List"):
        return "list_item"
    return "paragraph"


def _segment_type_for_block(block_type: str) -> str:
    mapping = {
        "step": "paragraph",
        "figure": "image_caption",
        "caption": "image_caption",
    }
    return mapping.get(block_type, block_type)


def _step_number(text: str) -> str:
    match = STEP_RE.match(text)
    if not match:
        return ""
    return match.group(0).strip()


def _section_path(document_title: str, heading_stack: list[tuple[int, str]]) -> list[str]:
    return [document_title, *[heading for _, heading in heading_stack]]


def _build_chunking_hints(document) -> dict[str, object]:
    sections: list[dict[str, object]] = []
    seen_paths: set[tuple[str, ...]] = set()
    for block in document.blocks:
        if block.block_type != "heading":
            continue
        path_key = tuple(block.section_path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        sections.append(
            {
                "section_path": block.section_path,
                "heading_level": block.heading_level,
                "block_ids": [candidate.block_id for candidate in document.blocks if candidate.section_path == block.section_path],
            }
        )
    return {
        "structure": "hierarchical_sections",
        "section_count": len(sections),
        "sections": sections,
    }
