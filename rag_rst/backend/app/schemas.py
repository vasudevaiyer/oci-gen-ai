from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass(slots=True)
class ChunkRecord:
    source_path: str
    doc_code: str
    title: str
    section_path: str
    chunk_index: int
    content: str
    retrieval_text: str
    anchors: list[str] = field(default_factory=list)
    image_refs: list[str] = field(default_factory=list)
    equation_labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImageRecord:
    image_path: str
    doc_code: str
    title: str
    caption_text: str
    related_source_path: str
    related_section_path: str
    related_chunk_index: int


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = Field(default=6, ge=2, le=12)
    image_data_url: str | None = None
    session_id: str | None = Field(default=None, max_length=128)


class SourceItem(BaseModel):
    source_path: str
    title: str
    section_path: str
    score: float
    excerpt: str
    image_urls: list[str] = Field(default_factory=list)


class ImageMatch(BaseModel):
    image_url: str
    caption_text: str
    score: float
    source_path: str
    section_path: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    matched_images: list[ImageMatch] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    model: str


class IngestRequest(BaseModel):
    rebuild: bool = True


class IngestResponse(BaseModel):
    status: str
    detail: str


class CorpusStatus(BaseModel):
    chunks: int
    images: int
    documents: int
    ingest_running: bool
    models: dict[str, str]
    stats: dict[str, Any] = Field(default_factory=dict)


class AnalyticsTopQuestion(BaseModel):
    question: str
    normalized_question: str
    count: int
    last_asked_at: str


class AnalyticsTopSource(BaseModel):
    source_path: str
    section_path: str
    count: int


class AnalyticsDailyCount(BaseModel):
    day: str
    count: int


class AnalyticsSummary(BaseModel):
    total_questions: int
    successful_questions: int
    failed_questions: int
    unique_questions: int
    questions_with_images: int
    avg_latency_ms: float
    top_questions: list[AnalyticsTopQuestion] = Field(default_factory=list)
    top_sources: list[AnalyticsTopSource] = Field(default_factory=list)
    daily_counts: list[AnalyticsDailyCount] = Field(default_factory=list)
