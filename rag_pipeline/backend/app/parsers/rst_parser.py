from __future__ import annotations

import re
from pathlib import Path

from .base import asset_path_for_storage, detect_languages, make_document, normalize_text
from ..schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedSegment, new_image_id

HEADING_CHARS = set("=-~^\"`:#*+")
DIRECTIVE_RE = re.compile(r"^\.\.\s+([a-zA-Z0-9_-]+)::\s*(.*)$")
ANCHOR_RE = re.compile(r"^\.\. _([^:]+):\s*$")
EQ_LABEL_RE = re.compile(r"^\s*:label:\s*(.+?)\s*$")
INLINE_MATH_RE = re.compile(r":math:`([^`]+)`")
IMAGE_DIRECTIVES = {"image", "figure"}
INDENT_PREFIXES = ("   ", "\t")


class RstParser:
    parser_name = "rst_parser"

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir

    def parse(self, path: Path, relative_path: str):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        lines = raw.splitlines()
        document = make_document(path, relative_path, "rst", parser_used=self.parser_name)
        blocks: list[BlockRecord] = []
        segments: list[NormalizedSegment] = []
        images: list[ImageContext] = []
        section_stack: list[str] = [document.title]
        buffer: list[str] = []
        buffer_type = "paragraph"
        block_start = 1
        line_number = 1

        def flush(end_line: int) -> None:
            nonlocal buffer, buffer_type, block_start
            text = normalize_text("\n".join(buffer))
            if not text:
                buffer = []
                return
            anchor = CitationAnchor(
                rst_path=" > ".join(section_stack),
                line_start=block_start,
                line_end=end_line,
                source_label=relative_path,
            )
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{len(blocks)}",
                    block_type=_block_type_for_buffer(buffer_type),
                    text=text,
                    order_index=len(blocks),
                    title=section_stack[-1],
                    section_path=section_stack[:],
                    citation_anchor=anchor,
                    metadata={"directive_type": buffer_type if buffer_type != "paragraph" else ""},
                )
            )
            segments.append(
                NormalizedSegment(
                    segment_id=f"{document.document_id}-seg-{len(segments)}",
                    segment_type=buffer_type,
                    text=text,
                    title=section_stack[-1],
                    section_path=section_stack[:],
                    citation_anchor=anchor,
                    metadata={"directive_type": buffer_type if buffer_type != "paragraph" else ""},
                )
            )
            buffer = []
            buffer_type = "paragraph"

        while line_number <= len(lines):
            line = lines[line_number - 1]
            next_line = lines[line_number] if line_number < len(lines) else ""
            if line and next_line and len(next_line) >= len(line.strip()) and set(next_line.strip()) <= HEADING_CHARS:
                flush(line_number - 1)
                level = _heading_level(next_line.strip()[:1])
                section_stack = section_stack[: max(level - 1, 0)] + [line.strip()]
                blocks.append(
                    BlockRecord(
                        block_id=f"{document.document_id}-block-{len(blocks)}",
                        block_type="heading",
                        text=line.strip(),
                        order_index=len(blocks),
                        title=section_stack[-1],
                        section_path=section_stack[:],
                        citation_anchor=CitationAnchor(
                            rst_path=" > ".join(section_stack),
                            line_start=line_number,
                            line_end=line_number + 1,
                            source_label=relative_path,
                        ),
                        heading_level=level,
                        metadata={"heading_char": next_line.strip()[:1]},
                    )
                )
                line_number += 2
                block_start = line_number
                continue

            directive = DIRECTIVE_RE.match(line)
            if directive:
                directive_name = directive.group(1)
                directive_arg = directive.group(2).strip()
                flush(line_number - 1)
                if directive_name in IMAGE_DIRECTIVES:
                    image_context, caption_text, end_line = _parse_image_directive(path, line_number, lines, directive_arg, self.root_dir)
                    if image_context is not None:
                        images.append(image_context)
                        segment_text = normalize_text(caption_text or image_context.alt_text or directive_arg)
                        if segment_text:
                            anchor = CitationAnchor(
                                rst_path=" > ".join(section_stack),
                                line_start=line_number,
                                line_end=end_line,
                                source_label=relative_path,
                            )
                            blocks.append(
                                BlockRecord(
                                    block_id=f"{document.document_id}-block-{len(blocks)}",
                                    block_type="caption",
                                    text=segment_text,
                                    order_index=len(blocks),
                                    title=section_stack[-1],
                                    section_path=section_stack[:],
                                    citation_anchor=anchor,
                                    metadata={
                                        "directive_type": directive_name,
                                        "image_target": directive_arg,
                                        "alt_text": image_context.alt_text,
                                    },
                                    image_contexts=[image_context],
                                )
                            )
                            segments.append(
                                NormalizedSegment(
                                    segment_id=f"{document.document_id}-seg-{len(segments)}",
                                    segment_type="image_caption",
                                    text=segment_text,
                                    title=section_stack[-1],
                                    section_path=section_stack[:],
                                    citation_anchor=anchor,
                                    metadata={
                                        "directive_type": directive_name,
                                        "image_target": directive_arg,
                                        "alt_text": image_context.alt_text,
                                    },
                                    image_contexts=[image_context],
                                )
                            )
                    line_number = end_line + 1
                    block_start = line_number
                    continue

                buffer_type = "code_block" if directive_name == "code-block" else "note"
                block_start = line_number
                title = directive_arg
                if title:
                    buffer.append(title)
                line_number += 1
                continue

            if line.startswith("    ") and buffer_type == "code_block":
                if not buffer:
                    block_start = line_number
                buffer.append(line[4:])
                line_number += 1
                continue

            if not line.strip():
                flush(line_number)
                block_start = line_number + 1
                line_number += 1
                continue

            if line.lstrip().startswith(("- ", "* ")):
                if buffer and buffer_type != "list_item":
                    flush(line_number - 1)
                buffer_type = "list_item"

            if not buffer:
                block_start = line_number
            buffer.append(line)
            line_number += 1

        flush(len(lines))
        document.images = images
        document.blocks = blocks
        document.segments = segments
        document.language_tags = detect_languages(block.text for block in blocks)
        document.metadata = {
            **document.metadata,
            "document_structure": "rst_sections",
            "chunking_hints": _build_chunking_hints(lines, relative_path),
        }
        for block in document.blocks:
            block.language_tags = document.language_tags
        for segment in document.segments:
            segment.language_tags = document.language_tags
        return document


