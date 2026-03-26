from __future__ import annotations

from .base import blocks_to_chunks, classify_document_archetype, detect_languages, materialize_blocks, normalize_text
from ..schemas import ChunkRecord, CitationAnchor, ImageRecord, NormalizedDocument, new_chunk_id


def chunk_rst_document(document: NormalizedDocument, max_words: int, overlap_words: int) -> tuple[list[ChunkRecord], list[ImageRecord]]:
    chunking_hints = document.metadata.get("chunking_hints") or {}
    sections = chunking_hints.get("sections") or []
    if not sections:
        document.metadata = {
            **document.metadata,
            "chunking_strategy": "generic_blocks",
        }
        return blocks_to_chunks(document, max_words, overlap_words)

    blocks = materialize_blocks(document)
    document.blocks = blocks
    document.document_archetype = classify_document_archetype(document)
    document.metadata = {
        **document.metadata,
        "document_archetype": document.document_archetype,
        "block_count": len(blocks),
        "chunking_strategy": "rst_section_window",
        "document_structure": chunking_hints.get("structure", "rst_sections"),
        "structure_section_count": len(sections),
    }
    document.metadata.pop("chunking_hints", None)

    chunks: list[ChunkRecord] = []
    images: list[ImageRecord] = []
    chunk_index = 0
    image_contexts = {image.image_path: image for image in document.images}
    emitted_image_paths: set[str] = set()

    for section in sections:
        section_path = list(section.get("section_path") or [document.title])
        section_blocks = list(section.get("blocks") or [])
        for window in _window_blocks(section_blocks, max_words=max_words, overlap_words=overlap_words):
            lines = _flatten_window_lines(window)
            display_text = _clean_chunk_text(lines)
            if not display_text:
                continue
            line_start = int(window[0]["line_start"])
            line_end = int(window[-1]["line_end"])
            anchors = _unique_values(window, "anchors")
            image_refs = _unique_values(window, "image_refs")
            equation_labels = _unique_values(window, "equation_labels")
            directive_types = _unique_values(window, "directive_types")
            inline_math_count = sum(int(block.get("inline_math_count", 0)) for block in window)
            block_ids, block_types = _window_block_details(blocks, section_path, line_start, line_end)
            citation_anchor = CitationAnchor(
                rst_path=" > ".join(section_path),
                line_start=line_start,
                line_end=line_end,
                source_label=document.source_path,
            )
            chunk_type = _chunk_type_for_window(document.document_archetype, block_types, image_refs, equation_labels, directive_types)
            chunk_id = new_chunk_id()
            language_tags = detect_languages([display_text]) or document.language_tags
            metadata = {
                **document.metadata,
                "anchors": anchors,
                "image_refs": image_refs,
                "equation_labels": equation_labels,
                "directive_types": directive_types,
                "inline_math_count": inline_math_count,
                "block_ids": block_ids,
                "block_types": block_types,
                "line_start": line_start,
                "line_end": line_end,
            }
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    source_path=document.source_path,
                    file_type=document.file_type,
                    document_archetype=document.document_archetype,
                    chunk_type=chunk_type,
                    title=section_path[-1],
                    section_path=section_path,
                    chunk_index=chunk_index,
                    display_text=display_text,
                    embedding_text=_build_rst_embedding_text(
                        document=document,
                        section_path=section_path,
                        display_text=display_text,
                        chunk_type=chunk_type,
                        citation_anchor=citation_anchor,
                        anchors=anchors,
                        image_refs=image_refs,
                        equation_labels=equation_labels,
                        directive_types=directive_types,
                        inline_math_count=inline_math_count,
                    ),
                    block_ids=block_ids,
                    block_types=block_types,
                    language_tags=language_tags,
                    citation_anchor=citation_anchor,
                    parser_used=document.parser_used,
                    parser_confidence=document.parser_confidence,
                    metadata=metadata,
                    image_refs=image_refs,
                )
            )
            chunk_index += 1

            for image_ref in image_refs:
                image_context = image_contexts.get(image_ref)
                if image_context is None:
                    continue
                emitted_image_paths.add(image_ref)
                images.append(
                    ImageRecord(
                        image_id=image_context.image_id,
                        document_id=document.document_id,
                        source_path=document.source_path,
                        image_path=image_context.image_path,
                        document_archetype=document.document_archetype,
                        title=section_path[-1],
                        caption_text=image_context.caption or image_context.alt_text or display_text[:700],
                        related_section_path=section_path,
                        related_chunk_id=chunk_id,
                        related_block_ids=block_ids,
                        related_chunk_ids=[chunk_id],
                        language_tags=language_tags,
                        citation_anchor=citation_anchor,
                        metadata={
                            "alt_text": image_context.alt_text,
                            "ocr_text": image_context.ocr_text,
                            "related_section_path": image_context.related_section_path,
                            "document_archetype": document.document_archetype,
                            "anchors": anchors,
                            "equation_labels": equation_labels,
                        },
                    )
                )

    for image_context in document.images:
        if image_context.image_path in emitted_image_paths:
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


