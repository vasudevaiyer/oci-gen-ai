from __future__ import annotations

import json
from pathlib import Path

from .base import detect_languages, make_document, normalize_text, serialize_json
from ..schemas import BlockRecord, CitationAnchor, NormalizedSegment


class JsonParser:
    parser_name = "json_parser"

    def parse(self, path: Path, relative_path: str):
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        document = make_document(path, relative_path, "json", parser_used=self.parser_name)
        blocks: list[BlockRecord] = []
        segments: list[NormalizedSegment] = []
        for index, item in enumerate(_flatten_payload(payload)):
            json_path, content = item
            normalized = normalize_text(content)
            if not normalized:
                continue
            anchor = CitationAnchor(json_path=json_path, source_label=json_path)
            blocks.append(
                BlockRecord(
                    block_id=f"{document.document_id}-block-{index}",
                    block_type="paragraph",
                    text=normalized,
                    order_index=len(blocks),
                    title=document.title,
                    section_path=[document.title, json_path],
                    citation_anchor=anchor,
                    metadata={"json_path": json_path},
                )
            )
            segments.append(
                NormalizedSegment(
                    segment_id=f"{document.document_id}-seg-{index}",
                    segment_type="json_object",
                    text=normalized,
                    title=document.title,
                    section_path=[document.title, json_path],
                    citation_anchor=anchor,
                    metadata={"json_path": json_path},
                )
            )
        document.blocks = blocks
        document.segments = segments
        document.language_tags = detect_languages(block.text for block in blocks)
        for block in document.blocks:
            block.language_tags = document.language_tags
        for segment in document.segments:
            segment.language_tags = document.language_tags
        return document



def _flatten_payload(payload: object, path: str = "$"):
    if isinstance(payload, dict):
        text = "\n".join(f"{key}: {_scalar_repr(value)}" for key, value in payload.items() if not isinstance(value, (dict, list)))
        if text:
            yield path, text
        for key, value in payload.items():
            yield from _flatten_payload(value, f"{path}.{key}")
    elif isinstance(payload, list):
        if payload and all(not isinstance(item, (dict, list)) for item in payload):
            yield path, ", ".join(_scalar_repr(item) for item in payload)
        for index, value in enumerate(payload):
            yield from _flatten_payload(value, f"{path}[{index}]")
    else:
        yield path, _scalar_repr(payload)



def _scalar_repr(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    return serialize_json(value)
