from __future__ import annotations

from .base import blocks_to_chunks, classify_document_archetype, detect_languages, materialize_blocks, normalize_text
from ..schemas import ChunkRecord, CitationAnchor, ImageRecord, NormalizedDocument, new_chunk_id


def chunk_xlsx_document(document: NormalizedDocument, max_words: int, overlap_words: int) -> tuple[list[ChunkRecord], list[ImageRecord]]:
    chunking_hints = document.metadata.get("chunking_hints") or {}
    sheets = chunking_hints.get("sheets") or []
    if not sheets:
        document.metadata = {
            **document.metadata,
            "chunking_strategy": "generic_blocks",
        }
        return blocks_to_chunks(document, max_words, overlap_words)

    blocks = materialize_blocks(document)
    block_by_id = {block.block_id: block for block in blocks}
    document.blocks = blocks
    document.document_archetype = classify_document_archetype(document)
    document.metadata = {
        **document.metadata,
        "document_archetype": document.document_archetype,
        "block_count": len(blocks),
        "chunking_strategy": "xlsx_sheet_window",
        "document_structure": chunking_hints.get("structure", "workbook_sheets"),
        "structure_sheet_count": len(sheets),
    }
    document.metadata.pop("chunking_hints", None)

    chunks: list[ChunkRecord] = []
    chunk_index = 0

    for sheet in sheets:
        sheet_name = str(sheet.get("sheet_name") or "Sheet")
        for region in sheet.get("regions") or []:
            section_path = list(region.get("section_path") or [document.title, sheet_name])
            region_title = str(region.get("region_title") or section_path[-1])
            region_type = str(region.get("region_type") or "table")
            headers = [str(value) for value in region.get("headers") or [] if str(value).strip()]
            summary_block = block_by_id.get(region.get("summary_block_id"))
            row_blocks = [block_by_id[block_id] for block_id in region.get("row_block_ids") or [] if block_id in block_by_id]
            summary_text = normalize_text(summary_block.text if summary_block else "")

            if summary_text:
                chunk_id = new_chunk_id()
                anchor = summary_block.citation_anchor if summary_block else CitationAnchor(sheet_name=sheet_name, source_label=sheet_name)
                chunk_type = "table_chunk" if region_type == "table" else "reference_entry_chunk"
                summary_block_id = summary_block.block_id if summary_block else ""
                chunks.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        source_path=document.source_path,
                        file_type=document.file_type,
                        document_archetype=document.document_archetype,
                        chunk_type=chunk_type,
                        title=region_title,
                        section_path=section_path,
                        chunk_index=chunk_index,
                        display_text=summary_text,
                        embedding_text=_build_xlsx_embedding_text(
                            document=document,
                            section_path=section_path,
                            chunk_type=chunk_type,
                            display_text=summary_text,
                            sheet_name=sheet_name,
                            region_type=region_type,
                            headers=headers,
                            row_range=(region.get("row_start"), region.get("row_end")),
                        ),
                        block_ids=[summary_block_id] if summary_block_id else [],
                        block_types=[summary_block.block_type] if summary_block else [],
                        language_tags=detect_languages([summary_text]) or document.language_tags,
                        citation_anchor=anchor,
                        parser_used=document.parser_used,
                        parser_confidence=document.parser_confidence,
                        metadata={
                            **document.metadata,
                            "sheet_name": sheet_name,
                            "region_type": region_type,
                            "headers": headers,
                            "row_start": region.get("row_start"),
                            "row_end": region.get("row_end"),
                            "block_role": "region_summary",
                        },
                    )
                )
                chunk_index += 1

            if region_type == "key_value":
                continue

            for window in _window_rows(row_blocks, max_words=max_words, overlap_words=overlap_words):
                display_text = _build_row_window_text(headers, window)
                if not display_text:
                    continue
                row_start = min(_row_index(block) for block in window)
                row_end = max(_row_index(block) for block in window)
                chunk_id = new_chunk_id()
                chunks.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        source_path=document.source_path,
                        file_type=document.file_type,
                        document_archetype=document.document_archetype,
                        chunk_type="row_chunk" if region_type == "table" else "reference_entry_chunk",
                        title=region_title,
                        section_path=section_path,
                        chunk_index=chunk_index,
                        display_text=display_text,
                        embedding_text=_build_xlsx_embedding_text(
                            document=document,
                            section_path=section_path,
                            chunk_type="row_chunk" if region_type == "table" else "reference_entry_chunk",
                            display_text=display_text,
                            sheet_name=sheet_name,
                            region_type=region_type,
                            headers=headers,
                            row_range=(row_start, row_end),
                        ),
                        block_ids=[block.block_id for block in window],
                        block_types=[block.block_type for block in window],
                        language_tags=detect_languages([display_text]) or document.language_tags,
                        citation_anchor=CitationAnchor(
                            sheet_name=sheet_name,
                            line_start=row_start,
                            line_end=row_end,
                            source_label=f"{sheet_name}:{row_start}-{row_end}",
                        ),
                        parser_used=document.parser_used,
                        parser_confidence=document.parser_confidence,
                        metadata={
                            **document.metadata,
                            "sheet_name": sheet_name,
                            "region_type": region_type,
                            "headers": headers,
                            "row_start": row_start,
                            "row_end": row_end,
                            "block_role": "row_window",
                        },
                    )
                )
                chunk_index += 1

    return chunks, []


def _window_rows(blocks, *, max_words: int, overlap_words: int):
    windows = []
    current = []
    current_words = 0
    for block in blocks:
        block_words = len((block.text or "").split())
        if current and current_words + block_words > max_words:
            windows.append(current[:])
            if overlap_words > 0:
                overlap = []
                carry = 0
                for item in reversed(current):
                    overlap.insert(0, item)
                    carry += len((item.text or "").split())
                    if carry >= overlap_words:
                        break
                current = overlap[:]
                current_words = sum(len((item.text or "").split()) for item in current)
            else:
                current = []
                current_words = 0
        current.append(block)
        current_words += block_words
    if current:
        windows.append(current)
    return windows


def _build_row_window_text(headers: list[str], window) -> str:
    row_text = normalize_text("\n".join(block.text for block in window if (block.text or "").strip()))
    parts = []
    if headers:
        parts.append(f"Headers: {', '.join(headers)}")
    if row_text:
        parts.append("Rows:\n" + row_text)
    return normalize_text("\n\n".join(parts))


def _row_index(block) -> int:
    return int(block.metadata.get("row_index") or block.citation_anchor.line_start or 0)


def _build_xlsx_embedding_text(
    *,
    document: NormalizedDocument,
    section_path: list[str],
    chunk_type: str,
    display_text: str,
    sheet_name: str,
    region_type: str,
    headers: list[str],
    row_range: tuple[object, object],
) -> str:
    row_start, row_end = row_range
    if row_start and row_end:
        row_range_text = f"{row_start}-{row_end}"
    else:
        row_range_text = "n/a"
    return (
        f"Document title: {document.title}\n"
        f"Archetype: {document.document_archetype}\n"
        f"Section path: {' > '.join(section_path)}\n"
        f"Content type: {chunk_type}\n"
        f"Sheet name: {sheet_name}\n"
        f"Region type: {region_type}\n"
        f"Headers: {', '.join(headers) if headers else 'none'}\n"
        f"Row range: {row_range_text}\n\n"
        f"Content:\n{display_text}"
    )