def _parse_image_directive(path: Path, start_line: int, lines: list[str], target: str, root_dir: Path | None) -> tuple[ImageContext | None, str, int]:
    alt_text = ""
    caption_lines: list[str] = []
    line_index = start_line
    while line_index < len(lines):
        line = lines[line_index]
        if line.strip() == "":
            line_index += 1
            continue
        if not line.startswith(INDENT_PREFIXES):
            break
        stripped = line.strip()
        if stripped.startswith(":alt:"):
            alt_text = stripped.split(":alt:", 1)[1].strip()
        elif stripped.startswith(":"):
            pass
        else:
            caption_lines.append(stripped)
        line_index += 1

    resolved = (path.parent / target).resolve()
    image_context = None
    if resolved.exists() and resolved.is_file():
        rel_path = asset_path_for_storage(resolved, root_dir)
        image_context = ImageContext(
            image_id=new_image_id(),
            image_path=rel_path,
            alt_text=alt_text,
            caption=normalize_text(" ".join(caption_lines)),
            related_section_path=path.stem,
        )

    return image_context, normalize_text("\n".join(caption_lines)), line_index


def _build_chunking_hints(lines: list[str], relative_path: str) -> dict[str, object]:
    sections = _extract_sections(lines, relative_path)
    return {
        "preferred_strategy": "rst_section_window",
        "structure": "rst_sections",
        "section_count": len(sections),
        "sections": sections,
    }


def _extract_sections(lines: list[str], relative_path: str) -> list[dict[str, object]]:
    headings = _find_headings(lines)
    if not headings:
        headings = [(0, Path(relative_path).stem, 1, 0)]

    sections: list[dict[str, object]] = []
    hierarchy: list[tuple[int, str]] = []
    for index, (_line_index, heading, level, content_start) in enumerate(headings):
        while hierarchy and hierarchy[-1][0] >= level:
            hierarchy.pop()
        hierarchy.append((level, heading))
        next_heading_start = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
        blocks = _to_line_blocks(lines[content_start:next_heading_start], start_line=content_start + 1)
        if not blocks:
            continue
        section_path = [item[1] for item in hierarchy]
        sections.append(
            {
                "section_path": section_path,
                "heading_level": level,
                "line_start": content_start + 1,
                "line_end": next_heading_start,
                "blocks": [_build_block_hint(block, relative_path) for block in blocks],
            }
        )
    return sections


def _build_block_hint(block: dict[str, object], relative_path: str) -> dict[str, object]:
    lines = [str(line) for line in block["lines"]]
    anchors = [match.group(1) for line in lines if (match := ANCHOR_RE.match(line))]
    image_refs: list[str] = []
    directive_types: list[str] = []
    for line in lines:
        directive = DIRECTIVE_RE.match(line)
        if not directive:
            continue
        directive_name = directive.group(1)
        directive_types.append(directive_name)
        if directive_name in IMAGE_DIRECTIVES:
            image_refs.append(_normalize_image_ref(relative_path, directive.group(2).strip()))
    equation_labels = [match.group(1) for line in lines if (match := EQ_LABEL_RE.match(line))]
    inline_math_count = sum(len(INLINE_MATH_RE.findall(line)) for line in lines)
    return {
        "line_start": block["line_start"],
        "line_end": block["line_end"],
        "lines": lines,
        "anchors": anchors,
        "image_refs": image_refs,
        "equation_labels": equation_labels,
        "directive_types": directive_types,
        "inline_math_count": inline_math_count,
    }


def _find_headings(lines: list[str]) -> list[tuple[int, str, int, int]]:
    headings: list[tuple[int, str, int, int]] = []
    for index in range(len(lines) - 1):
        title = lines[index].rstrip()
        underline = lines[index + 1].strip()
        if not title or len(underline) < len(title.strip()):
            continue
        if len(set(underline)) == 1 and underline[0] in HEADING_CHARS:
            headings.append((index, title.strip(), _heading_level(underline[0]), index + 2))
    return headings


def _to_line_blocks(lines: list[str], start_line: int) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    current: list[str] = []
    block_start = start_line
    for offset, line in enumerate(lines):
        line_number = start_line + offset
        if line.strip():
            if not current:
                block_start = line_number
            current.append(line)
            continue
        if current:
            blocks.append({"line_start": block_start, "line_end": line_number - 1, "lines": current[:]})
            current = []
    if current:
        blocks.append({"line_start": block_start, "line_end": start_line + len(lines) - 1, "lines": current[:]})
    return blocks


def _normalize_image_ref(source_path: str, image_ref: str) -> str:
    source_dir = Path(source_path).parent
    return str((source_dir / image_ref).as_posix())


def _heading_level(char: str) -> int:
    order = ["=", "-", "~", "^", '"', "`", ":", "#", "*", "+"]
    return order.index(char) + 1 if char in order else 2


def _block_type_for_buffer(buffer_type: str) -> str:
    mapping = {
        "paragraph": "paragraph",
        "list_item": "list_item",
        "code_block": "code",
        "note": "note",
    }
    return mapping.get(buffer_type, "paragraph")
