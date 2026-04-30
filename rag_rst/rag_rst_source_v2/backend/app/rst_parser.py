from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .config import Settings
from .schemas import ChunkRecord, ImageRecord


HEADING_CHARS = {"=": 1, "-": 2, "~": 3, "^": 4, '"': 5}
ANCHOR_RE = re.compile(r"^\s*\.\. _([^:]+):\s*$")
EQ_LABEL_RE = re.compile(r"^\s*:label:\s*(.+?)\s*$")
INLINE_MATH_RE = re.compile(r":math:`([^`]+)`")
INCLUDE_RE = re.compile(r"^\s*\.\. include::\s+(.+?)\s*$")
IMAGE_SEARCH_RE = re.compile(r"\.\.\s+(?:image|figure)::\s+")


def parse_corpus(settings: Settings) -> tuple[list[ChunkRecord], list[ImageRecord], dict[str, int]]:
    chunks: list[ChunkRecord] = []
    images: dict[str, ImageRecord] = {}
    stats = defaultdict(int)

    for path in sorted(settings.data_dir.rglob("*.rst")):
        doc_chunks, doc_images, doc_stats = parse_rst_file(path, settings)
        chunks.extend(doc_chunks)
        for image in doc_images:
            images.setdefault(image.image_path, image)
        for key, value in doc_stats.items():
            stats[key] += value

    stats["documents"] = len({chunk.source_path for chunk in chunks})
    return chunks, list(images.values()), dict(stats)


def parse_rst_file(path: Path, settings: Settings) -> tuple[list[ChunkRecord], list[ImageRecord], dict[str, int]]:
    lines, include_stats = _read_expanded_lines(path)
    headings = _find_headings(lines)
    if not headings:
        title = path.stem
        headings = [(0, title, 1, len(lines))]

    chunks: list[ChunkRecord] = []
    image_records: list[ImageRecord] = []
    stats = defaultdict(int)
    stats.update(include_stats)
    path_rel = str(path.relative_to(settings.data_dir))
    doc_code = path.parent.name
    hierarchy: list[tuple[int, str]] = []
    next_chunk_index = 0

    for index, (_, heading, level, content_start) in enumerate(headings):
        while hierarchy and hierarchy[-1][0] >= level:
            hierarchy.pop()
        hierarchy.append((level, heading))
        next_heading_start = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
        section_lines = lines[content_start:next_heading_start]
        clean_blocks = _to_blocks(section_lines)
        if not clean_blocks:
            continue

        for block_lines in _window_blocks(clean_blocks, settings.max_chunk_words, settings.chunk_overlap_words):
            anchors = [match.group(1) for line in block_lines if (match := ANCHOR_RE.match(line))]
            image_refs = [
                _normalize_image_ref(path_rel, image_ref)
                for line in block_lines
                if (image_ref := _extract_image_ref(line))
            ]
            equation_labels = [match.group(1) for line in block_lines if (match := EQ_LABEL_RE.match(line))]
            cleaned_text = _clean_chunk_text(block_lines)
            if len(cleaned_text.split()) < 20:
                continue

            section_path = " > ".join(item[1] for item in hierarchy)
            retrieval_text = (
                f"Titre: {hierarchy[0][1]}\n"
                f"Document: {doc_code}\n"
                f"Section: {section_path}\n"
                f"Ancres: {', '.join(anchors) if anchors else 'aucune'}\n"
                f"Images: {', '.join(image_refs) if image_refs else 'aucune'}\n\n"
                f"{cleaned_text}"
            )
            chunks.append(
                ChunkRecord(
                    source_path=path_rel,
                    doc_code=doc_code,
                    title=hierarchy[0][1],
                    section_path=section_path,
                    chunk_index=next_chunk_index,
                    content=cleaned_text,
                    retrieval_text=retrieval_text,
                    anchors=anchors,
                    image_refs=image_refs,
                    equation_labels=equation_labels,
                )
            )
            stats["chunks"] += 1
            stats["math_inline"] += len(INLINE_MATH_RE.findall("\n".join(block_lines)))
            stats["math_block"] += sum(1 for line in block_lines if line.strip() == ".. math::")

            for image_ref in image_refs:
                image_records.append(
                    ImageRecord(
                        image_path=image_ref,
                        doc_code=doc_code,
                        title=hierarchy[0][1],
                        caption_text=cleaned_text[:700],
                        related_source_path=path_rel,
                        related_section_path=section_path,
                        related_chunk_index=next_chunk_index,
                    )
                )
                stats["images"] += 1
            next_chunk_index += 1

    return chunks, image_records, stats


