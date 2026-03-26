from __future__ import annotations

import re
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None

from ..config import Settings
from .base import asset_path_for_storage, detect_languages, make_document, normalize_text
from ..schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedSegment, new_image_id

VISUAL_PAGE_KEYWORDS = (
    "figure",
    "architecture",
    "topology",
    "diagram",
    "workflow",
    "overview",
    "reference architecture",
    "network",
)
STEP_RE = re.compile(r"^(?:step\s+)?(?:\d+|[a-zA-Z])[\).:-]\s+")
CAPTION_RE = re.compile(r"^(?:figure|fig\.?|diagram|workflow|architecture|table|chart|image|screenshot|screen)\s*[\dA-Za-z.-]*[:\-]?\s+", re.IGNORECASE)
TABLE_SEPARATORS_RE = re.compile(r"\s{2,}|\t|\|")
ENUMERATED_HEADING_RE = re.compile(r"^(?:[\(\[]?[\d٠-٩IVXivxA-Za-z]+[\)\].:-]\s*).+")
NUMERIC_SIGNAL_RE = re.compile(r"[\d٠-٩]")


class PdfParser:
    parser_name = "pdf_parser"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.extracted_images_dir = settings.extracted_images_dir
        self.root_dir = settings.root_dir

    def parse(self, path: Path, relative_path: str):
        reader = PdfReader(str(path))
        document = make_document(path, relative_path, "pdf", parser_used=self.parser_name)
        asset_dir = self.extracted_images_dir / document.document_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        segments: list[NormalizedSegment] = []
        blocks: list[BlockRecord] = []
        images: list[ImageContext] = []
        page_texts = [normalize_text(page.extract_text() or "") for page in reader.pages]
        page_images = self._extract_images(path, asset_dir, page_texts)
        order_index = 0
        segment_index = 0
        heading_stack: list[tuple[int, str]] = []

        for page_number, text in enumerate(page_texts, start=1):
            image_contexts = page_images.get(page_number, [])
            images.extend(image_contexts)
            page_blocks, heading_stack = self._page_blocks(document, page_number, text, image_contexts, order_index, heading_stack)
            order_index += len(page_blocks)
            blocks.extend(page_blocks)
            for block in page_blocks:
                if block.block_type == "heading":
                    continue
                if not block.text and not block.image_contexts:
                    continue
                segments.append(
                    NormalizedSegment(
                        segment_id=f"{document.document_id}-seg-{segment_index}",
                        segment_type=_segment_type_for_block(block.block_type),
                        text=block.text or block.title,
                        title=block.title,
                        section_path=block.section_path,
                        citation_anchor=block.citation_anchor,
                        image_contexts=block.image_contexts,
                        metadata=dict(block.metadata),
                    )
                )
                segment_index += 1

        document.images = images
        document.blocks = blocks
        document.segments = segments
        chunking_hints = _build_chunking_hints(document)
        document.metadata = {
            **document.metadata,
            "document_structure": chunking_hints.get("structure", "paged_sections"),
            "chunking_hints": chunking_hints,
        }
        language_tags = detect_languages(block.text or block.title for block in blocks if block.text or block.title)
        document.language_tags = language_tags
        for block in document.blocks:
            block.language_tags = language_tags
        for segment in document.segments:
            segment.language_tags = language_tags
        return document

    def _page_blocks(
        self,
        document,
        page_number: int,
        text: str,
        image_contexts: list[ImageContext],
        start_index: int,
        heading_stack: list[tuple[int, str]],
    ) -> tuple[list[BlockRecord], list[tuple[int, str]]]:
        blocks: list[BlockRecord] = []
        active_headings = heading_stack[:]
        units = _page_content_units(text)
        for offset, unit in enumerate(units):
            block_type = str(unit.get("block_type") or "paragraph")
            paragraph = str(unit.get("text") or "")
            if not paragraph and block_type != "heading":
                continue

            if block_type == "heading":
                heading_level = int(unit.get("heading_level") or 1)
                active_headings = _updated_heading_stack(active_headings, paragraph, heading_level)
                section_path = _section_path(document.title, active_headings, page_number)
                blocks.append(
                    BlockRecord(
                        block_id=f"{document.document_id}-block-{start_index + len(blocks)}",
                        block_type="heading",
                        text=paragraph,
                        order_index=start_index + len(blocks),
                        title=paragraph,
                        section_path=section_path,
                        citation_anchor=CitationAnchor(page_number=page_number, source_label=f"page {page_number}"),
                        heading_level=heading_level,
                        metadata={
                            "page_number": page_number,
                            "paragraph_index": offset,
                            "layout_hint": "heading",
                            "heading_style": unit.get("heading_style", "heuristic"),
                        },
                    )
                )
                continue

            section_path = _section_path(document.title, active_headings, page_number)
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{start_index + len(blocks)}",
                    block_type=block_type,
                    text=paragraph,
                    order_index=start_index + len(blocks),
                    title=section_path[-1],
                    section_path=section_path,
                    citation_anchor=CitationAnchor(page_number=page_number, source_label=f"page {page_number}"),
                    step_number=_step_number(paragraph) if block_type == "step" else "",
                    metadata={
                        "page_number": page_number,
                        "paragraph_index": offset,
                        "layout_hint": block_type,
                    },
                )
            )

        if image_contexts:
            anchor_block = _image_anchor_block(blocks)
            if anchor_block is None:
                section_path = _section_path(document.title, active_headings, page_number)
                anchor_block = BlockRecord(
                    block_id=f"{document.document_id}-block-{start_index + len(blocks)}",
                    block_type="figure",
                    text="",
                    order_index=start_index + len(blocks),
                    title=section_path[-1],
                    section_path=section_path,
                    citation_anchor=CitationAnchor(page_number=page_number, source_label=f"page {page_number}"),
                    metadata={"page_number": page_number, "generated": True, "layout_hint": "figure"},
                )
                blocks.append(anchor_block)
            anchor_block.image_contexts.extend(image_contexts)
            if anchor_block.block_type == "paragraph" and not anchor_block.text:
                anchor_block.block_type = "figure"
            anchor_block.metadata = {**anchor_block.metadata, "has_linked_image": True}

        if not blocks and image_contexts:
            section_path = _section_path(document.title, active_headings, page_number)
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{start_index}",
                    block_type="figure",
                    text="",
                    order_index=start_index,
                    title=section_path[-1],
                    section_path=section_path,
                    citation_anchor=CitationAnchor(page_number=page_number, source_label=f"page {page_number}"),
                    image_contexts=image_contexts,
                    metadata={"page_number": page_number, "layout_hint": "figure"},
                )
            )
        return blocks, active_headings

    def _extract_images(self, path: Path, asset_dir: Path, page_texts: list[str]) -> dict[int, list[ImageContext]]:
        if fitz is None:
            return {}
        results: dict[int, list[ImageContext]] = {}
        pdf = fitz.open(path)
        rendered_pages = 0
        try:
            for page_index in range(pdf.page_count):
                page = pdf.load_page(page_index)
                page_number = page_index + 1
                entries = self._extract_embedded_images(pdf, page, page_number, asset_dir)
                if not entries and rendered_pages < self.settings.max_pdf_visual_pages:
                    drawings = len(page.get_drawings()) if hasattr(page, "get_drawings") else 0
                    if should_render_page_visual(
                        page_texts[page_index] if page_index < len(page_texts) else "",
                        drawing_count=drawings,
                        has_embedded_images=False,
                        min_drawing_count=self.settings.min_pdf_drawing_count,
                    ):
                        rendered = self._render_page_image(page, page_number, asset_dir)
                        if rendered is not None:
                            entries.append(rendered)
                            rendered_pages += 1
                if entries:
                    results[page_number] = entries
        finally:
            pdf.close()
        return results

    def _extract_embedded_images(self, pdf, page, page_number: int, asset_dir: Path) -> list[ImageContext]:
        entries: list[ImageContext] = []
        for image_info in page.get_images(full=True):
            xref = image_info[0]
            image = pdf.extract_image(xref)
            ext = image.get("ext", "png")
            image_name = f"page-{page_number}-{new_image_id()}.{ext}"
            image_path = asset_dir / image_name
            image_path.write_bytes(image["image"])
            rel_path = asset_path_for_storage(image_path, self.root_dir)
            entries.append(
                ImageContext(
                    image_id=new_image_id(),
                    image_path=rel_path,
                    related_section_path=f"Page {page_number}",
                )
            )
        return entries

    def _render_page_image(self, page, page_number: int, asset_dir: Path) -> ImageContext | None:
        scale = max(self.settings.pdf_render_dpi / 72.0, 1.0)
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image_name = f"page-render-{page_number}-{new_image_id()}.png"
        image_path = asset_dir / image_name
        pixmap.save(image_path)
        rel_path = asset_path_for_storage(image_path, self.root_dir)
        return ImageContext(
            image_id=new_image_id(),
            image_path=rel_path,
            related_section_path=f"Page {page_number}",
        )


