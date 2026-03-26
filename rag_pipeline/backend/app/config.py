from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EXTRACTED_IMAGES_DIR = DATA_DIR / "extracted_images"

load_dotenv(ROOT_DIR / ".env")



def _oci_config_default(option: str, fallback: str = "") -> str:
    config_path = Path(os.getenv("OCI_CONFIG_PATH", "/home/opc/.oci/config"))
    profile = os.getenv("OCI_PROFILE", "DEFAULT")
    if not config_path.exists():
        return fallback
    parser = configparser.ConfigParser()
    parser.read(config_path)
    if not parser.has_section(profile):
        return fallback
    return parser.get(profile, option, fallback=fallback).strip().strip('"')


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "OCI Multi-Format RAG Pipeline")
    root_dir: Path = ROOT_DIR
    data_dir: Path = Path(os.getenv("DATA_DIR", str(DATA_DIR)))
    uploads_dir: Path = Path(os.getenv("UPLOADS_DIR", str(UPLOADS_DIR)))
    extracted_images_dir: Path = Path(os.getenv("EXTRACTED_IMAGES_DIR", str(EXTRACTED_IMAGES_DIR)))
    wallet_dir: Path = Path(os.getenv("ORACLE_WALLET_DIR", "/home/opc/wallet"))
    oracle_user: str = os.getenv("ORACLE_USER", "")
    oracle_password: str = os.getenv("ORACLE_PASSWORD", "")
    oracle_dsn: str = os.getenv("ORACLE_DSN", "genaivasuatp_high")
    wallet_password: str = os.getenv("ORACLE_WALLET_PASSWORD", "")
    oci_config_path: Path = Path(os.getenv("OCI_CONFIG_PATH", "/home/opc/.oci/config"))
    oci_profile: str = os.getenv("OCI_PROFILE", "DEFAULT")
    oci_compartment_id: str = os.getenv("OCI_COMPARTMENT_OCID", _oci_config_default("OCI_COMPARTMENT_OCID", ""))
    oci_endpoint: str = os.getenv(
        "OCI_GENAI_ENDPOINT",
        _oci_config_default(
            "OCI_GENAI_ENDPOINT",
            "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
        ),
    )
    embedding_model_id: str = os.getenv("OCI_EMBED_MODEL_ID", "cohere.embed-v4.0")
    chat_model_id: str = os.getenv("OCI_CHAT_MODEL_ID", "cohere.command-a-03-2025")
    vision_model_id: str = os.getenv("OCI_VISION_MODEL_ID", "cohere.command-a-vision")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    max_chunk_words: int = int(os.getenv("MAX_CHUNK_WORDS", "220"))
    chunk_overlap_words: int = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))
    max_context_chunks: int = int(os.getenv("MAX_CONTEXT_CHUNKS", "6"))
    max_context_images: int = int(os.getenv("MAX_CONTEXT_IMAGES", "4"))
    max_eager_image_captions: int = int(os.getenv("MAX_EAGER_IMAGE_CAPTIONS", "12"))
    min_indexed_image_width: int = int(os.getenv("MIN_INDEXED_IMAGE_WIDTH", "120"))
    min_indexed_image_height: int = int(os.getenv("MIN_INDEXED_IMAGE_HEIGHT", "48"))
    min_indexed_image_area: int = int(os.getenv("MIN_INDEXED_IMAGE_AREA", "12000"))
    repeated_image_occurrence_threshold: int = int(os.getenv("REPEATED_IMAGE_OCCURRENCE_THRESHOLD", "5"))
    repeated_image_max_area: int = int(os.getenv("REPEATED_IMAGE_MAX_AREA", "90000"))
    pdf_render_dpi: int = int(os.getenv("PDF_RENDER_DPI", "144"))
    max_pdf_visual_pages: int = int(os.getenv("MAX_PDF_VISUAL_PAGES", "8"))
    min_pdf_drawing_count: int = int(os.getenv("MIN_PDF_DRAWING_COUNT", "25"))
    supported_extensions: tuple[str, ...] = (
        ".pdf",
        ".docx",
        ".ppt",
        ".pptx",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".xls",
        ".xlsx",
        ".txt",
        ".json",
        ".rst",
    )

    @property
    def schema_path(self) -> Path:
        return self.root_dir / "backend" / "app" / "sql" / "schema.sql"

    @property
    def runtime_python(self) -> Path:
        return Path("/u01/venv/bin/python")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
