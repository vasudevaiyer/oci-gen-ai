from __future__ import annotations

from ..config import Settings
from .base import UnsupportedDocumentError
from .docx_parser import DocxParser
from .image_parser import ImageFileParser
from .json_parser import JsonParser
from .pdf_parser import PdfParser
from .pptx_parser import PptxParser
from .rst_parser import RstParser
from .text_parser import TextParser
from .xlsx_parser import XlsxParser


class ParserRouter:
    def __init__(self, settings: Settings, genai=None) -> None:
        self.settings = settings
        self.parsers = {
            ".pdf": PdfParser(settings),
            ".docx": DocxParser(settings.extracted_images_dir, settings.root_dir),
            ".ppt": PptxParser(settings.extracted_images_dir, settings.root_dir),
            ".pptx": PptxParser(settings.extracted_images_dir, settings.root_dir),
            ".png": ImageFileParser(settings.root_dir, genai),
            ".jpg": ImageFileParser(settings.root_dir, genai),
            ".jpeg": ImageFileParser(settings.root_dir, genai),
            ".webp": ImageFileParser(settings.root_dir, genai),
            ".gif": ImageFileParser(settings.root_dir, genai),
            ".bmp": ImageFileParser(settings.root_dir, genai),
            ".tif": ImageFileParser(settings.root_dir, genai),
            ".tiff": ImageFileParser(settings.root_dir, genai),
            ".xls": XlsxParser(),
            ".xlsx": XlsxParser(),
            ".txt": TextParser(),
            ".json": JsonParser(),
            ".rst": RstParser(settings.root_dir),
        }

    def parse(self, path, relative_path: str):
        suffix = path.suffix.lower()
        parser = self.parsers.get(suffix)
        if parser is None:
            raise UnsupportedDocumentError(f"Unsupported file type: {suffix}")
        return parser.parse(path, relative_path)
