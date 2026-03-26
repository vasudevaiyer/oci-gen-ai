from pathlib import Path

from backend.app.parsers.base import blocks_to_chunks, build_embedding_text, classify_document_archetype, segment_to_chunks, window_text
from backend.app.parsers.chunking import choose_chunking_strategy
from backend.app.parsers.rst_parser import RstParser
from backend.app.schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedDocument


def test_window_text_splits_with_overlap() -> None:
    text = "\n\n".join([
        "alpha beta gamma delta",
        "epsilon zeta eta theta",
        "iota kappa lambda mu",
    ])
    windows = window_text(text, max_words=6, overlap_words=2)
    assert len(windows) >= 2


def test_embedding_text_includes_semantic_context() -> None:
    rendered = build_embedding_text(
        document_title="Runbook",
        section_path=["Runbook", "Recovery"],
        chunk_type="procedure_chunk",
        location_hint="page 3",
        content="Check replication lag before failover.",
        document_archetype="procedural",
    )
    assert "Document title: Runbook" in rendered
    assert "Archetype: procedural" in rendered
    assert "Section path: Runbook > Recovery" in rendered
    assert "Location: page 3" in rendered


def test_blocks_to_chunks_groups_paragraph_and_figure_for_mixed_multimodal_sections() -> None:
    image = ImageContext(image_id="img-arch", image_path="images/architecture.png", related_section_path="Future State Architecture > Physical Architecture")
    document = NormalizedDocument(
        document_id="doc-arch",
        source_path="uploads/architecture.docx",
        file_name="architecture.docx",
        file_type="docx",
        title="Architecture",
        checksum="checksum",
        document_archetype="mixed_multimodal",
        blocks=[
            BlockRecord(
                block_id="h1",
                block_type="heading",
                text="Physical Architecture",
                order_index=0,
                title="Physical Architecture",
                section_path=["Architecture", "Future State Architecture", "Physical Architecture"],
                citation_anchor=CitationAnchor(source_label="Physical Architecture"),
            ),
            BlockRecord(
                block_id="p1",
                block_type="paragraph",
                text="The physical architecture diagram below illustrates the components and their interactions.",
                order_index=1,
                title="Physical Architecture",
                section_path=["Architecture", "Future State Architecture", "Physical Architecture"],
                citation_anchor=CitationAnchor(source_label="Physical Architecture"),
            ),
            BlockRecord(
                block_id="f1",
                block_type="figure",
                text="",
                order_index=2,
                title="Physical Architecture",
                section_path=["Architecture", "Future State Architecture", "Physical Architecture"],
                citation_anchor=CitationAnchor(source_label="Physical Architecture"),
                image_contexts=[image],
            ),
            BlockRecord(
                block_id="c1",
                block_type="caption",
                text="OCI physical architecture",
                order_index=3,
                title="Physical Architecture",
                section_path=["Architecture", "Future State Architecture", "Physical Architecture"],
                citation_anchor=CitationAnchor(source_label="Physical Architecture"),
            ),
        ],
        images=[image],
    )

    chunks, images = blocks_to_chunks(document, max_words=120, overlap_words=10)

    assert len(chunks) == 1
    assert chunks[0].block_ids == ["h1", "p1", "f1", "c1"]
    assert chunks[0].image_refs == ["images/architecture.png"]
    assert len(images) == 1
    assert images[0].related_block_ids == ["h1", "p1", "f1", "c1"]


def test_blocks_to_chunks_groups_steps_with_linked_images() -> None:
    image = ImageContext(image_id="img-1", image_path="images/step.png", related_section_path="Access Review")
    document = NormalizedDocument(
        document_id="doc-1",
        source_path="uploads/sop.docx",
        file_name="sop.docx",
        file_type="docx",
        title="Access SOP",
        checksum="checksum",
        blocks=[
            BlockRecord(
                block_id="b0",
                block_type="heading",
                text="Access Review",
                order_index=0,
                title="Access Review",
                section_path=["Access SOP", "Access Review"],
                citation_anchor=CitationAnchor(source_label="Access Review"),
            ),
            BlockRecord(
                block_id="b1",
                block_type="step",
                text="1. Open the review console.",
                order_index=1,
                title="Access Review",
                section_path=["Access SOP", "Access Review"],
                citation_anchor=CitationAnchor(page_number=2, source_label="page 2"),
                image_contexts=[image],
                step_number="1.",
            ),
            BlockRecord(
                block_id="b2",
                block_type="paragraph",
                text="Verify the request details before approval.",
                order_index=2,
                title="Access Review",
                section_path=["Access SOP", "Access Review"],
                citation_anchor=CitationAnchor(page_number=2, source_label="page 2"),
            ),
        ],
        images=[image],
    )

    chunks, images = blocks_to_chunks(document, max_words=80, overlap_words=10)

    assert document.document_archetype == "mixed_multimodal"
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "mixed_context_chunk"
    assert chunks[0].block_ids == ["b0", "b1", "b2"]
    assert chunks[0].image_refs == ["images/step.png"]
    assert len(images) == 1
    assert images[0].related_block_ids == ["b0", "b1", "b2"]


