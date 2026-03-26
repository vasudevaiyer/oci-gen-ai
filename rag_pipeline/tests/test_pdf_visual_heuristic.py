from types import SimpleNamespace

from backend.app.parsers.pdf_parser import (
    _build_chunking_hints,
    _image_anchor_block,
    _looks_like_heading,
    _looks_like_heading_line,
    _page_content_units,
    _paragraph_block_type,
    should_render_page_visual,
)
from backend.app.schemas import BlockRecord, CitationAnchor


def test_render_page_visual_when_drawing_count_is_high() -> None:
    assert should_render_page_visual("plain page", drawing_count=30, has_embedded_images=False, min_drawing_count=25)


def test_render_page_visual_when_keyword_is_present() -> None:
    assert should_render_page_visual("Reference architecture for OCI DR", drawing_count=0, has_embedded_images=False, min_drawing_count=25)


def test_render_page_visual_skips_when_embedded_images_exist() -> None:
    assert not should_render_page_visual("Reference architecture", drawing_count=40, has_embedded_images=True, min_drawing_count=25)


def test_pdf_paragraph_block_type_detects_caption_and_table() -> None:
    assert _paragraph_block_type("Figure 2: Recovery workflow") == "caption"
    assert _paragraph_block_type("Region   Status   Lag") == "table"


def test_pdf_heading_confidence_rejects_sentence_like_text() -> None:
    assert _looks_like_heading("Disaster Recovery Overview")
    assert not _looks_like_heading("This section explains how the standby region is promoted during failover.")


def test_pdf_image_anchor_prefers_caption_over_generic_paragraph() -> None:
    blocks = [
        BlockRecord(block_id="b1", block_type="paragraph", text="The workflow is shown below.", order_index=0),
        BlockRecord(block_id="b2", block_type="caption", text="Figure 2: Recovery workflow", order_index=1),
    ]

    anchor = _image_anchor_block(blocks)

    assert anchor is not None
    assert anchor.block_id == "b2"


def test_pdf_page_content_units_detects_nested_heading_like_lines() -> None:
    text = "Chapter Two: Remote Work\nArticle 4: Eligibility\nEmployees may work from home up to 30 days per year."

    units = _page_content_units(text)

    assert [unit["block_type"] for unit in units] == ["heading", "heading", "paragraph"]
    assert units[0]["heading_level"] == 1
    assert units[1]["heading_level"] == 2


def test_pdf_chunking_hints_preserve_hierarchical_sections() -> None:
    document = SimpleNamespace(
        blocks=[
            BlockRecord(
                block_id="h1",
                block_type="heading",
                text="Chapter Two: Remote Work",
                order_index=0,
                title="Chapter Two: Remote Work",
                section_path=["Policy", "Chapter Two: Remote Work"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                metadata={"page_number": 3, "layout_hint": "heading"},
            ),
            BlockRecord(
                block_id="h2",
                block_type="heading",
                text="Article 4: Eligibility",
                order_index=1,
                title="Article 4: Eligibility",
                section_path=["Policy", "Chapter Two: Remote Work", "Article 4: Eligibility"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                metadata={"page_number": 3, "layout_hint": "heading"},
            ),
            BlockRecord(
                block_id="p1",
                block_type="paragraph",
                text="Employees may work from home up to 30 days per year.",
                order_index=2,
                title="Article 4: Eligibility",
                section_path=["Policy", "Chapter Two: Remote Work", "Article 4: Eligibility"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                metadata={"page_number": 3, "layout_hint": "paragraph"},
            ),
        ]
    )

    hints = _build_chunking_hints(document)

    assert hints["structure"] == "hierarchical_paged_sections"
    assert hints["pages"][0]["sections"][0]["section_path"] == ["Policy", "Chapter Two: Remote Work", "Article 4: Eligibility"]
    assert hints["pages"][0]["sections"][0]["block_ids"] == ["p1"]


def test_pdf_heading_detection_keeps_long_numbered_lines_as_body_text() -> None:
    text = "1. Based on employee request and subject to the annual remote-work balance."

    assert not _looks_like_heading_line(text)
