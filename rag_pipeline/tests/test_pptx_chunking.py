from backend.app.parsers.base import segment_to_chunks
from backend.app.parsers.chunking import choose_chunking_strategy
from backend.app.schemas import BlockRecord, CitationAnchor, NormalizedDocument


def test_choose_chunking_strategy_uses_slide_hints() -> None:
    document = NormalizedDocument(
        document_id="doc-pptx",
        source_path="uploads/deck.pptx",
        file_name="deck.pptx",
        file_type="pptx",
        title="Deck",
        checksum="checksum",
        metadata={"chunking_hints": {"preferred_strategy": "slide_window"}},
    )

    strategy = choose_chunking_strategy(document)

    assert strategy.name == "slide_window"


def test_segment_to_chunks_uses_slide_structure_aware_strategy() -> None:
    document = NormalizedDocument(
        document_id="doc-pptx",
        source_path="uploads/deck.pptx",
        file_name="deck.pptx",
        file_type="pptx",
        title="DR Deck",
        checksum="checksum",
        parser_used="pptx_parser",
        parser_confidence=0.85,
        blocks=[
            BlockRecord(
                block_id="h1",
                block_type="heading",
                text="Remote Work",
                order_index=0,
                title="Remote Work",
                section_path=["DR Deck", "Remote Work"],
                citation_anchor=CitationAnchor(slide_number=1, source_label="slide 1"),
                metadata={"slide_number": 1, "layout_hint": "title"},
            ),
            BlockRecord(
                block_id="b1",
                block_type="paragraph",
                text="Employees may work from home up to 30 days per year.",
                order_index=1,
                title="Remote Work",
                section_path=["DR Deck", "Remote Work"],
                citation_anchor=CitationAnchor(slide_number=1, source_label="slide 1"),
                metadata={"slide_number": 1, "layout_hint": "body"},
            ),
            BlockRecord(
                block_id="n1",
                block_type="note",
                text="Manager approval is required.",
                order_index=2,
                title="Remote Work",
                section_path=["DR Deck", "Remote Work"],
                citation_anchor=CitationAnchor(slide_number=1, source_label="slide 1"),
                metadata={"slide_number": 1, "layout_hint": "notes"},
            ),
        ],
        metadata={
            "document_structure": "slides",
            "chunking_hints": {
                "preferred_strategy": "slide_window",
                "structure": "slides",
                "slides": [
                    {
                        "slide_number": 1,
                        "section_path": ["DR Deck", "Remote Work"],
                        "block_ids": ["h1", "b1", "n1"],
                        "layout_hints": ["title", "body", "notes"],
                    }
                ],
            },
        },
    )

    chunks, _ = segment_to_chunks(document, max_words=120, overlap_words=10)

    assert document.metadata["chunking_strategy"] == "slide_window"
    assert document.metadata["structure_slide_count"] == 1
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "slide_chunk"
    assert chunks[0].metadata["slide_number"] == 1
    assert chunks[0].metadata["layout_hints"] == ["title", "body", "notes"]
    assert "Slide number: 1" in chunks[0].embedding_text
    assert "Layout hints: title, body, notes" in chunks[0].embedding_text
