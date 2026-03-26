from pathlib import Path

from backend.app.parsers.text_parser import TextParser


def test_text_parser_detects_underlined_headings_and_sections(tmp_path: Path) -> None:
    path = tmp_path / "guide.txt"
    path.write_text(
        """
Remote Work
===========

Employees may request remote work with manager approval.

Eligibility
-----------

Up to 30 days per year are allowed.
""".strip(),
        encoding="utf-8",
    )

    document = TextParser().parse(path, "guide.txt")

    assert document.metadata["document_structure"] == "line_sections"
    assert document.metadata["chunking_hints"]["section_count"] == 2
    paragraph_blocks = [block for block in document.blocks if block.block_type == "paragraph"]
    assert paragraph_blocks[0].section_path == [document.title, "Remote Work"]
    assert paragraph_blocks[1].section_path == [document.title, "Eligibility"]