def should_render_page_visual(text: str, *, drawing_count: int, has_embedded_images: bool, min_drawing_count: int) -> bool:
    if has_embedded_images:
        return False
    if drawing_count >= min_drawing_count:
        return True
    lowered = text.lower()
    return any(keyword in lowered for keyword in VISUAL_PAGE_KEYWORDS)


def _page_paragraphs(text: str) -> list[str]:
    return [normalize_text(part) for part in text.split("\n\n") if normalize_text(part)]


def _page_content_units(text: str) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for paragraph in _page_paragraphs(text):
        lines = [normalize_text(line) for line in paragraph.split("\n") if normalize_text(line)]
        if not lines:
            continue
        buffer: list[str] = []
        for line in lines:
            if _looks_like_heading_line(line):
                if buffer:
                    units.append({"block_type": _paragraph_block_type("\n".join(buffer)), "text": "\n".join(buffer)})
                    buffer = []
                units.append(
                    {
                        "block_type": "heading",
                        "text": line,
                        "heading_level": _heading_level_for_line(line),
                        "heading_style": "line_heuristic",
                    }
                )
            else:
                buffer.append(line)
        if buffer:
            units.append({"block_type": _paragraph_block_type("\n".join(buffer)), "text": "\n".join(buffer)})
    return units


