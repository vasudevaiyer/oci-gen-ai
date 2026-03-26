from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import detect_languages, make_document, normalize_text
from ..schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedSegment


class ImageFileParser:
    parser_name = "image_parser"

    def __init__(self, root_dir: Path | None = None, genai: Any | None = None) -> None:
        self.root_dir = root_dir
        self.genai = genai

    def parse(self, path: Path, relative_path: str):
        document = make_document(path, relative_path, path.suffix.lower().lstrip('.'), parser_used=self.parser_name)
        image_context = ImageContext(
            image_id=f"{document.document_id}-image-0",
            image_path=relative_path,
            related_section_path=document.title,
        )

        structure = self._image_structure(path)
        title = normalize_text(str(structure.get('title') or document.title)) or document.title
        summary = normalize_text(str(structure.get('summary') or ''))
        visible_text = [normalize_text(str(value)) for value in structure.get('visible_text', []) if normalize_text(str(value))]
        sections = [section for section in structure.get('sections', []) if isinstance(section, dict)]
        image_type = normalize_text(str(structure.get('image_type') or 'unknown')) or 'unknown'

        blocks: list[BlockRecord] = []
        segments: list[NormalizedSegment] = []
        order_index = 0
        segment_index = 0
        root_section = [document.title]

        if title and title != document.title:
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{order_index}",
                    block_type='heading',
                    text=title,
                    order_index=order_index,
                    title=title,
                    section_path=[document.title, title],
                    citation_anchor=CitationAnchor(source_label=document.file_name),
                    heading_level=1,
                    metadata={'layout_hint': 'image_title', 'image_type': image_type},
                )
            )
            order_index += 1
            root_section = [document.title, title]

        summary_text = summary or (visible_text[0] if visible_text else f"Image file: {document.file_name}")
        blocks.append(
            BlockRecord(
                block_id=f"{document.document_id}-block-{order_index}",
                block_type='figure',
                text=summary_text,
                order_index=order_index,
                title=root_section[-1],
                section_path=root_section,
                citation_anchor=CitationAnchor(source_label=document.file_name),
                image_contexts=[image_context],
                metadata={'layout_hint': 'image_summary', 'image_type': image_type},
            )
        )
        segments.append(
            NormalizedSegment(
                segment_id=f"{document.document_id}-seg-{segment_index}",
                segment_type='image_caption',
                text=summary_text,
                title=root_section[-1],
                section_path=root_section,
                citation_anchor=CitationAnchor(source_label=document.file_name),
                image_contexts=[image_context],
                metadata={'layout_hint': 'image_summary', 'image_type': image_type},
            )
        )
        order_index += 1
        segment_index += 1

        if visible_text:
            visible_text_block = normalize_text("\n".join(visible_text[:8]))
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{order_index}",
                    block_type='note',
                    text=visible_text_block,
                    order_index=order_index,
                    title=root_section[-1],
                    section_path=[*root_section, 'Visible Text'],
                    citation_anchor=CitationAnchor(source_label=document.file_name),
                    metadata={'layout_hint': 'visible_text', 'image_type': image_type},
                )
            )
            segments.append(
                NormalizedSegment(
                    segment_id=f"{document.document_id}-seg-{segment_index}",
                    segment_type='note',
                    text=visible_text_block,
                    title='Visible Text',
                    section_path=[*root_section, 'Visible Text'],
                    citation_anchor=CitationAnchor(source_label=document.file_name),
                    metadata={'layout_hint': 'visible_text', 'image_type': image_type},
                )
            )
            order_index += 1
            segment_index += 1

        for section in sections[:6]:
            heading = normalize_text(str(section.get('heading') or ''))
            content = normalize_text(str(section.get('content') or ''))
            if not content:
                continue
            section_path = [*root_section, heading] if heading else root_section
            if heading:
                blocks.append(
                    BlockRecord(
                        block_id=f"{document.document_id}-block-{order_index}",
                        block_type='heading',
                        text=heading,
                        order_index=order_index,
                        title=heading,
                        section_path=section_path,
                        citation_anchor=CitationAnchor(source_label=document.file_name),
                        heading_level=2,
                        metadata={'layout_hint': 'image_section_heading', 'image_type': image_type},
                    )
                )
                order_index += 1
            block_type = _section_block_type(section.get('block_type'))
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{order_index}",
                    block_type=block_type,
                    text=content,
                    order_index=order_index,
                    title=section_path[-1],
                    section_path=section_path,
                    citation_anchor=CitationAnchor(source_label=document.file_name),
                    metadata={'layout_hint': 'image_section', 'image_type': image_type},
                )
            )
            segments.append(
                NormalizedSegment(
                    segment_id=f"{document.document_id}-seg-{segment_index}",
                    segment_type='paragraph',
                    text=content,
                    title=section_path[-1],
                    section_path=section_path,
                    citation_anchor=CitationAnchor(source_label=document.file_name),
                    metadata={'layout_hint': 'image_section', 'image_type': image_type},
                )
            )
            order_index += 1
            segment_index += 1

        document.images = [image_context]
        document.blocks = blocks
        document.segments = segments
        document.metadata = {
            **document.metadata,
            'document_structure': 'image_analysis',
            'chunking_hints': {
                'structure': 'image_analysis',
                'image_type': image_type,
                'section_count': len(sections[:6]),
            },
            'image_type': image_type,
        }
        document.language_tags = detect_languages(block.text or block.title for block in blocks if block.text or block.title)
        for block in document.blocks:
            block.language_tags = document.language_tags
        for segment in document.segments:
            segment.language_tags = document.language_tags
        return document

    def _image_structure(self, path: Path) -> dict[str, Any]:
        extractor = getattr(self.genai, 'extract_image_structure', None)
        if callable(extractor):
            try:
                payload = extractor(path)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                return payload
        return {
            'image_type': 'unknown',
            'title': path.stem.replace('_', ' ').replace('-', ' '),
            'summary': f'Image file {path.name}',
            'visible_text': [],
            'sections': [],
        }


def _section_block_type(value: Any) -> str:
    block_type = str(value or '').strip().casefold()
    if block_type in {'paragraph', 'list_item', 'table', 'note', 'warning', 'code', 'quote'}:
        return block_type
    return 'paragraph'
