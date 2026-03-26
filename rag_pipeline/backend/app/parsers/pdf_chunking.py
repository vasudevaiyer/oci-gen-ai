from __future__ import annotations

from .base import blocks_to_chunks, classify_document_archetype, detect_languages, materialize_blocks, normalize_text
from ..schemas import ChunkRecord, CitationAnchor, ImageRecord, NormalizedDocument, new_chunk_id


def chunk_pdf_document(document: NormalizedDocument, max_words: int, overlap_words: int) -> tuple[list[ChunkRecord], list[ImageRecord]]:
    chunking_hints = document.metadata.get("chunking_hints") or {}
    pages = chunking_hints.get("pages") or []
    if not pages:
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
        "chunking_strategy": "pdf_section_window",
        "document_structure": chunking_hints.get("structure", "paged_sections"),
        "structure_page_count": len(pages),
    }
    document.metadata.pop("chunking_hints", None)

    chunks: list[ChunkRecord] = []
    images: list[ImageRecord] = []
    chunk_index = 0
    emitted_image_paths: set[str] = set()

    for page in pages:
        page_number = int(page["page_number"])
        for section in page.get("sections", []):
            section_path = list(section.get("section_path") or [document.title, f"Page {page_number}"])
            section_block_ids = list(section.get("block_ids") or [])
            section_blocks = _section_blocks(blocks, section_path, section_block_ids)
            if not section_blocks:
                continue
            for window in _window_blocks(section_blocks, max_words=max_words, overlap_words=overlap_words):
                display_text = normalize_text("\n\n".join(block.text for block in window if block.text.strip()))
                if not display_text and not any(block.image_contexts for block in window):
                    continue
                block_ids = [block.block_id for block in window]
                block_types = [block.block_type for block in window]
                image_refs = _image_refs(window)
                citation_anchor = CitationAnchor(page_number=page_number, source_label=f"page {page_number}")
                chunk_type = _chunk_type_for_window(document.document_archetype, block_types)
                language_tags = detect_languages([display_text]) or document.language_tags
                layout_hints = _layout_hints(window)
                metadata = {
                    **document.metadata,
                    "page_number": page_number,
                    "section_title": section_path[-1],
                    "layout_hints": layout_hints,
                    "block_ids": block_ids,
                    "block_types": block_types,
                }
                chunk_id = new_chunk_id()
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
                        embedding_text=_build_pdf_embedding_text(
                            document=document,
                            section_path=section_path,
                            display_text=display_text,
                            chunk_type=chunk_type,
                            page_number=page_number,
                            layout_hints=layout_hints,
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

                for image_context in _collect_images(window):
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
                                "page_number": page_number,
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


def _section_blocks(blocks, section_path: list[str], section_block_ids: list[str]):
    section_id_set = set(section_block_ids)
    ordered = [
        block
        for block in blocks
        if block.block_id in section_id_set or (block.block_type == "heading" and block.section_path == section_path)
    ]
    ordered.sort(key=lambda block: block.order_index)
    return ordered


def _window_blocks(blocks, *, max_words: int, overlap_words: int):
    windows = []
    current = []
    current_words = 0
    for block in blocks:
        block_words = len(block.text.split()) if block.text else 0
        if current and current_words + block_words > max_words:
            windows.append(current[:])
            if overlap_words > 0:
                overlap = []
                carry = 0
                for item in reversed(current):
                    overlap.insert(0, item)
                    carry += len(item.text.split()) if item.text else 0
                    if carry >= overlap_words:
                        break
                current = overlap[:]
                current_words = sum(len(item.text.split()) if item.text else 0 for item in current)
            else:
                current = []
                current_words = 0
        current.append(block)
        current_words += block_words
    if current:
        windows.append(current)
    return windows


def _layout_hints(blocks) -> list[str]:
    hints: list[str] = []
    for block in blocks:
        layout_hint = str(block.metadata.get("layout_hint", "")).strip()
        if layout_hint and layout_hint not in hints:
            hints.append(layout_hint)
    return hints


def _collect_images(blocks):
    images = []
    seen = set()
    for block in blocks:
        for image_context in block.image_contexts:
            key = image_context.image_id or image_context.image_path
            if key in seen:
                continue
            seen.add(key)
            images.append(image_context)
    return images


def _image_refs(blocks) -> list[str]:
    return [image.image_path for image in _collect_images(blocks)]


def _chunk_type_for_window(archetype: str, block_types: list[str]) -> str:
    block_type_set = set(block_types)
    if {"figure", "caption"} & block_type_set:
        return "figure_explainer_chunk" if len(block_type_set) > 1 else "image_caption_chunk"
    if "table" in block_type_set:
        return "table_chunk"
    if archetype == "procedural" and block_type_set & {"step", "list_item"}:
        return "procedure_chunk"
    if archetype == "regulatory":
        return "policy_clause_chunk"
    return "section_chunk"


def _build_pdf_embedding_text(
    *,
    document: NormalizedDocument,
    section_path: list[str],
    display_text: str,
    chunk_type: str,
    page_number: int,
    layout_hints: list[str],
) -> str:
    return (
        f"Document title: {document.title}\n"
        f"Archetype: {document.document_archetype}\n"
        f"Section path: {' > '.join(section_path)}\n"
        f"Content type: {chunk_type}\n"
        f"Page number: {page_number}\n"
        f"Layout hints: {', '.join(layout_hints) if layout_hints else 'none'}\n\n"
        f"Content:\n{display_text}"
    )
