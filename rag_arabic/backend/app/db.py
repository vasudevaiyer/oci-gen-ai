from __future__ import annotations

import json
from contextlib import contextmanager

import oracledb

from .config import Settings
from .schemas import ChunkRecord, ImageRecord


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
        vector_dim = self.settings.embedding_dimensions
        chunk_table = self.settings.chunk_table_name
        image_table = self.settings.image_table_name
        statements = [
            f"""
            create table {chunk_table} (
                chunk_id number generated always as identity primary key,
                source_path varchar2(1024) not null,
                doc_code varchar2(128) not null,
                title varchar2(512) not null,
                section_path varchar2(2000) not null,
                chunk_index number not null,
                content clob not null,
                retrieval_text clob not null,
                anchors clob,
                image_refs clob,
                equation_labels clob,
                metadata clob,
                embedding vector({vector_dim}, float32),
                created_at timestamp default current_timestamp,
                constraint {chunk_table}_meta_json check (metadata is json)
            )
            """,
            f"create unique index {chunk_table}_uk on {chunk_table} (source_path, chunk_index)",
            f"""
            create table {image_table} (
                image_id number generated always as identity primary key,
                image_path varchar2(1024) not null,
                doc_code varchar2(128) not null,
                title varchar2(512) not null,
                caption_text clob not null,
                related_source_path varchar2(1024) not null,
                related_section_path varchar2(2000) not null,
                related_chunk_index number not null,
                metadata clob,
                embedding vector({vector_dim}, float32),
                created_at timestamp default current_timestamp,
                constraint {image_table}_meta_json check (metadata is json)
            )
            """,
            f"create unique index {image_table}_uk on {image_table} (image_path)",
        ]

        with self.connect() as connection:
            cursor = connection.cursor()
            for statement in statements:
                try:
                    cursor.execute(statement)
                except oracledb.DatabaseError as exc:
                    error_obj = exc.args[0]
                    if getattr(error_obj, "code", None) not in {955, 2261}:
                        raise
            connection.commit()

    def rebuild(self, chunks: list[ChunkRecord], embeddings: list[list[float]], images: list[ImageRecord], image_embeddings: list[list[float]]) -> None:
        chunk_table = self.settings.chunk_table_name
        image_table = self.settings.image_table_name
        with self.connect() as connection:
            cursor = connection.cursor()
            for table_name in (image_table, chunk_table):
                try:
                    cursor.execute(f"truncate table {table_name}")
                except oracledb.DatabaseError:
                    cursor.execute(f"delete from {table_name}")

            cursor.executemany(
                f"""
                insert into {chunk_table} (
                    source_path, doc_code, title, section_path, chunk_index, embedding,
                    content, retrieval_text, anchors, image_refs, equation_labels, metadata
                ) values (
                    :source_path, :doc_code, :title, :section_path, :chunk_index, to_vector(:embedding),
                    :content, :retrieval_text, :anchors, :image_refs, :equation_labels, :metadata
                )
                """,
                [
                    {
                        "source_path": chunk.source_path,
                        "doc_code": chunk.doc_code,
                        "title": chunk.title,
                        "section_path": chunk.section_path,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "retrieval_text": chunk.retrieval_text,
                        "anchors": json.dumps(chunk.anchors, ensure_ascii=False),
                        "image_refs": json.dumps(chunk.image_refs, ensure_ascii=False),
                        "equation_labels": json.dumps(chunk.equation_labels, ensure_ascii=False),
                        "metadata": json.dumps(
                            {
                                "source_path": chunk.source_path,
                                "doc_code": chunk.doc_code,
                                "section_path": chunk.section_path,
                            },
                            ensure_ascii=False,
                        ),
                        "embedding": _vector_literal(embedding),
                    }
                    for chunk, embedding in zip(chunks, embeddings, strict=True)
                ],
            )
            cursor.executemany(
                f"""
                insert into {image_table} (
                    image_path, doc_code, title, related_source_path,
                    related_section_path, related_chunk_index, embedding, caption_text, metadata
                ) values (
                    :image_path, :doc_code, :title, :related_source_path,
                    :related_section_path, :related_chunk_index, to_vector(:embedding), :caption_text, :metadata
                )
                """,
                [
                    {
                        "image_path": image.image_path,
                        "doc_code": image.doc_code,
                        "title": image.title,
                        "caption_text": image.caption_text,
                        "related_source_path": image.related_source_path,
                        "related_section_path": image.related_section_path,
                        "related_chunk_index": image.related_chunk_index,
                        "metadata": json.dumps(
                            {
                                "image_path": image.image_path,
                                "related_source_path": image.related_source_path,
                                "related_section_path": image.related_section_path,
                            },
                            ensure_ascii=False,
                        ),
                        "embedding": _vector_literal(embedding),
                    }
                    for image, embedding in zip(images, image_embeddings, strict=True)
                ],
            )
            connection.commit()

    def query_chunks(self, query_embedding: list[float], top_k: int) -> list[dict]:
        chunk_table = self.settings.chunk_table_name
        sql = f"""
            select
                source_path,
                title,
                section_path,
                dbms_lob.substr(content, 4000, 1) as content_text,
                dbms_lob.substr(image_refs, 4000, 1) as image_refs_text,
                1 - vector_distance(embedding, to_vector(:embedding), COSINE) as score
            from {chunk_table}
            order by vector_distance(embedding, to_vector(:embedding), COSINE)
            fetch first {int(top_k)} rows only
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, {"embedding": _vector_literal(query_embedding)})
            rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "source_path": row[0],
                    "title": row[1],
                    "section_path": row[2],
                    "content": row[3] or "",
                    "image_refs": json.loads((row[4] or "[]")),
                    "score": float(row[5]),
                }
            )
        return results

    def query_images(self, query_embedding: list[float], top_k: int) -> list[dict]:
        image_table = self.settings.image_table_name
        sql = f"""
            select
                image_path,
                dbms_lob.substr(caption_text, 4000, 1) as caption_text_value,
                related_source_path,
                related_section_path,
                1 - vector_distance(embedding, to_vector(:embedding), COSINE) as score
            from {image_table}
            order by vector_distance(embedding, to_vector(:embedding), COSINE)
            fetch first {int(top_k)} rows only
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, {"embedding": _vector_literal(query_embedding)})
            rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "image_path": row[0],
                    "caption_text": row[1] or "",
                    "source_path": row[2],
                    "section_path": row[3],
                    "score": float(row[4]),
                }
            )
        return results

    def corpus_counts(self) -> dict[str, int]:
        chunk_table = self.settings.chunk_table_name
        image_table = self.settings.image_table_name
        with self.connect() as connection:
            cursor = connection.cursor()
            counts = {}
            for table_name, label in ((chunk_table, "chunks"), (image_table, "images")):
                try:
                    cursor.execute(f"select count(*) from {table_name}")
                    counts[label] = int(cursor.fetchone()[0])
                except oracledb.DatabaseError:
                    counts[label] = 0
            try:
                cursor.execute(f"select count(distinct source_path) from {chunk_table}")
                counts["documents"] = int(cursor.fetchone()[0])
            except oracledb.DatabaseError:
                counts["documents"] = 0
        return counts


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ", ".join(f"{value:.9f}" for value in embedding) + "]"
