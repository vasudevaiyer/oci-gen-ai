from __future__ import annotations

import re
from pathlib import Path

from .base import detect_languages, make_document, normalize_text
from ..schemas import BlockRecord, CitationAnchor, NormalizedSegment

HEADING_UNDERLINE_CHARS = set("=-~^#*+")
STEP_RE = re.compile(r"^(?:step\s+)?(?:\d+|[a-zA-Z])[\).:-]\s+")


class TextParser:
    parser_name = "text_parser"

    def parse(self, path: Path, relative_path: str):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        lines = raw.splitlines()
        document = make_document(path, relative_path, path.suffix.lower().lstrip("."), parser_used=self.parser_name)
        blocks: list[BlockRecord] = []
        segments: list[NormalizedSegment] = []
        current_section = document.title
        paragraph_lines: list[str] = []
        block_start = 1
        line_number = 1

        def flush(end_line: int) -> None:
            nonlocal paragraph_lines, block_start
            text = normalize_text("\n".join(paragraph_lines))
            if not text:
                paragraph_lines = []
                return
            block_type = "list_item" if text.lstrip().startswith(("- ", "* ")) else "paragraph"
            if STEP_RE.match(text):
                block_type = "step"
            section_path = [document.title, current_section] if current_section != document.title else [document.title]
            anchor = CitationAnchor(source_label=relative_path, line_start=block_start, line_end=end_line)
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{len(blocks)}",
                    block_type=block_type,
                    text=text,
                    order_index=len(blocks),
                    title=current_section,
                    section_path=section_path,
                    citation_anchor=anchor,
                    step_number=text.split()[0] if block_type == "step" else "",
                    metadata={"line_start": block_start, "line_end": end_line},
                )
            )
            segments.append(
                NormalizedSegment(
                    segment_id=f"{document.document_id}-seg-{len(segments)}",
                    segment_type="paragraph",
                    text=text,
                    title=current_section,
                    section_path=section_path,
                    citation_anchor=anchor,
                    metadata={"line_start": block_start, "line_end": end_line},
                )
            )
            paragraph_lines = []

        while line_number <= len(lines):
            line = lines[line_number - 1]
            next_line = lines[line_number] if line_number < len(lines) else ""
            if line.strip() and next_line.strip() and len(next_line.strip()) >= len(line.strip()) and set(next_line.strip()) <= HEADING_UNDERLINE_CHARS:
                flush(line_number - 1)
                current_section = normalize_text(line.strip())
                section_path = [document.title, current_section]
                blocks.append(
                    BlockRecord(
                        block_id=f"{document.document_id}-block-{len(blocks)}",
                        block_type="heading",
                        text=current_section,
                        order_index=len(blocks),
                        title=current_section,
                        section_path=section_path,
                        citation_anchor=CitationAnchor(source_label=relative_path, line_start=line_number, line_end=line_number + 1),
                        metadata={"line_start": line_number, "line_end": line_number + 1, "heading_style": "underlined"},
                    )
                )
                line_number += 2
                block_start = line_number
                continue

            if _looks_like_heading(line):
                flush(line_number - 1)
                current_section = normalize_text(line.strip())
                section_path = [document.title, current_section]
                blocks.append(
                    BlockRecord(
                        block_id=f"{document.document_id}-block-{len(blocks)}",
                        block_type="heading",
                        text=current_section,
                        order_index=len(blocks),
                        title=current_section,
                        section_path=section_path,
                        citation_anchor=CitationAnchor(source_label=relative_path, line_start=line_number, line_end=line_number),
                        metadata={"line_start": line_number, "line_end": line_number, "heading_style": "heuristic"},
                    )
                )
                line_number += 1
                block_start = line_number
                continue

            if not line.strip():
                flush(line_number)
                block_start = line_number + 1
                line_number += 1
                continue

            if not paragraph_lines:
                block_start = line_number
            paragraph_lines.append(line)
            line_number += 1

        flush(len(lines))
        document.blocks = blocks
        document.segments = segments
        document.metadata = {
            **document.metadata,
            "document_structure": "line_sections",
            "chunking_hints": _build_chunking_hints(document),
        }
        document.language_tags = detect_languages(block.text for block in blocks if block.text)
        for block in document.blocks:
            block.language_tags = document.language_tags
        for segment in document.segments:
            segment.language_tags = document.language_tags
        return document


def _looks_like_heading(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    words = text.split()
    if len(words) > 8:
        return False
    if text.endswith((".", ";", "?", "!")):
        return False
    if STEP_RE.match(text):
        return False
    alphabetic = [char for char in text if char.isalpha()]
    if alphabetic and sum(1 for char in alphabetic if char.isupper()) / len(alphabetic) > 0.75:
        return True
    return text.istitle() and len(words) <= 6


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
                "block_ids": [candidate.block_id for candidate in document.blocks if candidate.section_path == block.section_path],
            }
        )
    return {
        "structure": "line_sections",
        "section_count": len(sections),
        "sections": sections,
    }
