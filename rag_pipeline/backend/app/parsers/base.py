from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from ..normalization.arabic_text import contains_arabic, normalize_arabic_text
from ..schemas import (
    BlockRecord,
    CitationAnchor,
    ChunkRecord,
    ImageRecord,
    NormalizedDocument,
    new_chunk_id,
    safe_title_from_path,
)


class UnsupportedDocumentError(ValueError):
    pass


class BaseDocumentParser:
    parser_name = "base"

    def parse(self, path: Path, relative_path: str) -> NormalizedDocument:
        raise NotImplementedError


STEP_RE = re.compile(r"^(?:step\s+)?(?:\d+|[a-zA-Z])[\).:-]\s+")
REGULATORY_KEYWORDS = ("policy", "standard", "governance", "compliance", "control", "shall", "must")
PROCEDURAL_KEYWORDS = ("procedure", "step", "runbook", "rollback", "prerequisite", "verify")
TECHNICAL_KEYWORDS = ("architecture", "design", "component", "interface", "topology", "diagram")
REFERENCE_KEYWORDS = ("faq", "reference", "parameter", "command", "field")


def compute_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()



def detect_languages(texts: Iterable[str]) -> list[str]:
    joined = " ".join(texts).strip()
    if not joined:
        return ["unknown"]
    tags: list[str] = []
    if contains_arabic(joined):
        tags.append("ar")
    if re.search(r"[\u4E00-\u9FFF]", joined):
        tags.append("zh")
    if re.search(r"[\u3040-\u30FF]", joined):
        tags.append("ja")
    if re.search(r"[A-Za-z]", joined):
        tags.append("en")
    return tags or ["unknown"]



def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if contains_arabic(text):
        text = normalize_arabic_text(text)
    return text



def make_document(path: Path, relative_path: str, file_type: str, *, title: str | None = None, parser_used: str) -> NormalizedDocument:
    checksum = compute_checksum(path)
    return NormalizedDocument(
        document_id=checksum[:32],
        source_path=relative_path,
        file_name=path.name,
        file_type=file_type,
        title=title or safe_title_from_path(path),
        checksum=checksum,
        parser_used=parser_used,
        parser_confidence=0.85,
    )



def asset_path_for_storage(file_path: Path, root_dir: Path | None) -> str:
    if root_dir is not None:
        try:
            return str(file_path.relative_to(root_dir))
        except ValueError:
            pass
    return str(file_path)



def segment_to_chunks(document: NormalizedDocument, max_words: int, overlap_words: int) -> tuple[list[ChunkRecord], list[ImageRecord]]:
    from .chunking import document_to_chunks

    return document_to_chunks(document, max_words, overlap_words)



def blocks_to_chunks(document: NormalizedDocument, max_words: int, overlap_words: int) -> tuple[list[ChunkRecord], list[ImageRecord]]:
    blocks = materialize_blocks(document)
    document.blocks = blocks
    document.document_archetype = classify_document_archetype(document)
    document.metadata = {
        **document.metadata,
        "document_archetype": document.document_archetype,
        "block_count": len(blocks),
    }

    chunks: list[ChunkRecord] = []
    images: list[ImageRecord] = []
    emitted_image_paths: set[str] = set()
    chunk_index = 0

    for group in assemble_block_groups(blocks, document.document_archetype):
        combined_text = normalize_text("\n\n".join(block.text for block in group if block.text.strip()))
        if not combined_text:
            continue
        section_path = _group_section_path(group, document.title)
        title = _group_title(group, document.title)
        chunk_type = _chunk_type_for_group(group, document.document_archetype)
        block_ids = [block.block_id for block in group]
        block_types = [block.block_type for block in group]
        group_images = _collect_group_images(group)
        windows = window_text(combined_text, max_words=max_words, overlap_words=overlap_words)
        anchor = _group_anchor(group)
        for window in windows:
            if not window.strip():
                continue
            chunk_id = new_chunk_id()
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    source_path=document.source_path,
                    file_type=document.file_type,
                    document_archetype=document.document_archetype,
                    chunk_type=chunk_type,
                    title=title,
                    section_path=section_path,
                    chunk_index=chunk_index,
                    display_text=window,
                    embedding_text=build_embedding_text(
                        document_title=document.title,
                        section_path=section_path,
                        chunk_type=chunk_type,
                        location_hint=location_hint(anchor),
                        content=window,
                        document_archetype=document.document_archetype,
                    ),
                    block_ids=block_ids,
                    block_types=block_types,
                    language_tags=_group_languages(group, document.language_tags),
                    citation_anchor=anchor,
                    parser_used=document.parser_used,
                    parser_confidence=document.parser_confidence,
                    metadata={
                        **document.metadata,
                        **_merged_group_metadata(group),
                        "document_archetype": document.document_archetype,
                        "block_ids": block_ids,
                        "block_types": block_types,
                    },
                    image_refs=_unique_image_paths(group_images),
                )
            )
            chunk_index += 1
            for image_context in group_images:
                if image_context.image_path in emitted_image_paths:
                    continue
                emitted_image_paths.add(image_context.image_path)
                images.append(
                    ImageRecord(
                        image_id=image_context.image_id,
                        document_id=document.document_id,
                        source_path=document.source_path,
                        image_path=image_context.image_path,
                        document_archetype=document.document_archetype,
                        title=title,
                        caption_text=image_context.caption or image_context.alt_text or image_context.ocr_text,
                        related_section_path=section_path,
                        related_chunk_id=chunk_id,
                        related_block_ids=block_ids,
                        related_chunk_ids=[chunk_id],
                        language_tags=_group_languages(group, document.language_tags),
                        citation_anchor=anchor,
                        metadata={
                            "alt_text": image_context.alt_text,
                            "ocr_text": image_context.ocr_text,
                            "related_section_path": image_context.related_section_path,
                            "document_archetype": document.document_archetype,
                            "block_ids": block_ids,
                        },
                    )
                )

    seen_image_paths = {image.image_path for image in images}
    for image_context in document.images:
        if image_context.image_path in seen_image_paths:
            continue
        images.append(
            ImageRecord(
                image_id=image_context.image_id,
                document_id=document.document_id,
                source_path=document.source_path,
                image_path=image_context.image_path,
                document_archetype=document.document_archetype,
                title=document.title,
                caption_text=image_context.caption or image_context.alt_text or image_context.ocr_text,
                related_section_path=[document.title],
                related_block_ids=[],
                related_chunk_ids=[],
                language_tags=document.language_tags,
                metadata={
                    "alt_text": image_context.alt_text,
                    "ocr_text": image_context.ocr_text,
                    "document_archetype": document.document_archetype,
                },
            )
        )
    return chunks, images



