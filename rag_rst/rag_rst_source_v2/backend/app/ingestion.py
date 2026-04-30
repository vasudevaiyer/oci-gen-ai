from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

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
        self._last_stats: dict[str, Any] = {}

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_stats(self) -> dict[str, Any]:
        return self._last_stats

    def rebuild_index(self) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return self._last_stats
        self._running = True
        try:
            self._last_stats = {"phase": "initializing"}
            self.store.initialize_schema()
            self.store.reset_corpus()
            self._last_stats = {"phase": "parsing"}
            chunks, images, stats = parse_corpus(self.settings)
            self._last_stats = {
                **stats,
                "phase": "parsed",
                "parsed_chunks": len(chunks),
                "parsed_images": len(images),
            }
            self._index_chunks(chunks, stats)
            valid_images = []
            missing_images = 0
            unsupported_images = 0
            invalid_image_paths = 0
            for image in images:
                try:
                    image_path = Path(image.image_path)
                    resolved_path = self.settings.data_dir / image_path
                    if image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
                        unsupported_images += 1
                        continue
                    if not resolved_path.exists():
                        missing_images += 1
                        continue
                    valid_images.append(image)
                except OSError:
                    invalid_image_paths += 1

            stats["valid_images"] = len(valid_images)
            stats["missing_images"] = missing_images
            stats["unsupported_images"] = unsupported_images
            stats["invalid_image_paths"] = invalid_image_paths
            self._index_images(valid_images, chunks, stats)
            self._last_stats = {
                **stats,
                **self.store.corpus_counts(),
                "phase": "complete",
                "parsed_chunks": len(chunks),
                "parsed_images": len(valid_images),
            }
            return self._last_stats
        finally:
            self._running = False
            self._lock.release()

    def _index_chunks(self, chunks: list, stats: dict[str, int]) -> None:
        total = len(chunks)
        batch_size = max(1, self.settings.ingestion_chunk_batch_size)
        inserted = 0
        self._last_stats = {
            **stats,
            "phase": "embedding_text",
            "parsed_chunks": total,
            "embedded_chunks": inserted,
            "parsed_images": 0,
        }

        for start in range(0, total, batch_size):
            batch = chunks[start : start + batch_size]
            embeddings = self.genai.embed_texts(
                [chunk.retrieval_text for chunk in batch],
                input_type="SEARCH_DOCUMENT",
            )
            self.store.append_chunks(batch, embeddings)
            inserted += len(batch)
            self._last_stats = {
                **stats,
                **self.store.corpus_counts(),
                "phase": "embedding_text",
                "parsed_chunks": total,
                "embedded_chunks": inserted,
                "parsed_images": 0,
            }

    def _index_images(self, images: list, chunks: list, stats: dict[str, int]) -> None:
        total = len(images)
        batch_size = max(1, self.settings.ingestion_image_batch_size)
        inserted = 0
        self._last_stats = {
            **stats,
            **self.store.corpus_counts(),
            "phase": "embedding_images",
            "parsed_chunks": len(chunks),
            "embedded_chunks": len(chunks),
            "parsed_images": total,
            "embedded_images": inserted,
        }

        for start in range(0, total, batch_size):
            batch = images[start : start + batch_size]
            data_urls = [
                self.genai.image_file_to_data_url(self.settings.data_dir / Path(image.image_path))
                for image in batch
            ]
            embeddings = self.genai.embed_image_data_urls(data_urls) if batch else []
            self.store.append_images(batch, embeddings)
            inserted += len(batch)
            self._last_stats = {
                **stats,
                **self.store.corpus_counts(),
                "phase": "embedding_images",
                "parsed_chunks": len(chunks),
                "embedded_chunks": len(chunks),
                "parsed_images": total,
                "embedded_images": inserted,
            }
