from __future__ import annotations

from pathlib import Path
from threading import Lock

from .config import Settings
from .db import OracleVectorStore
from .oci_services import OciGenAiService
from .rst_parser import parse_corpus

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


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
            valid_images = [
                image
                for image in images
                if (self.settings.data_dir / Path(image.image_path)).exists()
                and Path(image.image_path).suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
            ]
            image_data_urls = [
                self.genai.image_file_to_data_url(self.settings.data_dir / Path(image.image_path))
                for image in valid_images
            ]
            image_embeddings = self.genai.embed_image_data_urls(image_data_urls) if valid_images else []
            self.store.rebuild(chunks, chunk_embeddings, valid_images, image_embeddings)
            self._last_stats = {**stats, **self.store.corpus_counts()}
            return self._last_stats
        finally:
            self._running = False
            self._lock.release()
