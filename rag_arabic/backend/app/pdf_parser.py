from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader

from .config import Settings
from .schemas import ChunkRecord, ImageRecord


CHAPTER_RE = re.compile(r"^الفصل\s+(.+)$")
ARTICLE_NUMBER_RE = re.compile(r"(?:المادة\s*([0-9٠-٩]+)|([0-9٠-٩]+)\s*المادة)")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
HEADER_TEXT = "العمل عن بعد سياسة"
TOC_TEXT = "جدول المحتويات"


def parse_corpus(settings: Settings) -> tuple[list[ChunkRecord], list[ImageRecord], dict[str, int]]:
    chunks: list[ChunkRecord] = []
    stats = defaultdict(int)

    for path in sorted(settings.data_dir.rglob("*.pdf")):
        doc_chunks, doc_stats = parse_pdf_file(path, settings)
        chunks.extend(doc_chunks)
        for key, value in doc_stats.items():
            stats[key] += value

    stats["documents"] = len({chunk.source_path for chunk in chunks})
    return chunks, [], dict(stats)


def parse_pdf_file(path: Path, settings: Settings) -> tuple[list[ChunkRecord], dict[str, int]]:
    reader = PdfReader(str(path))
    pages = [_extract_page_text(page) for page in reader.pages]
    page_lines = [_clean_page_lines(text) for text in pages]

    stats = defaultdict(int)
    stats["pages"] = len(page_lines)
    path_rel = str(path.relative_to(settings.data_dir))
    doc_code = path.stem
    document_title = HEADER_TEXT
    current_chapter = ""
    current_article = ""
    current_page = 1
    article_lines: list[str] = []
    article_start_page = 1
    chunks: list[ChunkRecord] = []
    next_chunk_index = 0
    active_section = False

    def flush_article() -> None:
        nonlocal article_lines, article_start_page, next_chunk_index
        if not article_lines:
            return
        blocks = _to_blocks(article_lines)
        if not blocks:
            article_lines = []
            return
        section_path = f"{current_chapter} > {current_article} > الصفحة {article_start_page}"
        for block_lines in _window_blocks(blocks, settings.max_chunk_words, settings.chunk_overlap_words):
            content = _normalize_spacing("\n".join(block_lines))
            if len(content.split()) < 15:
                continue
            retrieval_text = (
                f"عنوان الوثيقة: {document_title}\n"
                f"القسم: {current_chapter}\n"
                f"المادة: {current_article}\n"
                f"الصفحة: {article_start_page}\n\n"
                f"{content}"
            )
            chunks.append(
                ChunkRecord(
                    source_path=path_rel,
                    doc_code=doc_code,
                    title=document_title,
                    section_path=section_path,
                    chunk_index=next_chunk_index,
                    content=content,
                    retrieval_text=retrieval_text,
                )
            )
            next_chunk_index += 1
            stats["chunks"] += 1
        article_lines = []

    for page_number, lines in enumerate(page_lines, start=1):
        if _is_toc_page(lines):
            continue
        for line in lines:
            chapter = _parse_chapter(line)
            if chapter:
                flush_article()
                current_chapter = chapter
                current_article = chapter
                article_start_page = page_number
                active_section = True
                continue

            article = _parse_article(line)
            if article:
                flush_article()
                current_article = article
                article_start_page = page_number
                active_section = True
                continue

            if not active_section:
                continue
            if not line.strip():
                continue
            article_lines.append(line)
            current_page = page_number

    article_start_page = current_page if article_lines else article_start_page
    flush_article()
    return chunks, dict(stats)


def _extract_page_text(page) -> str:
    raw = page.extract_text() or ""
    normalized = unicodedata.normalize("NFKC", raw)
    normalized = normalized.replace("\u200f", "").replace("\u200e", "")
    return normalized


def _clean_page_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = _normalize_spacing(raw_line)
        if not line:
            continue
        if line == HEADER_TEXT:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        lines.append(line)
    return lines


def _normalize_spacing(text: str) -> str:
    text = text.translate(ARABIC_DIGITS)
    text = _normalize_bidi_numbers(text)
    text = re.sub(r"[ \t]+", " ", text.strip())
    text = re.sub(r"\s+([،؛:.])", r"\1", text)
    text = re.sub(r"([(:])\s+", r"\1", text)
    text = re.sub(r"\s+([)])", r"\1", text)
    return text


def _normalize_bidi_numbers(text: str) -> str:
    # PDF extraction can reverse short numeric tokens in RTL text. Common patterns in this
    # corpus include ".03" for "30", "٪05" for "50٪", and dotted list markers such as
    # ".10" for "10." or ".41" for "14.". Normalize those forms before chunking.
    def normalize_digits(digits: str) -> str:
        if len(digits) > 1 and digits.endswith("0"):
            return digits
        return digits[::-1]

    text = re.sub(
        r"(?m)(^|[ 	]*[-(]?[ 	]*)\.([0-9]{1,3})(?=\s)",
        lambda match: f"{match.group(1)}{normalize_digits(match.group(2))}.",
        text,
    )
    text = re.sub(
        r"(?<=\s)\.([0-9]{1,3})(?=[\u0600-\u06FF(])",
        lambda match: f" {normalize_digits(match.group(1))} ",
        text,
    )
    text = re.sub(
        r"(?<=[\u0600-\u06FF])\.([0-9]{1,3})(?=[\u0600-\u06FF(])",
        lambda match: f" {normalize_digits(match.group(1))} ",
        text,
    )
    text = re.sub(
        r"٪([0-9]{1,3})",
        lambda match: f"{normalize_digits(match.group(1))}٪",
        text,
    )
    return text


def _is_toc_page(lines: list[str]) -> bool:
    return any(TOC_TEXT in line for line in lines)


def _parse_chapter(line: str) -> str | None:
    match = CHAPTER_RE.match(line)
    if not match:
        return None
    return _normalize_spacing(match.group(0))


def _parse_article(line: str) -> str | None:
    if "المادة" not in line:
        return None
    if line.startswith("-") or line.startswith("."):
        return None
    if "." in line:
        return None
    if len(line) > 120:
        return None
    match = ARTICLE_NUMBER_RE.search(line)
    if not match:
        return None
    article_number = match.group(1) or match.group(2)
    title = re.sub(r"المادة\s*[0-9٠-٩]+|[0-9٠-٩]+\s*المادة", "", line)
    title = re.sub(r"[()[:：\]{}]+", " ", title)
    title = _normalize_spacing(title)
    if title:
        return f"المادة {article_number}: {title}"
    return f"المادة {article_number}"


def _to_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _window_blocks(blocks: list[list[str]], max_words: int, overlap_words: int) -> list[list[str]]:
    windows: list[list[str]] = []
    current: list[str] = []
    current_words = 0

    for block in blocks:
        block_words = len(" ".join(block).split())
        if current and current_words + block_words > max_words:
            windows.append(current[:])
            if overlap_words > 0:
                overlap: list[str] = []
                carry = 0
                for line in reversed(current):
                    overlap.insert(0, line)
                    carry += len(line.split())
                    if carry >= overlap_words:
                        break
                current = overlap[:]
                current_words = len(" ".join(current).split())
            else:
                current = []
                current_words = 0

        current.extend(block + [""])
        current_words += block_words

    if current:
        windows.append(current)
    return windows