def test_procedure_chunks_split_at_next_step_boundary() -> None:
    document = NormalizedDocument(
        document_id="doc-proc",
        source_path="uploads/runbook.docx",
        file_name="runbook.docx",
        file_type="docx",
        title="Failover Runbook",
        checksum="checksum",
        blocks=[
            BlockRecord(
                block_id="h1",
                block_type="heading",
                text="Failover",
                order_index=0,
                title="Failover",
                section_path=["Failover Runbook", "Failover"],
                citation_anchor=CitationAnchor(source_label="Failover"),
            ),
            BlockRecord(
                block_id="s1",
                block_type="step",
                text="1. Confirm replication health.",
                order_index=1,
                title="Failover",
                section_path=["Failover Runbook", "Failover"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                step_number="1.",
            ),
            BlockRecord(
                block_id="p1",
                block_type="paragraph",
                text="Check lag is below the policy threshold.",
                order_index=2,
                title="Failover",
                section_path=["Failover Runbook", "Failover"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
            ),
            BlockRecord(
                block_id="s2",
                block_type="step",
                text="2. Start the failover workflow.",
                order_index=3,
                title="Failover",
                section_path=["Failover Runbook", "Failover"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
                step_number="2.",
            ),
            BlockRecord(
                block_id="p2",
                block_type="paragraph",
                text="Track the workflow until standby promotion is complete.",
                order_index=4,
                title="Failover",
                section_path=["Failover Runbook", "Failover"],
                citation_anchor=CitationAnchor(page_number=3, source_label="page 3"),
            ),
        ],
    )

    chunks, _ = blocks_to_chunks(document, max_words=80, overlap_words=10)

    assert len(chunks) == 2
    assert all(chunk.chunk_type == "procedure_chunk" for chunk in chunks)
    assert chunks[0].block_ids == ["h1", "s1", "p1"]
    assert chunks[1].block_ids == ["s2", "p2"]


def test_classify_document_archetype_detects_regulatory_blocks() -> None:
    document = NormalizedDocument(
        document_id="doc-2",
        source_path="uploads/policy.docx",
        file_name="policy.docx",
        file_type="docx",
        title="Access Policy",
        checksum="checksum",
        blocks=[
            BlockRecord(
                block_id="b0",
                block_type="heading",
                text="Access Control",
                order_index=0,
                title="Access Control",
                section_path=["Access Policy", "Access Control"],
                citation_anchor=CitationAnchor(source_label="Access Control"),
            ),
            BlockRecord(
                block_id="b1",
                block_type="paragraph",
                text="Managers must review privileged access every quarter and shall record exceptions.",
                order_index=1,
                title="Access Control",
                section_path=["Access Policy", "Access Control"],
                citation_anchor=CitationAnchor(page_number=7, source_label="page 7"),
            ),
            BlockRecord(
                block_id="b2",
                block_type="paragraph",
                text="Exceptions require written approval from the control owner.",
                order_index=2,
                title="Access Control",
                section_path=["Access Policy", "Access Control"],
                citation_anchor=CitationAnchor(page_number=7, source_label="page 7"),
            ),
        ],
    )

    assert classify_document_archetype(document) == "regulatory"

    chunks, _ = blocks_to_chunks(document, max_words=120, overlap_words=10)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "policy_clause_chunk"
    assert chunks[0].block_ids == ["b0", "b1", "b2"]


def test_slide_blocks_map_to_slide_chunks() -> None:
    document = NormalizedDocument(
        document_id="doc-slide",
        source_path="uploads/deck.pptx",
        file_name="deck.pptx",
        file_type="pptx",
        title="DR Deck",
        checksum="checksum",
        blocks=[
            BlockRecord(
                block_id="sl1",
                block_type="paragraph",
                text="Recovery architecture and failover sequence.",
                order_index=0,
                title="Architecture",
                section_path=["DR Deck", "Architecture"],
                citation_anchor=CitationAnchor(slide_number=4, source_label="slide 4"),
            )
        ],
    )

    chunks, _ = blocks_to_chunks(document, max_words=80, overlap_words=10)

    assert document.document_archetype == "presentation"
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "slide_chunk"


def test_choose_chunking_strategy_uses_rst_hints() -> None:
    document = NormalizedDocument(
        document_id="doc-rst",
        source_path="uploads/guide.rst",
        file_name="guide.rst",
        file_type="rst",
        title="Guide",
        checksum="checksum",
        metadata={"chunking_hints": {"preferred_strategy": "rst_section_window"}},
    )

    strategy = choose_chunking_strategy(document)

    assert strategy.name == "rst_section_window"


def test_segment_to_chunks_uses_rst_structure_aware_strategy(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    images_dir = docs_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "diagram.png").write_bytes(b"fake")

    rst_path = docs_dir / "guide.rst"
    rst_path.write_text(
        """
Guide Title
===========

.. _remote-work:

Remote work details with :math:`n + 1`.

.. figure:: images/diagram.png
   :alt: Recovery diagram

   Recovery flow between primary and standby regions.

Policy Notes
------------

.. math::
   :label: eq-allowance

   allowance = 30
""".strip(),
        encoding="utf-8",
    )

    document = RstParser(tmp_path).parse(rst_path, "docs/guide.rst")

    chunks, images = segment_to_chunks(document, max_words=80, overlap_words=10)

    assert document.metadata["chunking_strategy"] == "rst_section_window"
    assert document.metadata["structure_section_count"] == 2
    assert "chunking_hints" not in document.metadata
    assert len(chunks) == 2
    assert chunks[0].chunk_type == "figure_explainer_chunk"
    assert chunks[0].metadata["anchors"] == ["remote-work"]
    assert chunks[0].image_refs == ["docs/images/diagram.png"]
    assert "RST anchors: remote-work" in chunks[0].embedding_text
    assert "RST images: docs/images/diagram.png" in chunks[0].embedding_text
    assert chunks[1].chunk_type == "reference_entry_chunk"
    assert chunks[1].metadata["equation_labels"] == ["eq-allowance"]
    assert chunks[1].metadata["directive_types"] == ["math"]
    assert "RST equation labels: eq-allowance" in chunks[1].embedding_text
    assert len(images) == 1
    assert images[0].image_path == "docs/images/diagram.png"
