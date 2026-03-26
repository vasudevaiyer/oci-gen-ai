from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from backend.app.ingestion import IngestionManager
from backend.app.schemas import BlockRecord, CitationAnchor, ImageContext, NormalizedDocument, NormalizedSegment


def _manager(tmp_path: Path, **overrides):
    manager = IngestionManager.__new__(IngestionManager)
    manager.settings = SimpleNamespace(
        root_dir=tmp_path,
        min_indexed_image_width=overrides.get('min_indexed_image_width', 120),
        min_indexed_image_height=overrides.get('min_indexed_image_height', 48),
        min_indexed_image_area=overrides.get('min_indexed_image_area', 12000),
        repeated_image_occurrence_threshold=overrides.get('repeated_image_occurrence_threshold', 3),
        repeated_image_max_area=overrides.get('repeated_image_max_area', 90000),
    )
    return manager


def _image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size, color=color).save(path)


def test_prune_document_images_removes_repeated_small_assets(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    repeated_paths = []
    for index in range(3):
        path = tmp_path / 'data' / f'repeated-{index}.png'
        _image(path, (518, 144), (12, 34, 56))
        repeated_paths.append(path)
    kept_path = tmp_path / 'data' / 'kept.png'
    _image(kept_path, (1200, 800), (90, 120, 180))

    repeated_images = [
        ImageContext(image_id=f'repeated-{index}', image_path=str(path.relative_to(tmp_path)), related_section_path='Page 1')
        for index, path in enumerate(repeated_paths)
    ]
    kept_image = ImageContext(image_id='kept', image_path=str(kept_path.relative_to(tmp_path)), related_section_path='Architecture')

    document = NormalizedDocument(
        document_id='doc-1',
        source_path='data/uploads/policy.pdf',
        file_name='policy.pdf',
        file_type='pdf',
        title='Policy',
        checksum='checksum',
        blocks=[
            BlockRecord(
                block_id='b1',
                block_type='figure',
                text='',
                order_index=0,
                title='Page 1',
                section_path=['Policy', 'Page 1'],
                citation_anchor=CitationAnchor(page_number=1, source_label='page 1'),
                image_contexts=[*repeated_images, kept_image],
            )
        ],
        segments=[
            NormalizedSegment(
                segment_id='s1',
                segment_type='image_caption',
                text='Architecture figure',
                title='Page 1',
                section_path=['Policy', 'Page 1'],
                citation_anchor=CitationAnchor(page_number=1, source_label='page 1'),
                image_contexts=[*repeated_images, kept_image],
            )
        ],
        images=[*repeated_images, kept_image],
    )

    manager._prune_document_images(document)

    assert [image.image_id for image in document.images] == ['kept']
    assert [image.image_id for image in document.blocks[0].image_contexts] == ['kept']
    assert [image.image_id for image in document.segments[0].image_contexts] == ['kept']
    assert document.metadata['image_filtering']['removed'] == 3
    assert document.metadata['image_filtering']['removed_reasons'] == {'repeated_small_asset': 3}
    assert not any(path.exists() for path in repeated_paths)
    assert kept_path.exists()


def test_prune_document_images_removes_tiny_images_and_empty_figure_blocks(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    tiny_path = tmp_path / 'data' / 'tiny.png'
    _image(tiny_path, (105, 23), (1, 2, 3))
    tiny_image = ImageContext(image_id='tiny', image_path=str(tiny_path.relative_to(tmp_path)), related_section_path='Page 2')

    document = NormalizedDocument(
        document_id='doc-2',
        source_path='data/uploads/policy.docx',
        file_name='policy.docx',
        file_type='docx',
        title='Policy',
        checksum='checksum',
        blocks=[
            BlockRecord(
                block_id='h1',
                block_type='heading',
                text='Policy',
                order_index=0,
                title='Policy',
                section_path=['Policy'],
                citation_anchor=CitationAnchor(source_label='Policy'),
            ),
            BlockRecord(
                block_id='f1',
                block_type='figure',
                text='',
                order_index=1,
                title='Page 2',
                section_path=['Policy', 'Page 2'],
                citation_anchor=CitationAnchor(page_number=2, source_label='page 2'),
                image_contexts=[tiny_image],
            ),
        ],
        segments=[
            NormalizedSegment(
                segment_id='seg-1',
                segment_type='image_caption',
                text='',
                title='Page 2',
                section_path=['Policy', 'Page 2'],
                citation_anchor=CitationAnchor(page_number=2, source_label='page 2'),
                image_contexts=[tiny_image],
            )
        ],
        images=[tiny_image],
    )

    manager._prune_document_images(document)

    assert document.images == []
    assert [block.block_id for block in document.blocks] == ['h1']
    assert document.segments == []
    assert document.metadata['image_filtering']['removed_reasons'] == {'too_small': 1}
    assert not tiny_path.exists()
