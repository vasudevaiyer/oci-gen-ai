from pathlib import Path

from backend.app.parsers.rst_parser import RstParser


def test_rst_parser_extracts_code_blocks_images_and_chunking_hints(tmp_path: Path) -> None:
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image_path = images_dir / "diagram.png"
    image_path.write_bytes(b"fake")

    rst_path = tmp_path / "guide.rst"
    rst_path.write_text(
        """
Guide Title
===========

.. figure:: images/diagram.png
   :alt: Recovery architecture diagram

   Recovery flow between primary and standby regions.

.. code-block:: python

   print('hello')
   value = 50
""".strip(),
        encoding="utf-8",
    )

    parser = RstParser(tmp_path)
    document = parser.parse(rst_path, "guide.rst")

    assert any(segment.segment_type == "code_block" for segment in document.segments)
    assert any(segment.segment_type == "image_caption" for segment in document.segments)
    assert any(block.block_type == "heading" for block in document.blocks)
    assert any(block.block_type == "code" for block in document.blocks)
    assert any(block.block_type == "caption" for block in document.blocks)
    assert len(document.images) == 1
    assert document.images[0].alt_text == "Recovery architecture diagram"
    assert document.images[0].caption == "Recovery flow between primary and standby regions."
    assert document.images[0].image_path.endswith("images/diagram.png")
    assert document.metadata["document_structure"] == "rst_sections"
    assert document.metadata["chunking_hints"]["preferred_strategy"] == "rst_section_window"
    assert document.metadata["chunking_hints"]["section_count"] == 1


def test_rst_parser_extracts_section_level_chunking_hints(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    rst_path = docs_dir / "guide.rst"
    rst_path.write_text(
        """
Guide Title
===========

.. _remote-work:

Remote work details with :math:`n + 1`.

Policy Notes
------------

.. math::
   :label: eq-allowance

   allowance = 30
""".strip(),
        encoding="utf-8",
    )

    document = RstParser(tmp_path).parse(rst_path, "docs/guide.rst")

    sections = document.metadata["chunking_hints"]["sections"]
    assert len(sections) == 2
    assert sections[0]["section_path"] == ["Guide Title"]
    assert sections[0]["blocks"][0]["anchors"] == ["remote-work"]
    assert sections[0]["blocks"][0]["inline_math_count"] == 0
    assert sections[0]["blocks"][1]["inline_math_count"] == 1
    assert sections[1]["section_path"] == ["Guide Title", "Policy Notes"]
    assert sections[1]["blocks"][0]["equation_labels"] == ["eq-allowance"]
    assert sections[1]["blocks"][0]["directive_types"] == ["math"]