def _unique_image_paths(image_contexts: list[ImageContext]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for image_context in image_contexts:
        if image_context.image_path in seen:
            continue
        seen.add(image_context.image_path)
        result.append(image_context.image_path)
    return result


def materialize_blocks(document: NormalizedDocument) -> list[BlockRecord]:
    if document.blocks:
        return document.blocks
    blocks: list[BlockRecord] = []
    for index, segment in enumerate(document.segments):
        block_type = _block_type_for_segment(segment.segment_type, segment.text)
        blocks.append(
            BlockRecord(
                block_id=segment.segment_id,
                block_type=block_type,
                text=segment.text,
                order_index=index,
                title=segment.title,
                section_path=segment.section_path,
                language_tags=segment.language_tags,
                metadata=dict(segment.metadata),
                citation_anchor=segment.citation_anchor,
                image_contexts=list(segment.image_contexts),
                step_number=_step_number(segment.text),
            )
        )
    return blocks



def classify_document_archetype(document: NormalizedDocument) -> str:
    blocks = materialize_blocks(document)
    block_types = {block.block_type for block in blocks}
    text = "\n".join(block.text for block in blocks if block.text).lower()
    figure_count = sum(1 for block in blocks if block.block_type in {"figure", "caption"} or block.image_contexts)
    step_count = sum(1 for block in blocks if block.block_type == "step")

    if any(block.citation_anchor.sheet_name for block in blocks) or {"table", "table_row"} & block_types:
        return "tabular"
    if any(block.citation_anchor.slide_number for block in blocks):
        return "presentation"

    regulatory_signal = any(keyword in text for keyword in REGULATORY_KEYWORDS)
    procedural_signal = step_count >= 2 or any(keyword in text for keyword in PROCEDURAL_KEYWORDS)
    technical_signal = any(keyword in text for keyword in TECHNICAL_KEYWORDS)
    reference_signal = any(keyword in text for keyword in REFERENCE_KEYWORDS)

    if figure_count and (regulatory_signal or procedural_signal or technical_signal):
        return "mixed_multimodal"
    if procedural_signal:
        return "procedural"
    if regulatory_signal:
        return "regulatory"
    if technical_signal:
        return "technical"
    if reference_signal:
        return "reference"
    return "knowledge"



def assemble_block_groups(blocks: list[BlockRecord], archetype: str) -> list[list[BlockRecord]]:
    groups: list[list[BlockRecord]] = []
    pending_headings: list[BlockRecord] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.block_type == "heading":
            pending_headings.append(block)
            index += 1
            continue

        group = pending_headings + [block]
        pending_headings = []

        if block.block_type in {"step", "list_item"}:
            index += 1
            while index < len(blocks):
                candidate = blocks[index]
                if candidate.block_type == "heading":
                    break
                if candidate.section_path != block.section_path:
                    break
                if candidate.block_type in {"step", "list_item"}:
                    break
                if candidate.block_type in {"note", "warning", "figure", "caption", "paragraph"}:
                    group.append(candidate)
                    index += 1
                    continue
                break
            groups.append(group)
            continue

        if archetype in {"regulatory", "knowledge", "technical", "reference", "mixed_multimodal"} and block.block_type in {"paragraph", "note", "warning", "caption", "figure"}:
            index += 1
            while index < len(blocks):
                candidate = blocks[index]
                if candidate.block_type == "heading":
                    break
                if candidate.section_path != block.section_path:
                    break
                if candidate.block_type in {"step", "list_item", "table", "table_row"}:
                    break
                group.append(candidate)
                index += 1
            groups.append(group)
            continue

        if block.block_type in {"figure", "caption"} and index + 1 < len(blocks):
            next_block = blocks[index + 1]
            if next_block.block_type != "heading" and next_block.section_path == block.section_path:
                group.append(next_block)
                index += 1

        groups.append(group)
        index += 1

    if pending_headings:
        groups.append(pending_headings)
    return groups



def build_embedding_text(*, document_title: str, section_path: list[str], chunk_type: str, location_hint: str, content: str, document_archetype: str = "unknown") -> str:
    return (
        f"Document title: {document_title}\n"
        f"Archetype: {document_archetype}\n"
        f"Section path: {' > '.join(section_path)}\n"
        f"Content type: {chunk_type}\n"
        f"Location: {location_hint or 'unknown'}\n\n"
        f"Content:\n{content}"
    )



def location_hint(anchor: CitationAnchor) -> str:
    if anchor.page_number is not None:
        return f"page {anchor.page_number}"
    if anchor.slide_number is not None:
        return f"slide {anchor.slide_number}"
    if anchor.sheet_name:
        return f"sheet {anchor.sheet_name}"
    if anchor.json_path:
        return f"json {anchor.json_path}"
    if anchor.rst_path:
        return f"rst {anchor.rst_path}"
    if anchor.line_start is not None:
        return f"line {anchor.line_start}"
    return anchor.source_label



def window_text(text: str, *, max_words: int, overlap_words: int) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return []
    windows: list[str] = []
    current: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        words = len(paragraph.split())
        if current and current_words + words > max_words:
            windows.append("\n\n".join(current).strip())
            if overlap_words > 0:
                overlap: list[str] = []
                carry = 0
                for item in reversed(current):
                    overlap.insert(0, item)
                    carry += len(item.split())
                    if carry >= overlap_words:
                        break
                current = overlap
                current_words = sum(len(item.split()) for item in current)
            else:
                current = []
                current_words = 0
        current.append(paragraph)
        current_words += words
    if current:
        windows.append("\n\n".join(current).strip())
    return windows



def _block_type_for_segment(segment_type: str, text: str) -> str:
    mapping = {
        "table": "table",
        "table_row": "table_row",
        "json_object": "paragraph",
        "code_block": "code",
        "image_caption": "caption",
        "slide": "paragraph",
        "sheet_summary": "paragraph",
        "list_item": "list_item",
        "note": "note",
    }
    if segment_type == "paragraph" and STEP_RE.match(text.strip()):
        return "step"
    return mapping.get(segment_type, "paragraph")



def _chunk_type_for_group(group: list[BlockRecord], archetype: str) -> str:
    block_types = {block.block_type for block in group}
    if any(block.citation_anchor.slide_number is not None for block in group):
        return "slide_chunk"
    if "table_row" in block_types:
        return "row_chunk"
    if "table" in block_types:
        return "table_chunk"
    if "code" in block_types:
        return "code_chunk"
    if {"figure", "caption"} & block_types:
        return "figure_explainer_chunk" if len(block_types) > 1 else "image_caption_chunk"
    if archetype == "procedural" and block_types & {"step", "list_item"}:
        return "procedure_chunk"
    if archetype == "mixed_multimodal" and (block_types & {"step", "list_item"} or {"figure", "caption"} & block_types):
        return "mixed_context_chunk"
    if archetype == "regulatory":
        return "policy_clause_chunk"
    if archetype == "reference":
        return "reference_entry_chunk"
    if block_types == {"heading"}:
        return "section_chunk"
    if "list_item" in block_types:
        return "list_chunk"
    if "note" in block_types or "warning" in block_types:
        return "note_chunk"
    return "section_chunk" if "heading" in block_types else "narrative_chunk"



def _group_section_path(group: list[BlockRecord], document_title: str) -> list[str]:
    for block in group:
        if block.section_path:
            return block.section_path
    return [document_title]



def _group_title(group: list[BlockRecord], document_title: str) -> str:
    for block in reversed(group):
        if block.title:
            return block.title
    section_path = _group_section_path(group, document_title)
    return section_path[-1] if section_path else document_title



def _group_anchor(group: list[BlockRecord]) -> CitationAnchor:
    for block in group:
        anchor = block.citation_anchor
        if location_hint(anchor):
            return anchor
    return CitationAnchor()



def _group_languages(group: list[BlockRecord], document_languages: list[str]) -> list[str]:
    tags: list[str] = []
    for block in group:
        for tag in block.language_tags:
            if tag not in tags:
                tags.append(tag)
    return tags or document_languages



def _merged_group_metadata(group: list[BlockRecord]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for block in group:
        metadata.update(block.metadata)
    return metadata



def _collect_group_images(group: list[BlockRecord]) -> list:
    images = []
    seen: set[str] = set()
    for block in group:
        for image in block.image_contexts:
            key = image.image_id or image.image_path
            if key in seen:
                continue
            seen.add(key)
            images.append(image)
    return images



def _step_number(text: str) -> str:
    match = STEP_RE.match(text.strip())
    if not match:
        return ""
    return match.group(0).strip()



def serialize_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
