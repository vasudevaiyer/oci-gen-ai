import zipfile
from pathlib import Path

from backend.app.parsers.docx_parser import DocxParser


def test_docx_parser_extracts_embedded_images(tmp_path: Path) -> None:
    docx_path = tmp_path / "sample.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>Architecture overview</w:t></w:r>
      <w:r><w:drawing><a:graphic><a:graphicData><a:blip r:embed="rIdImage1"/></a:graphicData></a:graphic></w:drawing></w:r>
    </w:p>
  </w:body>
</w:document>
""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>
""",
        )
        archive.writestr("word/media/image1.png", b"fakepng")

    parser = DocxParser(tmp_path / "images", tmp_path)
    document = parser.parse(docx_path, "sample.docx")

    assert len(document.images) == 1
    assert len(document.segments) == 1
    assert len(document.blocks) == 1
    assert document.blocks[0].block_type == "paragraph"
    assert len(document.segments[0].image_contexts) == 1
    assert len(document.blocks[0].image_contexts) == 1
    assert document.images[0].image_path.endswith("image1.png")
    assert document.metadata["document_structure"] == "hierarchical_sections"


def test_docx_parser_preserves_heading_hierarchy_in_section_paths(tmp_path: Path) -> None:
    docx_path = tmp_path / "sample.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Remote Work</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading2"/></w:pPr>
      <w:r><w:t>Eligibility</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Employees may request remote work with manager approval.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
""",
        )

    document = DocxParser(tmp_path / "images", tmp_path).parse(docx_path, "sample.docx")

    paragraph_block = next(block for block in document.blocks if block.block_type == "paragraph")
    assert paragraph_block.section_path == [document.title, "Remote Work", "Eligibility"]
    assert paragraph_block.title == "Eligibility"

    sections = document.metadata["chunking_hints"]["sections"]
    assert sections[0]["section_path"] == [document.title, "Remote Work"]
    assert sections[1]["section_path"] == [document.title, "Remote Work", "Eligibility"]
    assert document.metadata["chunking_hints"]["section_count"] == 2
