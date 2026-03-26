from backend.app.parsers.base import segment_to_chunks
from backend.app.parsers.chunking import choose_chunking_strategy
from backend.app.schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedDocument


def test_choose_chunking_strategy_uses_pdf_hints() -> None:
    document = NormalizedDocument(
        document_id="doc-pdf",
        source_path="uploads/policy.pdf",
        file_name="policy.pdf",
        file_type="pdf",
        title="Policy",
        checksum="checksum",
        metadata={"chunking_hints": {"preferred_strategy": "pdf_section_window"}},
    )

    strategy = choose_chunking_strategy(document)

    assert strategy.name == "pdf_section_window"


def test_segment_to_chunks_uses_pdf_structure_aware_strategy() -> None:
    image = ImageContext(image_id="img-1", image_path="images/policy.png", related_section_path="Policy > Eligibility")
    document = NormalizedDocument(
        document_id="doc-pdf",
        source_path="uploads/policy.pdf",
        file_name="policy.pdf",
        file_type="pdf",
        title="Remote Work Policy",
        checksum="checksum",
        parser_used="pdf_parser",
        parser_confidence=0.85,
        blocks=[
            BlockRecord(
                block_id="h1",
                block_type="heading",
                text="Eligibility",
                order_index=0,
                title="Eligibility",
                section_path=["Remote Work Policy", "Eligibility"],
                citation_anchor=CitationAnchor(page_number=2, source_label="page 2"),
                metadata={"page_number": 2, "layout_hint": "heading"},
            ),
            BlockRecord(
                block_id="p1",
                block_type="paragraph",
                text="Employees may work from home up to 30 days per year with manager approval.",
                order_index=1,
                title="Eligibility",
                section_path=["Remote Work Policy", "Eligibility"],
                citation_anchor=CitationAnchor(page_number=2, source_label="page 2"),
                metadata={"page_number": 2, "layout_hint": "paragraph"},
            ),
            BlockRecord(
                block_id="c1",
                block_type="caption",
                text="Figure 1: Remote work approval workflow.",
                order_index=2,
                title="Eligibility",
                section_path=["Remote Work Policy", "Eligibility"],
                citation_anchor=CitationAnchor(page_number=2, source_label="page 2"),
                image_contexts=[image],
                metadata={"page_number": 2, "layout_hint": "caption"},
            ),
        ],
        images=[image],
        metadata={
            "document_structure": "paged_sections",
            "chunking_hints": {
                "preferred_strategy": "pdf_section_window",
                "structure": "paged_sections",
                "pages": [
                    {
                        "page_number": 2,
                        "sections": [
                            {
                                "section_path": ["Remote Work Policy", "Eligibility"],
                                "block_ids": ["h1", "p1", "c1"],
                                "layout_hints": ["heading", "paragraph", "caption"],
                            }
                        ],
                    }
                ],
            },
        },
    )

    chunks, images = segment_to_chunks(document, max_words=120, overlap_words=10)

    assert document.metadata["chunking_strategy"] == "pdf_section_window"
    assert document.metadata["structure_page_count"] == 1
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "figure_explainer_chunk"
    assert chunks[0].metadata["page_number"] == 2
    assert chunks[0].metadata["layout_hints"] == ["heading", "paragraph", "caption"]
    assert "Page number: 2" in chunks[0].embedding_text
    assert "Layout hints: heading, paragraph, caption" in chunks[0].embedding_text
    assert chunks[0].image_refs == ["images/policy.png"]
    assert len(images) == 1
    assert images[0].image_path == "images/policy.png"


def test_pdf_section_chunks_include_heading_blocks_with_body_text() -> None:
    document = NormalizedDocument(
        document_id="doc-pdf-2",
        source_path="uploads/policy.pdf",
        file_name="policy.pdf",
        file_type="pdf",
        title="Remote Work Policy",
        checksum="checksum",
        parser_used="pdf_parser",
        parser_confidence=0.85,
        blocks=[
            BlockRecord(
                block_id="h1",
                block_type="heading",
                text="Article 4: Eligibility",
                order_index=0,
                title="Article 4: Eligibility",
                section_path=["Remote Work Policy", "Chapter Two", "Article 4: Eligibility"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                metadata={"page_number": 3, "layout_hint": "heading"},
            ),
            BlockRecord(
                block_id="p1",
                block_type="paragraph",
                text="Employees may work from home up to 30 days per year with manager approval.",
                order_index=1,
                title="Article 4: Eligibility",
                section_path=["Remote Work Policy", "Chapter Two", "Article 4: Eligibility"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                metadata={"page_number": 3, "layout_hint": "paragraph"},
            ),
        ],
        metadata={
            "document_structure": "hierarchical_paged_sections",
            "chunking_hints": {
                "preferred_strategy": "pdf_section_window",
                "structure": "hierarchical_paged_sections",
                "pages": [
                    {
                        "page_number": 3,
                        "sections": [
                            {
                                "section_path": ["Remote Work Policy", "Chapter Two", "Article 4: Eligibility"],
                                "block_ids": ["p1"],
                                "layout_hints": ["paragraph"],
                            }
                        ],
                    }
                ],
            },
        },
    )

    chunks, _images = segment_to_chunks(document, max_words=120, overlap_words=10)

    assert len(chunks) == 1
    assert chunks[0].display_text.startswith("Article 4: Eligibility")
    assert "30 days per year" in chunks[0].display_text
    assert chunks[0].block_ids == ["h1", "p1"]
