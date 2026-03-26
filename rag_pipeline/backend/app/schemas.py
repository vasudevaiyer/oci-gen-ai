from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

ChunkType = Literal[
    "narrative_chunk",
    "table_chunk",
    "row_chunk",
    "json_chunk",
    "code_chunk",
    "image_caption_chunk",
    "slide_chunk",
    "sheet_summary_chunk",
    "list_chunk",
    "note_chunk",
    "section_chunk",
    "procedure_chunk",
    "policy_clause_chunk",
    "reference_entry_chunk",
    "figure_explainer_chunk",
    "mixed_context_chunk",
]

DocumentArchetype = Literal[
    "regulatory",
    "procedural",
    "knowledge",
    "technical",
    "tabular",
    "reference",
    "presentation",
    "mixed_multimodal",
    "unknown",
]

BlockType = Literal[
    "heading",
    "paragraph",
    "list_item",
    "step",
    "table",
    "table_row",
    "figure",
    "caption",
    "note",
    "warning",
    "code",
    "quote",
    "metadata_block",
]


@dataclass(slots=True)
class CitationAnchor:
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    json_path: str | None = None
    rst_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    bbox: list[float] = field(default_factory=list)
    source_label: str = ""


@dataclass(slots=True)
class ImageContext:
    image_id: str
    image_path: str
    caption: str = ""
    alt_text: str = ""
    ocr_text: str = ""
    related_section_path: str = ""


@dataclass(slots=True)
class BlockRecord:
    block_id: str
    block_type: BlockType
    text: str
    order_index: int
    title: str = ""
    section_path: list[str] = field(default_factory=list)
    language_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    citation_anchor: CitationAnchor = field(default_factory=CitationAnchor)
    image_contexts: list[ImageContext] = field(default_factory=list)
    heading_level: int | None = None
    step_number: str = ""


@dataclass(slots=True)
class NormalizedSegment:
    segment_id: str
    segment_type: str
    text: str
    title: str = ""
    section_path: list[str] = field(default_factory=list)
    language_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    citation_anchor: CitationAnchor = field(default_factory=CitationAnchor)
    image_contexts: list[ImageContext] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedDocument:
    document_id: str
    source_path: str
    file_name: str
    file_type: str
    title: str
    checksum: str
    language_tags: list[str] = field(default_factory=list)
    document_archetype: DocumentArchetype = "unknown"
    blocks: list[BlockRecord] = field(default_factory=list)
    segments: list[NormalizedSegment] = field(default_factory=list)
    images: list[ImageContext] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parser_used: str = ""
    parser_confidence: float = 0.0
    extraction_quality: str = "standard"


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    source_path: str
    file_type: str
    document_archetype: DocumentArchetype
    chunk_type: ChunkType
    title: str
    section_path: list[str]
    chunk_index: int
    display_text: str
    embedding_text: str
    block_ids: list[str] = field(default_factory=list)
    block_types: list[str] = field(default_factory=list)
    language_tags: list[str] = field(default_factory=list)
    citation_anchor: CitationAnchor = field(default_factory=CitationAnchor)
    parser_used: str = ""
    parser_confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    image_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImageRecord:
    image_id: str
    document_id: str
    source_path: str
    image_path: str
    document_archetype: DocumentArchetype
    title: str
    caption_text: str
    related_section_path: list[str] = field(default_factory=list)
    related_chunk_id: str | None = None
    related_block_ids: list[str] = field(default_factory=list)
    related_chunk_ids: list[str] = field(default_factory=list)
    language_tags: list[str] = field(default_factory=list)
    citation_anchor: CitationAnchor = field(default_factory=CitationAnchor)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentRecord:
    document_id: str
    source_path: str
    file_name: str
    file_type: str
    checksum: str
    title: str
    status: str
    language_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class IngestResult:
    document: DocumentRecord
    chunks: list[ChunkRecord]
    images: list[ImageRecord]
    stats: dict[str, int]


class HealthResponse(BaseModel):
    status: str


class BootstrapResponse(BaseModel):
    status: str
    detail: str


class FolderImportRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    recurse: bool = True
    ingest: bool = True


class ReindexRequest(BaseModel):
    force: bool = False


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=6, ge=1, le=20)
    file_types: list[str] = Field(default_factory=list)
    include_images: bool = True


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2)
    top_k: int = Field(default=6, ge=1, le=20)
    file_types: list[str] = Field(default_factory=list)
    include_images: bool = True
    image_data_url: str | None = None


class UploadResponse(BaseModel):
    uploaded: list[str]
    ingested: list[str]
    skipped: list[str] = Field(default_factory=list)


class DocumentItem(BaseModel):
    document_id: str
    source_path: str
    file_name: str
    file_type: str
    title: str
    status: str
    language_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkMatch(BaseModel):
    chunk_id: str
    document_id: str
    source_path: str
    title: str
    section_path: str
    excerpt: str
    score: float
    chunk_type: str
    image_urls: list[str] = Field(default_factory=list)


class ImageMatch(BaseModel):
    image_id: str
    image_url: str
    caption_text: str
    source_path: str
    section_path: str
    score: float


class SearchResponse(BaseModel):
    chunks: list[ChunkMatch] = Field(default_factory=list)
    images: list[ImageMatch] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChunkMatch] = Field(default_factory=list)
    matched_images: list[ImageMatch] = Field(default_factory=list)
    model: str


class CorpusStatus(BaseModel):
    documents: int
    chunks: int
    images: int
    indexed_documents: int
    models: dict[str, str]


class DeleteResponse(BaseModel):
    status: str
    deleted_document_id: str


class DocumentDetail(BaseModel):
    document: DocumentItem
    chunk_count: int
    image_count: int



def new_document_id() -> str:
    return uuid4().hex



def new_chunk_id() -> str:
    return uuid4().hex



def new_image_id() -> str:
    return uuid4().hex



def safe_title_from_path(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    return stem or path.name
