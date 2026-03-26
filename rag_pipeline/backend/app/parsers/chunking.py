from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .base import blocks_to_chunks
from .pdf_chunking import chunk_pdf_document
from .pptx_chunking import chunk_pptx_document
from .rst_chunking import chunk_rst_document
from .xlsx_chunking import chunk_xlsx_document
from ..schemas import ChunkRecord, ImageRecord, NormalizedDocument

ChunkBuilder = Callable[[NormalizedDocument, int, int], tuple[list[ChunkRecord], list[ImageRecord]]]


@dataclass(frozen=True)
class ChunkingStrategy:
    name: str
    supports: Callable[[NormalizedDocument], bool]
    builder: ChunkBuilder


STRATEGIES: tuple[ChunkingStrategy, ...] = (
    ChunkingStrategy(
        name="pdf_section_window",
        supports=lambda document: document.file_type == "pdf"
        or (document.metadata.get("chunking_hints") or {}).get("preferred_strategy") == "pdf_section_window",
        builder=chunk_pdf_document,
    ),
    ChunkingStrategy(
        name="slide_window",
        supports=lambda document: document.file_type in {"ppt", "pptx"}
        or (document.metadata.get("chunking_hints") or {}).get("preferred_strategy") == "slide_window",
        builder=chunk_pptx_document,
    ),
    ChunkingStrategy(
        name="rst_section_window",
        supports=lambda document: document.file_type == "rst"
        or (document.metadata.get("chunking_hints") or {}).get("preferred_strategy") == "rst_section_window",
        builder=chunk_rst_document,
    ),
    ChunkingStrategy(
        name="xlsx_sheet_window",
        supports=lambda document: document.file_type in {"xls", "xlsx"}
        or (document.metadata.get("chunking_hints") or {}).get("preferred_strategy") == "xlsx_sheet_window",
        builder=chunk_xlsx_document,
    ),
    ChunkingStrategy(
        name="generic_blocks",
        supports=lambda document: True,
        builder=blocks_to_chunks,
    ),
)


def choose_chunking_strategy(document: NormalizedDocument) -> ChunkingStrategy:
    preferred = (document.metadata.get("chunking_hints") or {}).get("preferred_strategy")
    if preferred:
        for strategy in STRATEGIES:
            if strategy.name == preferred and strategy.supports(document):
                return strategy
    for strategy in STRATEGIES:
        if strategy.supports(document):
            return strategy
    return STRATEGIES[-1]


def document_to_chunks(document: NormalizedDocument, max_words: int, overlap_words: int) -> tuple[list[ChunkRecord], list[ImageRecord]]:
    strategy = choose_chunking_strategy(document)
    document.metadata = {
        **document.metadata,
        "chunking_strategy": strategy.name,
    }
    return strategy.builder(document, max_words, overlap_words)
