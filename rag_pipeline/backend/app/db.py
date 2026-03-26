from __future__ import annotations

import ast
import json
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from typing import Any

import oracledb

from .config import Settings
from .schemas import ChunkRecord, DocumentRecord, ImageRecord


class OracleVectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def connect(self):
        connection = oracledb.connect(
            user=self.settings.oracle_user,
            password=self.settings.oracle_password,
            dsn=self.settings.oracle_dsn,
            config_dir=str(self.settings.wallet_dir),
            wallet_location=str(self.settings.wallet_dir),
            wallet_password=self.settings.wallet_password,
        )
        try:
            yield connection
        finally:
            connection.close()

    def initialize_schema(self) -> None:
        statements = [statement.strip() for statement in self.settings.schema_path.read_text(encoding="utf-8").split(";") if statement.strip()]
        with self.connect() as connection:
            cursor = connection.cursor()
            for statement in statements:
                try:
                    cursor.execute(statement)
                except oracledb.DatabaseError as exc:
                    error_obj = exc.args[0]
                    if getattr(error_obj, "code", None) not in {955, 2261, 942, 2260}:
                        raise
            connection.commit()

    def upsert_document(self, document: DocumentRecord) -> None:
        sql = """
        merge into rp_documents target
        using (
            select :document_id document_id,
                   :source_path source_path,
                   :file_name file_name,
                   :file_type file_type,
                   :checksum checksum,
                   :title title,
                   :status status,
                   :language_tags language_tags,
                   :metadata metadata
            from dual
        ) source
        on (target.document_id = source.document_id)
        when matched then update set
            source_path = source.source_path,
            file_name = source.file_name,
            file_type = source.file_type,
            checksum = source.checksum,
            title = source.title,
            status = source.status,
            language_tags = source.language_tags,
            metadata = source.metadata,
            updated_at = current_timestamp
        when not matched then insert (
            document_id, source_path, file_name, file_type, checksum, title, status, language_tags, metadata
        ) values (
            source.document_id, source.source_path, source.file_name, source.file_type, source.checksum, source.title, source.status, source.language_tags, source.metadata
        )
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.setinputsizes(language_tags=oracledb.DB_TYPE_CLOB, metadata=oracledb.DB_TYPE_CLOB)
            cursor.execute(
                sql,
                {
                    "document_id": document.document_id,
                    "source_path": document.source_path,
                    "file_name": document.file_name,
                    "file_type": document.file_type,
                    "checksum": document.checksum,
                    "title": document.title,
                    "status": document.status,
                    "language_tags": json.dumps(document.language_tags, ensure_ascii=False),
                    "metadata": json.dumps(document.metadata, ensure_ascii=False),
                },
            )
            connection.commit()

    def replace_document_content(
        self,
        document: DocumentRecord,
        chunks: list[ChunkRecord],
        chunk_embeddings: list[list[float]],
        images: list[ImageRecord],
        image_embeddings: list[list[float]],
        *,
        embedding_model_id: str,
    ) -> None:
        self.upsert_document(document)
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute("delete from rp_image_embeddings where document_id = :document_id", {"document_id": document.document_id})
            cursor.execute("delete from rp_embeddings where document_id = :document_id", {"document_id": document.document_id})
            cursor.execute("delete from rp_images where document_id = :document_id", {"document_id": document.document_id})
            cursor.execute("delete from rp_chunks where document_id = :document_id", {"document_id": document.document_id})

            if chunks:
                cursor.setinputsizes(
                    section_path=oracledb.DB_TYPE_CLOB,
                    display_text=oracledb.DB_TYPE_CLOB,
                    embedding_text=oracledb.DB_TYPE_CLOB,
                    language_tags=oracledb.DB_TYPE_CLOB,
                    citation_anchor=oracledb.DB_TYPE_CLOB,
                    metadata=oracledb.DB_TYPE_CLOB,
                    image_refs=oracledb.DB_TYPE_CLOB,
                )
                cursor.executemany(
                    """
                    insert into rp_chunks (
                        chunk_id, document_id, source_path, file_type, chunk_type, title, section_path,
                        chunk_index, display_text, embedding_text, language_tags, citation_anchor,
                        parser_used, parser_confidence, metadata, image_refs
                    ) values (
                        :chunk_id, :document_id, :source_path, :file_type, :chunk_type, :title, :section_path,
                        :chunk_index, :display_text, :embedding_text, :language_tags, :citation_anchor,
                        :parser_used, :parser_confidence, :metadata, :image_refs
                    )
                    """,
                    [
                        {
                            "chunk_id": chunk.chunk_id,
                            "document_id": chunk.document_id,
                            "source_path": chunk.source_path,
                            "file_type": chunk.file_type,
                            "chunk_type": chunk.chunk_type,
                            "title": chunk.title,
                            "section_path": json.dumps(chunk.section_path, ensure_ascii=False),
                            "chunk_index": chunk.chunk_index,
                            "display_text": chunk.display_text,
                            "embedding_text": chunk.embedding_text,
                            "language_tags": json.dumps(chunk.language_tags, ensure_ascii=False),
                            "citation_anchor": json.dumps(_to_jsonable(chunk.citation_anchor), ensure_ascii=False),
                            "parser_used": chunk.parser_used,
                            "parser_confidence": chunk.parser_confidence,
                            "metadata": json.dumps(chunk.metadata, ensure_ascii=False),
                            "image_refs": json.dumps(chunk.image_refs, ensure_ascii=False),
                        }
                        for chunk in chunks
                    ],
                )
                cursor.executemany(
                    "insert into rp_embeddings (chunk_id, document_id, model_id, embedding) values (:chunk_id, :document_id, :model_id, to_vector(:embedding))",
                    [
                        {
                            "chunk_id": chunk.chunk_id,
                            "document_id": chunk.document_id,
                            "model_id": embedding_model_id,
                            "embedding": _vector_literal(embedding),
                        }
                        for chunk, embedding in zip(chunks, chunk_embeddings, strict=True)
                    ],
                )

            if images:
                cursor.setinputsizes(
                    caption_text=oracledb.DB_TYPE_CLOB,
                    related_section_path=oracledb.DB_TYPE_CLOB,
                    language_tags=oracledb.DB_TYPE_CLOB,
                    citation_anchor=oracledb.DB_TYPE_CLOB,
                    metadata=oracledb.DB_TYPE_CLOB,
                )
                cursor.executemany(
                    """
                    insert into rp_images (
                        image_id, document_id, source_path, image_path, title, caption_text,
                        related_section_path, related_chunk_id, language_tags, citation_anchor, metadata
                    ) values (
                        :image_id, :document_id, :source_path, :image_path, :title, :caption_text,
                        :related_section_path, :related_chunk_id, :language_tags, :citation_anchor, :metadata
                    )
                    """,
                    [
                        {
                            "image_id": image.image_id,
                            "document_id": image.document_id,
                            "source_path": image.source_path,
                            "image_path": image.image_path,
                            "title": image.title,
                            "caption_text": image.caption_text,
                            "related_section_path": json.dumps(image.related_section_path, ensure_ascii=False),
                            "related_chunk_id": image.related_chunk_id,
                            "language_tags": json.dumps(image.language_tags, ensure_ascii=False),
                            "citation_anchor": json.dumps(_to_jsonable(image.citation_anchor), ensure_ascii=False),
                            "metadata": json.dumps(image.metadata, ensure_ascii=False),
                        }
                        for image in images
                    ],
                )
                cursor.executemany(
                    "insert into rp_image_embeddings (image_id, document_id, model_id, embedding) values (:image_id, :document_id, :model_id, to_vector(:embedding))",
                    [
                        {
                            "image_id": image.image_id,
                            "document_id": image.document_id,
                            "model_id": embedding_model_id,
                            "embedding": _vector_literal(embedding),
                        }
                        for image, embedding in zip(images, image_embeddings, strict=True)
                    ],
                )
            connection.commit()

    def list_documents(self) -> list[dict[str, Any]]:
        sql = "select document_id, source_path, file_name, file_type, title, status, language_tags, metadata from rp_documents order by updated_at desc"
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            return [
                {
                    "document_id": row[0],
                    "source_path": row[1],
                    "file_name": row[2],
                    "file_type": row[3],
                    "title": row[4],
                    "status": row[5],
                    "language_tags": _load_json_list(row[6]),
                    "metadata": _load_json_object(row[7]),
                }
                for row in cursor.fetchall()
            ]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        sql = "select document_id, source_path, file_name, file_type, title, status, language_tags, metadata from rp_documents where document_id = :document_id"
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, {"document_id": document_id})
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "document_id": row[0],
                "source_path": row[1],
                "file_name": row[2],
                "file_type": row[3],
                "title": row[4],
                "status": row[5],
                "language_tags": _load_json_list(row[6]),
                "metadata": _load_json_object(row[7]),
            }

    def document_counts(self, document_id: str) -> dict[str, int]:
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute("select count(*) from rp_chunks where document_id = :document_id", {"document_id": document_id})
            chunk_count = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from rp_images where document_id = :document_id", {"document_id": document_id})
            image_count = int(cursor.fetchone()[0])
        return {"chunks": chunk_count, "images": image_count}

    def delete_document(self, document_id: str) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute("delete from rp_documents where document_id = :document_id", {"document_id": document_id})
            connection.commit()

    def query_chunks(self, query_embedding: list[float], top_k: int, *, file_types: list[str] | None = None) -> list[dict[str, Any]]:
        filters = ""
        bind_vars: dict[str, Any] = {"embedding": _vector_literal(query_embedding)}
        if file_types:
            placeholders = []
            for index, file_type in enumerate(file_types):
                key = f"file_type_{index}"
                placeholders.append(f":{key}")
                bind_vars[key] = file_type
            filters = f"where c.file_type in ({', '.join(placeholders)})"
        sql = f"""
            select
                c.chunk_id,
                c.document_id,
                c.source_path,
                c.title,
                c.section_path as section_path_json,
                c.display_text as display_text_value,
                c.chunk_type,
                c.image_refs as image_refs_json,
                c.metadata as metadata_json,
                1 - vector_distance(e.embedding, to_vector(:embedding), COSINE) as score
            from rp_chunks c
            join rp_embeddings e on e.chunk_id = c.chunk_id
            {filters}
            order by vector_distance(e.embedding, to_vector(:embedding), COSINE)
            fetch first {int(top_k)} rows only
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, bind_vars)
            results = []
            for row in cursor.fetchall():
                section_path = _load_json_list(row[4])
                results.append(
                    {
                        "chunk_id": row[0],
                        "document_id": row[1],
                        "source_path": row[2],
                        "title": row[3],
                        "section_path": section_path,
                        "content": _read_clob(row[5]) or "",
                        "chunk_type": row[6],
                        "image_refs": _load_json_list(row[7]),
                        "metadata": _load_json_object(row[8]),
                        "score": float(row[9]),
                    }
                )
            return results

    def query_images(self, query_embedding: list[float], top_k: int, *, file_types: list[str] | None = None) -> list[dict[str, Any]]:
        filters = ""
        bind_vars: dict[str, Any] = {"embedding": _vector_literal(query_embedding)}
        if file_types:
            placeholders = []
            for index, file_type in enumerate(file_types):
                key = f"file_type_{index}"
                placeholders.append(f":{key}")
                bind_vars[key] = file_type
            filters = f"where d.file_type in ({', '.join(placeholders)})"
        sql = f"""
            select
                i.image_id,
                i.document_id,
                i.related_chunk_id,
                i.image_path,
                i.caption_text as caption_text_value,
                i.source_path,
                i.related_section_path as section_path_json,
                1 - vector_distance(e.embedding, to_vector(:embedding), COSINE) as score
            from rp_images i
            join rp_image_embeddings e on e.image_id = i.image_id
            join rp_documents d on d.document_id = i.document_id
            {filters}
            order by vector_distance(e.embedding, to_vector(:embedding), COSINE)
            fetch first {int(top_k)} rows only
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, bind_vars)
            return [
                {
                    "image_id": row[0],
                    "document_id": row[1],
                    "related_chunk_id": row[2],
                    "image_path": row[3],
                    "caption_text": _read_clob(row[4]) or "",
                    "source_path": row[5],
                    "section_path": _load_json_list(row[6]),
                    "score": float(row[7]),
                }
                for row in cursor.fetchall()
            ]

    def corpus_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            cursor = connection.cursor()
            counts = {}
            for table_name, label in (("rp_documents", "documents"), ("rp_chunks", "chunks"), ("rp_images", "images")):
                try:
                    cursor.execute(f"select count(*) from {table_name}")
                    counts[label] = int(cursor.fetchone()[0])
                except oracledb.DatabaseError:
                    counts[label] = 0
            try:
                cursor.execute("select count(distinct document_id) from rp_embeddings")
                counts["indexed_documents"] = int(cursor.fetchone()[0])
            except oracledb.DatabaseError:
                counts["indexed_documents"] = 0
        return counts

    def log_query(self, query_text: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "insert into rp_query_log (query_text, request_payload, response_payload) values (:query_text, :request_payload, :response_payload)",
                {
                    "query_text": query_text,
                    "request_payload": json.dumps(request_payload, ensure_ascii=False),
                    "response_payload": json.dumps(response_payload, ensure_ascii=False),
                },
            )
            connection.commit()


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ", ".join(f"{value:.9f}" for value in embedding) + "]"


def _read_clob(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, oracledb.LOB):
        return value.read()
    return str(value)


def _load_json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, type(default)):
        return value

    raw = _read_clob(value)
    if raw is None:
        return default

    text = raw.strip()
    if not text:
        return default

    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, type(default)):
            return parsed
    return default


def _load_json_list(value: Any) -> list[Any]:
    parsed = _load_json_value(value, [])
    return parsed if isinstance(parsed, list) else []


def _load_json_object(value: Any) -> dict[str, Any]:
    parsed = _load_json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value
