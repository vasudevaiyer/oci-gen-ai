from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "extract_docs_code-aster"
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
    app_name: str = os.getenv("APP_NAME", "Code Aster OCI RAG")
    data_dir: Path = Path(os.getenv("DATA_DIR", str(DATA_DIR)))
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
    chunk_overlap_words: int = int(os.getenv("CHUNK_OVERLAP_WORDS", "35"))
    max_context_chunks: int = int(os.getenv("MAX_CONTEXT_CHUNKS", "6"))
    max_context_images: int = int(os.getenv("MAX_CONTEXT_IMAGES", "3"))

    @property
    def static_mount_dir(self) -> Path:
        return self.data_dir

    @property
    def frontend_dist_dir(self) -> Path:
        return ROOT_DIR / "frontend" / "dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