def _window_blocks(blocks: list[dict[str, object]], *, max_words: int, overlap_words: int) -> list[list[dict[str, object]]]:
    windows: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    current_words = 0
    for block in blocks:
        block_words = len(" ".join(str(line) for line in block.get("lines", [])).split())
        if current and current_words + block_words > max_words:
            windows.append(current[:])
            if overlap_words > 0:
                overlap: list[dict[str, object]] = []
                carry = 0
                for item in reversed(current):
                    overlap.insert(0, item)
                    carry += len(" ".join(str(line) for line in item.get("lines", [])).split())
                    if carry >= overlap_words:
                        break
                current = overlap[:]
                current_words = sum(len(" ".join(str(line) for line in item.get("lines", [])).split()) for item in current)
            else:
                current = []
                current_words = 0
        current.append(block)
        current_words += block_words
    if current:
        windows.append(current)
    return windows


def _flatten_window_lines(window: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for index, block in enumerate(window):
        lines.extend(str(line) for line in block.get("lines", []))
        if index < len(window) - 1:
            lines.append("")
    return lines


def _clean_chunk_text(lines: list[str]) -> str:
    rendered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(".. _") and stripped.endswith(":"):
            rendered.append(f"[Anchor: {stripped[4:-1]}]")
            continue
        if stripped.startswith(".. math::"):
            rendered.append("[Math]")
            continue
        if stripped.startswith(".. image::") or stripped.startswith(".. figure::"):
            rendered.append(f"[Image: {stripped.split('::', 1)[1].strip()}]")
            continue
        if stripped.startswith(".. code-block::"):
            rendered.append(f"[Code block: {stripped.split('::', 1)[1].strip() or 'text'}]")
            continue
        if stripped.startswith(":label:"):
            rendered.append(f"[Equation label: {stripped.split(':label:', 1)[1].strip()}]")
            continue
        rendered.append(stripped)
    return normalize_text("\n".join(item for item in rendered if item))


def _unique_values(window: list[dict[str, object]], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for block in window:
        for value in block.get(key, []):
            if value in seen:
                continue
            seen.add(value)
            values.append(str(value))
    return values


def _window_block_details(blocks, section_path: list[str], line_start: int, line_end: int) -> tuple[list[str], list[str]]:
    block_ids: list[str] = []
    block_types: list[str] = []
    for block in blocks:
        if block.section_path != section_path:
            continue
        anchor = block.citation_anchor
        if anchor.line_start is None or anchor.line_end is None:
            continue
        if anchor.line_start > line_end or anchor.line_end < line_start:
            continue
        block_ids.append(block.block_id)
        block_types.append(block.block_type)
    return block_ids, block_types


def _chunk_type_for_window(
    archetype: str,
    block_types: list[str],
    image_refs: list[str],
    equation_labels: list[str],
    directive_types: list[str],
) -> str:
    block_type_set = set(block_types)
    if image_refs:
        return "figure_explainer_chunk"
    if "code" in block_type_set or "code-block" in directive_types:
        return "code_chunk"
    if archetype == "procedural" and block_type_set & {"step", "list_item"}:
        return "procedure_chunk"
    if equation_labels or "math" in directive_types:
        return "reference_entry_chunk"
    if archetype == "regulatory":
        return "policy_clause_chunk"
    if archetype == "reference":
        return "reference_entry_chunk"
    return "section_chunk"


def _build_rst_embedding_text(
    *,
    document: NormalizedDocument,
    section_path: list[str],
    display_text: str,
    chunk_type: str,
    citation_anchor: CitationAnchor,
    anchors: list[str],
    image_refs: list[str],
    equation_labels: list[str],
    directive_types: list[str],
    inline_math_count: int,
) -> str:
    return (
        f"Document title: {document.title}\n"
        f"Archetype: {document.document_archetype}\n"
        f"Section path: {' > '.join(section_path)}\n"
        f"Content type: {chunk_type}\n"
        f"RST anchors: {', '.join(anchors) if anchors else 'none'}\n"
        f"RST images: {', '.join(image_refs) if image_refs else 'none'}\n"
        f"RST equation labels: {', '.join(equation_labels) if equation_labels else 'none'}\n"
        f"RST directives: {', '.join(directive_types) if directive_types else 'none'}\n"
        f"Inline math count: {inline_math_count}\n"
        f"Location: lines {citation_anchor.line_start}-{citation_anchor.line_end}\n\n"
        f"Content:\n{display_text}"
    )