def _find_headings(lines: list[str]) -> list[tuple[int, str, int, int]]:
    headings: list[tuple[int, str, int, int]] = []
    for i in range(len(lines) - 1):
        title = lines[i].rstrip()
        underline = lines[i + 1].strip()
        if not title or len(underline) < 3:
            continue
        if len(set(underline)) == 1 and underline[0] in HEADING_CHARS and len(underline) >= len(title.strip()):
            headings.append((i, title.strip(), HEADING_CHARS[underline[0]], i + 2))
    return headings


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
    chunks: list[list[str]] = []
    current: list[str] = []
    current_words = 0

    for block in blocks:
        for expanded_block in _split_oversized_block(block, max_words, overlap_words):
            block_words = len(" ".join(expanded_block).split())
            if current and current_words + block_words > max_words:
                chunks.append(current[:])
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
            current.extend(expanded_block + [""])
            current_words += block_words

    if current:
        chunks.append(current)
    return chunks


def _clean_chunk_text(lines: list[str]) -> str:
    output: list[str] = []
    for line in lines:
        anchor_match = ANCHOR_RE.match(line)
        if anchor_match:
            output.append(f"[Anchor: {anchor_match.group(1)}]")
            continue
        if image_ref := _extract_image_ref(line):
            output.append(f"[Image: {image_ref}]")
            continue
        stripped = line.strip()
        if INCLUDE_RE.match(line):
            continue
        if stripped.startswith(".. math::"):
            output.append("[Math]")
            continue
        if stripped.startswith(".. code-block::"):
            output.append(f"[Code block: {line.split('::', 1)[1].strip() or 'text'}]")
            continue
        if stripped.startswith(".. dropdown::"):
            output.append(f"[Dropdown: {line.split('::', 1)[1].strip() or 'details'}]")
            continue
        if stripped.startswith(".. note::"):
            output.append("[Note]")
            continue
        if stripped.startswith(".. warning::"):
            output.append("[Warning]")
            continue
        output.append(stripped)
    return "\n".join(item for item in output if item).strip()


def _normalize_image_ref(source_path: str, image_ref: str) -> str:
    source_dir = Path(source_path).parent
    return str((source_dir / image_ref).as_posix())


def _extract_image_ref(line: str) -> str | None:
    stripped = line.strip()
    match = IMAGE_SEARCH_RE.search(stripped)
    if not match:
        return None

    remainder = stripped[match.end() :].strip()
    if not remainder:
        return None

    if remainder[0] in {'"', "'"}:
        quote = remainder[0]
        closing = remainder.find(quote, 1)
        if closing > 1:
            return remainder[1:closing].strip()
        remainder = remainder[1:]

    token = remainder.split()[0].strip().strip('"').strip("'").strip("|")
    return token or None


def _read_expanded_lines(path: Path, seen: set[Path] | None = None) -> tuple[list[str], dict[str, int]]:
    seen = seen or set()
    if path in seen:
        return [], {"include_cycles": 1}
    seen.add(path)
    stats = defaultdict(int)
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        include_match = INCLUDE_RE.match(line)
        if not include_match:
            lines.append(line)
            continue
        include_target = (path.parent / include_match.group(1).strip()).resolve()
        if include_target.exists():
            stats["includes_resolved"] += 1
            included_lines, include_stats = _read_expanded_lines(include_target, seen)
            lines.extend(included_lines)
            for key, value in include_stats.items():
                stats[key] += value
        else:
            stats["includes_missing"] += 1
    seen.remove(path)
    return lines, dict(stats)


def _split_oversized_block(block: list[str], max_words: int, overlap_words: int) -> list[list[str]]:
    if len(" ".join(block).split()) <= max_words:
        return [block]

    chunks: list[list[str]] = []
    current: list[str] = []
    current_words = 0

    for line in block:
        line_words = len(line.split())
        if current and current_words + line_words > max_words:
            chunks.append(current[:])
            if overlap_words > 0:
                overlap: list[str] = []
                carry = 0
                for previous in reversed(current):
                    overlap.insert(0, previous)
                    carry += len(previous.split())
                    if carry >= overlap_words:
                        break
                current = overlap[:]
                current_words = len(" ".join(current).split())
            else:
                current = []
                current_words = 0
        if line_words > max_words:
            if current:
                chunks.append(current[:])
                current = []
                current_words = 0
            chunks.append([line])
            continue
        current.append(line)
        current_words += line_words

    if current:
        chunks.append(current)
    return chunks