def _paragraph_block_type(paragraph: str) -> str:
    if _looks_like_table(paragraph):
        return "table"
    if STEP_RE.match(paragraph):
        return "step"
    if CAPTION_RE.match(paragraph):
        return "caption"
    if _looks_like_heading(paragraph):
        return "heading"
    return "paragraph"


def _looks_like_heading_line(text: str) -> bool:
    if _looks_like_table(text) or CAPTION_RE.match(text) or STEP_RE.match(text):
        return False
    if text.endswith((".", ";", "?", "!")):
        return False
    words = text.split()
    if not words or len(words) > 14:
        return False
    if ENUMERATED_HEADING_RE.match(text):
        return _is_compact_enumerated_heading(text)
    if text.endswith(":"):
        return True
    if ":" in text and len(words) <= 12:
        return True
    return _looks_like_heading(text)


def _heading_level_for_line(text: str) -> int:
    words = text.split()
    if ENUMERATED_HEADING_RE.match(text) and _is_compact_enumerated_heading(text):
        return 2
    if ":" in text and NUMERIC_SIGNAL_RE.search(text):
        return 2
    if ":" in text and not NUMERIC_SIGNAL_RE.search(text):
        return 1
    if len(words) <= 4:
        return 1
    return 2


def _is_compact_enumerated_heading(text: str) -> bool:
    words = text.split()
    if len(words) > 10:
        return False
    if any(punct in text for punct in (",", "،", ";", "؛")):
        return False
    return True


