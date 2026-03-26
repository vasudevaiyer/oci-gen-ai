from pathlib import Path
from types import SimpleNamespace

from backend.app.ingestion import IngestionManager
from backend.app.schemas import ImageContext, NormalizedDocument, NormalizedSegment


class _FakeGenAi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def caption_image(self, image_path: Path, *, context_hint: str = "") -> str:
        self.calls.append((image_path.name, context_hint))
        return f"caption:{image_path.name}"


def test_hydrate_image_captions_caps_vision_calls_and_keeps_fallback(tmp_path: Path) -> None:
    images = []
    for index in range(3):
        image_path = tmp_path / f"img-{index}.png"
        image_path.write_bytes(b"png")
        images.append(
            ImageContext(
                image_id=f"img-{index}",
                image_path=image_path.name,
                related_section_path=f"Page {index + 1}",
            )
        )

    document = NormalizedDocument(
        document_id="doc-1",
        source_path="data/uploads/doc.pdf",
        file_name="doc.pdf",
        file_type="pdf",
        title="doc",
        checksum="checksum",
        images=images,
        segments=[
            NormalizedSegment(
                segment_id="seg-1",
                segment_type="paragraph",
                text="hello",
                image_contexts=images,
            )
        ],
    )

    manager = IngestionManager.__new__(IngestionManager)
    manager.settings = SimpleNamespace(root_dir=tmp_path, max_eager_image_captions=2)
    manager.genai = _FakeGenAi()

    manager._hydrate_image_captions(document)

    assert manager.genai.calls == [("img-0.png", "Page 1"), ("img-1.png", "Page 2")]
    assert document.images[0].caption == "caption:img-0.png"
    assert document.images[1].caption == "caption:img-1.png"
    assert document.images[2].caption == "Image from Page 3"
