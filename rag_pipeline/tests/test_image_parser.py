from pathlib import Path

from backend.app.parsers.image_parser import ImageFileParser


class _FakeGenAi:
    def extract_image_structure(self, image_path: Path) -> dict[str, object]:
        return {
            "image_type": "diagram",
            "title": "Physical Architecture",
            "summary": "Architecture diagram showing OCI services and data flow.",
            "visible_text": ["Physical Architecture", "OCI Generative AI", "ATP"],
            "sections": [
                {
                    "heading": "Components",
                    "block_type": "list_item",
                    "content": "OCI Generative AI, APEX UI, ATP, Integration Cloud",
                },
                {
                    "heading": "Flow",
                    "block_type": "paragraph",
                    "content": "Users interact with APEX, which calls services that store data in ATP.",
                },
            ],
        }


def test_image_parser_emits_structured_blocks_and_segments(tmp_path: Path) -> None:
    image_path = tmp_path / "physical-architecture.png"
    image_path.write_bytes(b"fakepng")

    document = ImageFileParser(tmp_path, _FakeGenAi()).parse(image_path, "physical-architecture.png")

    assert document.file_type == "png"
    assert document.parser_used == "image_parser"
    assert document.metadata["document_structure"] == "image_analysis"
    assert document.metadata["image_type"] == "diagram"
    assert len(document.images) == 1
    assert document.images[0].image_path == "physical-architecture.png"
    assert any(block.block_type == "figure" for block in document.blocks)
    assert any(block.block_type == "note" for block in document.blocks)
    assert any(block.block_type == "list_item" for block in document.blocks)
    assert any(segment.segment_type == "image_caption" for segment in document.segments)
    assert any(segment.title == "Flow" for segment in document.segments)


def test_image_parser_falls_back_without_vision_structure(tmp_path: Path) -> None:
    image_path = tmp_path / "simple-screen.png"
    image_path.write_bytes(b"fakepng")

    document = ImageFileParser(tmp_path, genai=None).parse(image_path, "simple-screen.png")

    assert len(document.images) == 1
    assert document.metadata["image_type"] == "unknown"
    assert document.blocks[0].block_type == "figure"
    assert document.segments[0].segment_type == "image_caption"
    assert "Image file" in document.blocks[0].text