def _updated_heading_stack(stack: list[tuple[int, str]], heading_text: str, heading_level: int) -> list[tuple[int, str]]:
    updated = stack[:]
    while updated and updated[-1][0] >= heading_level:
        updated.pop()
    updated.append((heading_level, heading_text))
    return updated


def _section_path(document_title: str, heading_stack: list[tuple[int, str]], page_number: int) -> list[str]:
    if not heading_stack:
        return [document_title, f"Page {page_number}"]
    return [document_title, *[heading for _, heading in heading_stack]]


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    if not words or len(words) > 8:
        return False
    if CAPTION_RE.match(text) or STEP_RE.match(text) or _looks_like_table(text):
        return False
    if text.endswith((".", ";", "?", "!")):
        return False
    if text.endswith(":"):
        return len(words) <= 6
    if sum(char.isdigit() for char in text) > 4:
        return False
    alphabetic = [char for char in text if char.isalpha()]
    if alphabetic and sum(1 for char in alphabetic if char.isupper()) / len(alphabetic) > 0.75:
        return True
    return text.istitle() and len(words) <= 6


def _looks_like_table(text: str) -> bool:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 2 and all(TABLE_SEPARATORS_RE.search(line) for line in lines[: min(4, len(lines))]):
        return True
    if len(lines) == 1:
        separators = len(TABLE_SEPARATORS_RE.findall(lines[0]))
        return separators >= 2 and len(lines[0].split()) >= 3
    return False


def _image_anchor_block(blocks: list[BlockRecord]) -> BlockRecord | None:
    caption_block = next((block for block in blocks if block.block_type == "caption"), None)
    if caption_block is not None:
        return caption_block
    figure_paragraph = next((block for block in blocks if _contains_visual_reference(block.text)), None)
    if figure_paragraph is not None:
        return figure_paragraph
    step_block = next((block for block in blocks if block.block_type == "step"), None)
    if step_block is not None:
        return step_block
    return next((block for block in blocks if block.block_type not in {"heading", "table"}), None)


def _contains_visual_reference(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ("figure", "diagram", "workflow", "architecture", "screenshot", "shown"))


def _segment_type_for_block(block_type: str) -> str:
    mapping = {
        "step": "paragraph",
        "figure": "image_caption",
        "caption": "image_caption",
    }
    return mapping.get(block_type, block_type)


def _step_number(text: str) -> str:
    match = STEP_RE.match(text)
    if not match:
        return ""
    return match.group(0).strip()


def _build_chunking_hints(document) -> dict[str, object]:
    pages: list[dict[str, object]] = []
    blocks_by_page: dict[int, list[BlockRecord]] = {}
    has_hierarchical_sections = False
    for block in document.blocks:
        page_number = block.citation_anchor.page_number
        if page_number is None:
            continue
        blocks_by_page.setdefault(page_number, []).append(block)
        if len(block.section_path) > 2:
            has_hierarchical_sections = True

    for page_number in sorted(blocks_by_page):
        page_blocks = blocks_by_page[page_number]
        sections: list[dict[str, object]] = []
        seen_paths: set[tuple[str, ...]] = set()
        for block in page_blocks:
            if block.block_type == "heading":
                continue
            path_key = tuple(block.section_path)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            layout_hints: list[str] = []
            block_ids: list[str] = []
            for candidate in page_blocks:
                if candidate.section_path != block.section_path or candidate.block_type == "heading":
                    continue
                block_ids.append(candidate.block_id)
                layout_hint = str(candidate.metadata.get("layout_hint", "")).strip()
                if layout_hint and layout_hint not in layout_hints:
                    layout_hints.append(layout_hint)
            if not block_ids:
                continue
            sections.append(
                {
                    "section_path": block.section_path,
                    "block_ids": block_ids,
                    "layout_hints": layout_hints,
                }
            )
        pages.append(
            {
                "page_number": page_number,
                "sections": sections,
            }
        )

    structure = "hierarchical_paged_sections" if has_hierarchical_sections else "paged_sections"
    return {
        "preferred_strategy": "pdf_section_window",
        "structure": structure,
        "page_count": len(pages),
        "pages": pages,
    }
