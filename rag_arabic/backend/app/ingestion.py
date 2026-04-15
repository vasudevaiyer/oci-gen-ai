from __future__ import annotations

from threading import Lock

from .config import Settings
from .db import OracleVectorStore
from .oci_services import OciGenAiService
from .pdf_parser import parse_corpus


class IngestionManager:
    def __init__(self, settings: Settings, store: OracleVectorStore, genai: OciGenAiService) -> None:
        self.settings = settings
        self.store = store
        self.genai = genai
        self._lock = Lock()
        self._running = False
        self._last_stats: dict[str, int] = {}

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_stats(self) -> dict[str, int]:
        return self._last_stats

    def rebuild_index(self) -> dict[str, int]:
        if not self._lock.acquire(blocking=False):
            return self._last_stats
        self._running = True
        try:
            self.store.initialize_schema()
            chunks, images, stats = parse_corpus(self.settings)
            chunk_embeddings = self.genai.embed_texts(
                [chunk.retrieval_text for chunk in chunks],
                input_type="SEARCH_DOCUMENT",
            )
            self.store.rebuild(chunks, chunk_embeddings, images, [])
            self._last_stats = {**stats, **self.store.corpus_counts()}
            return self._last_stats
        finally:
            self._running = False
            self._lock.release()
