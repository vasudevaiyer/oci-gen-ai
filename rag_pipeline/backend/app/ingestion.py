from __future__ import annotations

import hashlib
import shutil
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Iterable

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover
    Image = None
    UnidentifiedImageError = Exception

from .config import Settings
from .db import OracleVectorStore
from .parsers import ParserRouter
from .parsers.chunking import document_to_chunks
from .schemas import DocumentRecord, IngestResult
from .services.cohere_service import OciGenAiService


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


class IngestionManager:
    def __init__(self, settings: Settings, store: OracleVectorStore, genai: OciGenAiService) -> None:
        self.settings = settings
        self.store = store
        self.genai = genai
        self.router = ParserRouter(settings, genai=genai)
        self._lock = Lock()
        self._running = False
        self._last_stats: dict[str, int] = {}

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_stats(self) -> dict[str, int]:
        return self._last_stats

    def bootstrap(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.settings.extracted_images_dir.mkdir(parents=True, exist_ok=True)
        self.store.initialize_schema()

    def ingest_path(self, path: Path, *, preserve_name: bool = True) -> IngestResult:
        self.bootstrap()
        target_path = path if str(path).startswith(str(self.settings.uploads_dir)) else self._copy_into_uploads(path, preserve_name=preserve_name)
        relative_path = str(target_path.relative_to(self.settings.root_dir))
        document = self.router.parse(target_path, relative_path)
        document.language_tags = document.language_tags or ["unknown"]
        self._prune_document_images(document)
        self._hydrate_image_captions(document)

        chunks, images = document_to_chunks(document, self.settings.max_chunk_words, self.settings.chunk_overlap_words)
        chunk_embeddings = self.genai.embed_texts([chunk.embedding_text for chunk in chunks], input_type="SEARCH_DOCUMENT")
        image_assets = [
            image
            for image in images
            if (self.settings.root_dir / image.image_path).exists()
            and (self.settings.root_dir / image.image_path).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ]
        image_embeddings = self.genai.embed_image_data_urls(
            [self.genai.image_file_to_data_url(self.settings.root_dir / image.image_path) for image in image_assets]
        )
        if len(image_assets) != len(images):
            images = image_assets

        record = DocumentRecord(
            document_id=document.document_id,
            source_path=document.source_path,
            file_name=document.file_name,
            file_type=document.file_type,
            checksum=document.checksum,
            title=document.title,
            status="indexed",
            language_tags=document.language_tags,
            metadata={
                **document.metadata,
                "parser_used": document.parser_used,
                "parser_confidence": document.parser_confidence,
                "extraction_quality": document.extraction_quality,
                "caption_model": self.settings.vision_model_id,
                "embedding_model": self.settings.embedding_model_id,
            },
        )
        self.store.replace_document_content(
            record,
            chunks,
            chunk_embeddings,
            images,
            image_embeddings,
            embedding_model_id=self.settings.embedding_model_id,
        )
        stats = {"documents": 1, "chunks": len(chunks), "images": len(images)}
        self._last_stats = stats
        return IngestResult(document=record, chunks=chunks, images=images, stats=stats)

    def _prune_document_images(self, document) -> None:
        thresholds = {
            "min_width": max(int(getattr(self.settings, "min_indexed_image_width", 120)), 1),
            "min_height": max(int(getattr(self.settings, "min_indexed_image_height", 48)), 1),
            "min_area": max(int(getattr(self.settings, "min_indexed_image_area", 12000)), 1),
            "repeat_threshold": max(int(getattr(self.settings, "repeated_image_occurrence_threshold", 5)), 2),
            "repeat_max_area": max(int(getattr(self.settings, "repeated_image_max_area", 90000)), 1),
        }

        image_infos: list[dict[str, object]] = []
        hash_counts: Counter[str] = Counter()
        unique_images = list(self._iter_unique_images(document))

        for image in unique_images:
            image_path = self.settings.root_dir / image.image_path
            if not image_path.exists() or image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                continue
            width, height = self._image_dimensions(image_path)
            if width <= 0 or height <= 0:
                continue
            digest = self._file_digest(image_path)
            area = width * height
            image_infos.append(
                {
                    "image": image,
                    "path": image_path,
                    "width": width,
                    "height": height,
                    "area": area,
                    "digest": digest,
                }
            )
            if digest:
                hash_counts[digest] += 1

        kept_ids: set[str] = set()
        removed_paths: list[Path] = []
        removed_reasons: Counter[str] = Counter()

        for info in image_infos:
            image = info["image"]
            width = int(info["width"])
            height = int(info["height"])
            area = int(info["area"])
            digest = str(info["digest"] or "")
            duplicate_count = hash_counts.get(digest, 1) if digest else 1
            reason = self._image_drop_reason(
                width=width,
                height=height,
                area=area,
                duplicate_count=duplicate_count,
                thresholds=thresholds,
            )
            if reason is None:
                kept_ids.add(image.image_id)
                continue
            removed_reasons[reason] += 1
            removed_paths.append(info["path"])

        if len(kept_ids) == len(unique_images):
            document.metadata = {
                **document.metadata,
                "image_filtering": {
                    "retained": len(unique_images),
                    "removed": 0,
                    "removed_reasons": {},
                },
            }
            return

        for image_path in removed_paths:
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                pass

        document.images = [image for image in document.images if image.image_id in kept_ids]
        document.blocks = [
            block
            for block in self._pruned_blocks(document.blocks, kept_ids)
            if block.block_type == "heading" or block.text.strip() or block.image_contexts
        ]
        document.segments = [
            segment
            for segment in self._pruned_segments(document.segments, kept_ids)
            if segment.text.strip() or segment.image_contexts
        ]
        document.metadata = {
            **document.metadata,
            "image_filtering": {
                "retained": len(document.images),
                "removed": len(unique_images) - len(document.images),
                "removed_reasons": dict(removed_reasons),
            },
        }
        if document.metadata["image_filtering"]["removed"] > 0:
            document.extraction_quality = "filtered"

    def _pruned_blocks(self, blocks, kept_ids: set[str]):
        for block in blocks:
            block.image_contexts = [image for image in block.image_contexts if image.image_id in kept_ids]
            yield block

    def _pruned_segments(self, segments, kept_ids: set[str]):
        for segment in segments:
            segment.image_contexts = [image for image in segment.image_contexts if image.image_id in kept_ids]
            yield segment

    def _image_dimensions(self, image_path: Path) -> tuple[int, int]:
        if Image is None:
            return (0, 0)
        try:
            with Image.open(image_path) as image:
                return image.size
        except (OSError, UnidentifiedImageError):
            return (0, 0)

    def _file_digest(self, image_path: Path) -> str:
        try:
            return hashlib.sha1(image_path.read_bytes()).hexdigest()
        except OSError:
            return ""

    def _image_drop_reason(self, *, width: int, height: int, area: int, duplicate_count: int, thresholds: dict[str, int]) -> str | None:
        if width < thresholds["min_width"] or height < thresholds["min_height"] or area < thresholds["min_area"]:
            return "too_small"
        if duplicate_count >= thresholds["repeat_threshold"] and area <= thresholds["repeat_max_area"]:
            return "repeated_small_asset"
        return None

    def _hydrate_image_captions(self, document) -> None:
        caption_candidates: list[tuple[object, Path]] = []
        seen_ids: set[str] = set()
        for image in self._iter_unique_images(document):
            fallback_caption = self._fallback_image_caption(image)
            if not image.caption:
                image.caption = fallback_caption
            image_path = self.settings.root_dir / image.image_path
            if image_path.exists() and image_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and image.image_id not in seen_ids:
                seen_ids.add(image.image_id)
                caption_candidates.append((image, image_path))

        eager_limit = max(self.settings.max_eager_image_captions, 0)
        for image, image_path in caption_candidates[:eager_limit]:
            try:
                caption = self.genai.caption_image(image_path, context_hint=image.related_section_path)
            except Exception:
                continue
            if caption.strip():
                image.caption = caption.strip()

    def _iter_unique_images(self, document) -> Iterable:
        seen_ids: set[str] = set()
        for image in document.images:
            if image.image_id in seen_ids:
                continue
            seen_ids.add(image.image_id)
            yield image
        for segment in document.segments:
            for image in segment.image_contexts:
                if image.image_id in seen_ids:
                    continue
                seen_ids.add(image.image_id)
                yield image

    def _fallback_image_caption(self, image) -> str:
        section_hint = (image.related_section_path or "").strip()
        if section_hint:
            return f"Image from {section_hint}"
        return "Document image"

    def ingest_folder(self, folder_path: Path, *, recurse: bool = True) -> dict[str, list[str]]:
        uploaded: list[str] = []
        ingested: list[str] = []
        skipped: list[str] = []
        mirrored_root = self._mirror_folder_into_uploads(folder_path, recurse=recurse)
        iterator: Iterable[Path] = mirrored_root.rglob("*") if recurse else mirrored_root.glob("*")
        for path in iterator:
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.settings.supported_extensions:
                continue
            result = self.ingest_path(path)
            uploaded.append(result.document.source_path)
            ingested.append(result.document.document_id)
        original_iterator: Iterable[Path] = folder_path.rglob("*") if recurse else folder_path.glob("*")
        for path in original_iterator:
            if path.is_file() and path.suffix.lower() not in self.settings.supported_extensions:
                skipped.append(str(path))
        return {"uploaded": uploaded, "ingested": ingested, "skipped": skipped}

    def rebuild_all(self) -> dict[str, int]:
        if not self._lock.acquire(blocking=False):
            return self._last_stats
        self._running = True
        try:
            self.bootstrap()
            stats = {"documents": 0, "chunks": 0, "images": 0}
            for path in sorted(self.settings.uploads_dir.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in self.settings.supported_extensions:
                    continue
                result = self.ingest_path(path)
                stats["documents"] += 1
                stats["chunks"] += result.stats["chunks"]
                stats["images"] += result.stats["images"]
            self._last_stats = stats
            return stats
        finally:
            self._running = False
            self._lock.release()

    def delete_document_assets(self, source_path: str) -> None:
        target = self.settings.root_dir / source_path
        if target.exists():
            target.unlink()

    def _copy_into_uploads(self, source_path: Path, *, preserve_name: bool) -> Path:
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        destination = self.settings.uploads_dir / source_path.name if preserve_name else self.settings.uploads_dir / f"{source_path.stem}-{source_path.stat().st_mtime_ns}{source_path.suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)
        return destination

    def _mirror_folder_into_uploads(self, folder_path: Path, *, recurse: bool) -> Path:
        destination_root = self.settings.uploads_dir / folder_path.name
        destination_root.mkdir(parents=True, exist_ok=True)
        iterator: Iterable[Path] = folder_path.rglob("*") if recurse else folder_path.glob("*")
        for source_path in iterator:
            if source_path.is_dir():
                continue
            relative_path = source_path.relative_to(folder_path)
            destination = destination_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
        return destination_root
