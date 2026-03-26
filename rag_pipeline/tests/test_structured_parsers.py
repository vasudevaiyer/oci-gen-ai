import json
from pathlib import Path

from openpyxl import Workbook

from backend.app.parsers.json_parser import JsonParser
from backend.app.parsers.xlsx_parser import XlsxParser


def test_json_parser_emits_blocks_and_segments(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"policy": {"owner": "security", "required": True}}), encoding="utf-8")

    document = JsonParser().parse(path, "sample.json")

    assert len(document.blocks) >= 2
    assert all(block.block_type == "paragraph" for block in document.blocks)
    assert any(segment.segment_type == "json_object" for segment in document.segments)
    assert any(block.metadata.get("json_path") == "$.policy" for block in document.blocks)


def test_xlsx_parser_emits_table_and_row_blocks(tmp_path: Path) -> None:
    path = tmp_path / "report.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Revenue"
    sheet.append(["Month", "Value"])
    sheet.append(["Jan", 10])
    sheet.append(["Feb", 12])
    workbook.save(path)

    document = XlsxParser().parse(path, "report.xlsx")

    assert any(block.block_type == "table" for block in document.blocks)
    assert any(block.block_type == "table_row" for block in document.blocks)
    assert any(segment.segment_type == "sheet_summary" for segment in document.segments)
    assert any(segment.segment_type == "table_row" for segment in document.segments)
