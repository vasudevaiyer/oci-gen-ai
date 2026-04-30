from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime

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
        chunks_table = self.settings.chunks_table
        images_table = self.settings.images_table
        chat_events_table = self.settings.chat_events_table
        statements = [
            f"""
            create table {chunks_table} (
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
                constraint {self._constraint_name(chunks_table, "meta_jsn")} check (metadata is json)
            )
            """,
            f"create unique index {self._index_name(chunks_table, 'uk')} on {chunks_table} (source_path, chunk_index)",
            f"""
            create table {images_table} (
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
                constraint {self._constraint_name(images_table, "meta_jsn")} check (metadata is json)
            )
            """,
            f"create unique index {self._index_name(images_table, 'uk')} on {images_table} (image_path)",
            f"""
            create table {chat_events_table} (
                event_id number generated always as identity primary key,
                asked_at timestamp default current_timestamp,
                session_id varchar2(128),
                question_text varchar2(2000) not null,
                question_normalized varchar2(2000) not null,
                had_image number(1) default 0 not null,
                top_k number not null,
                success number(1) default 1 not null,
                latency_ms number,
                answer_model varchar2(256),
                top_source_path varchar2(1024),
                top_section_path varchar2(2000),
                retrieved_count number default 0 not null,
                error_message varchar2(1000)
            )
            """,
            f"create index {self._index_name(chat_events_table, 'asked_ix')} on {chat_events_table} (asked_at)",
            f"create index {self._index_name(chat_events_table, 'question_ix')} on {chat_events_table} (question_normalized)",
            f"create index {self._index_name(chat_events_table, 'source_ix')} on {chat_events_table} (top_source_path)",
        ]
        self._execute_ddl_statements(statements)

    def initialize_analytics_schema(self) -> None:
        chat_events_table = self.settings.chat_events_table
        statements = [
            f"""
            create table {chat_events_table} (
                event_id number generated always as identity primary key,
                asked_at timestamp default current_timestamp,
                session_id varchar2(128),
                question_text varchar2(2000) not null,
                question_normalized varchar2(2000) not null,
                had_image number(1) default 0 not null,
                top_k number not null,
                success number(1) default 1 not null,
                latency_ms number,
                answer_model varchar2(256),
                top_source_path varchar2(1024),
                top_section_path varchar2(2000),
                retrieved_count number default 0 not null,
                error_message varchar2(1000)
            )
            """,
            f"create index {self._index_name(chat_events_table, 'asked_ix')} on {chat_events_table} (asked_at)",
            f"create index {self._index_name(chat_events_table, 'question_ix')} on {chat_events_table} (question_normalized)",
            f"create index {self._index_name(chat_events_table, 'source_ix')} on {chat_events_table} (top_source_path)",
        ]
        self._execute_ddl_statements(statements)

    def _execute_ddl_statements(self, statements: list[str]) -> None:
        acceptable_codes = {955, 1408, 2261}
        with self.connect() as connection:
            cursor = connection.cursor()
            for statement in statements:
                try:
                    cursor.execute(statement)
                except oracledb.DatabaseError as exc:
                    error_obj = exc.args[0]
                    if getattr(error_obj, "code", None) not in acceptable_codes:
                        raise
            connection.commit()

    def reset_corpus(self) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            for table_name in (self.settings.images_table, self.settings.chunks_table):
                try:
                    cursor.execute(f"truncate table {table_name}")
                except oracledb.DatabaseError:
                    cursor.execute(f"delete from {table_name}")
            connection.commit()

    def replace_chunks(self, chunks: list[ChunkRecord], embeddings: list[list[float]]) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(f"truncate table {self.settings.chunks_table}")
            except oracledb.DatabaseError:
                cursor.execute(f"delete from {self.settings.chunks_table}")
            self._insert_chunks(cursor, chunks, embeddings)
            connection.commit()

    def append_chunks(self, chunks: list[ChunkRecord], embeddings: list[list[float]]) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            self._insert_chunks(cursor, chunks, embeddings)
            connection.commit()

    def replace_images(self, images: list[ImageRecord], image_embeddings: list[list[float]]) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(f"truncate table {self.settings.images_table}")
            except oracledb.DatabaseError:
                cursor.execute(f"delete from {self.settings.images_table}")
            self._insert_images(cursor, images, image_embeddings)
            connection.commit()

    def append_images(self, images: list[ImageRecord], image_embeddings: list[list[float]]) -> None:
        with self.connect() as connection:
            cursor = connection.cursor()
            self._insert_images(cursor, images, image_embeddings)
            connection.commit()

    def query_chunks(self, query_embedding: list[float], top_k: int) -> list[dict]:
        sql = f"""
            select
                source_path,
                title,
                section_path,
                dbms_lob.substr(content, 4000, 1) as content_text,
                dbms_lob.substr(image_refs, 4000, 1) as image_refs_text,
                1 - vector_distance(embedding, to_vector(:embedding), COSINE) as score
            from {self.settings.chunks_table}
            order by vector_distance(embedding, to_vector(:embedding), COSINE)
            fetch first {int(top_k)} rows only
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, {"embedding": _vector_literal(query_embedding)})
            rows = cursor.fetchall()
        return [
            {
                "source_path": row[0],
                "title": row[1],
                "section_path": row[2],
                "content": row[3] or "",
                "image_refs": json.loads((row[4] or "[]")),
                "score": float(row[5]),
            }
            for row in rows
        ]

    def query_images(self, query_embedding: list[float], top_k: int) -> list[dict]:
        sql = f"""
            select
                image_path,
                dbms_lob.substr(caption_text, 4000, 1) as caption_text_value,
                related_source_path,
                related_section_path,
                1 - vector_distance(embedding, to_vector(:embedding), COSINE) as score
            from {self.settings.images_table}
            order by vector_distance(embedding, to_vector(:embedding), COSINE)
            fetch first {int(top_k)} rows only
        """
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, {"embedding": _vector_literal(query_embedding)})
            rows = cursor.fetchall()
        return [
            {
                "image_path": row[0],
                "caption_text": row[1] or "",
                "source_path": row[2],
                "section_path": row[3],
                "score": float(row[4]),
            }
            for row in rows
        ]

    def corpus_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            cursor = connection.cursor()
            counts = {}
            for table_name, label in ((self.settings.chunks_table, "chunks"), (self.settings.images_table, "images")):
                try:
                    cursor.execute(f"select count(*) from {table_name}")
                    counts[label] = int(cursor.fetchone()[0])
                except oracledb.DatabaseError:
                    counts[label] = 0
            try:
                cursor.execute(f"select count(distinct source_path) from {self.settings.chunks_table}")
                counts["documents"] = int(cursor.fetchone()[0])
            except oracledb.DatabaseError:
                counts["documents"] = 0
        return counts

    def log_chat_event(
        self,
        *,
        session_id: str | None,
        question_text: str,
        question_normalized: str,
        had_image: bool,
        top_k: int,
        success: bool,
        latency_ms: int,
        answer_model: str | None,
        top_source_path: str | None,
        top_section_path: str | None,
        retrieved_count: int,
        error_message: str | None = None,
    ) -> None:
        self.initialize_analytics_schema()
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                insert into {self.settings.chat_events_table} (
                    session_id, question_text, question_normalized, had_image, top_k,
                    success, latency_ms, answer_model, top_source_path, top_section_path,
                    retrieved_count, error_message
                ) values (
                    :session_id, :question_text, :question_normalized, :had_image, :top_k,
                    :success, :latency_ms, :answer_model, :top_source_path, :top_section_path,
                    :retrieved_count, :error_message
                )
                """,
                {
                    "session_id": session_id,
                    "question_text": question_text[:2000],
                    "question_normalized": question_normalized[:2000],
                    "had_image": 1 if had_image else 0,
                    "top_k": top_k,
                    "success": 1 if success else 0,
                    "latency_ms": latency_ms,
                    "answer_model": (answer_model or "")[:256] or None,
                    "top_source_path": (top_source_path or "")[:1024] or None,
                    "top_section_path": (top_section_path or "")[:2000] or None,
                    "retrieved_count": retrieved_count,
                    "error_message": (error_message or "")[:1000] or None,
                },
            )
            connection.commit()

    def analytics_summary(self, *, days: int = 30, top_n: int = 10) -> dict:
        self.initialize_analytics_schema()
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                select
                    count(*) as total_questions,
                    sum(case when success = 1 then 1 else 0 end) as successful_questions,
                    sum(case when success = 0 then 1 else 0 end) as failed_questions,
                    count(distinct question_normalized) as unique_questions,
                    sum(case when had_image = 1 then 1 else 0 end) as questions_with_images,
                    avg(latency_ms) as avg_latency_ms
                from {self.settings.chat_events_table}
                where asked_at >= current_timestamp - numtodsinterval(:days, 'DAY')
                """,
                {"days": days},
            )
            row = cursor.fetchone() or (0, 0, 0, 0, 0, None)
            summary = {
                "total_questions": int(row[0] or 0),
                "successful_questions": int(row[1] or 0),
                "failed_questions": int(row[2] or 0),
                "unique_questions": int(row[3] or 0),
                "questions_with_images": int(row[4] or 0),
                "avg_latency_ms": round(float(row[5] or 0.0), 2),
            }

            cursor.execute(
                f"""
                select
                    question_normalized,
                    min(question_text) keep (dense_rank first order by asked_at desc) as question_text,
                    count(*) as question_count,
                    max(asked_at) as last_asked_at
                from {self.settings.chat_events_table}
                where asked_at >= current_timestamp - numtodsinterval(:days, 'DAY')
                group by question_normalized
                order by question_count desc, last_asked_at desc
                fetch first {int(top_n)} rows only
                """,
                {"days": days},
            )
            top_questions = [
                {
                    "normalized_question": normalized or "",
                    "question": question or normalized or "",
                    "count": int(question_count or 0),
                    "last_asked_at": _timestamp_to_iso(last_asked_at),
                }
                for normalized, question, question_count, last_asked_at in cursor.fetchall()
            ]

            cursor.execute(
                f"""
                select
                    nvl(top_source_path, '(unknown)') as source_path,
                    nvl(top_section_path, '(unknown)') as section_path,
                    count(*) as source_count
                from {self.settings.chat_events_table}
                where asked_at >= current_timestamp - numtodsinterval(:days, 'DAY')
                  and success = 1
                group by top_source_path, top_section_path
                order by source_count desc, source_path, section_path
                fetch first {int(top_n)} rows only
                """,
                {"days": days},
            )
            top_sources = [
                {
                    "source_path": source_path,
                    "section_path": section_path,
                    "count": int(source_count or 0),
                }
                for source_path, section_path, source_count in cursor.fetchall()
            ]

            cursor.execute(
                f"""
                select
                    to_char(trunc(cast(asked_at as date)), 'YYYY-MM-DD') as asked_day,
                    count(*) as day_count
                from {self.settings.chat_events_table}
                where asked_at >= current_timestamp - numtodsinterval(:days, 'DAY')
                group by trunc(cast(asked_at as date))
                order by asked_day
                """,
                {"days": days},
            )
            daily_counts = [
                {"day": asked_day, "count": int(day_count or 0)}
                for asked_day, day_count in cursor.fetchall()
            ]

        return {
            **summary,
            "top_questions": top_questions,
            "top_sources": top_sources,
            "daily_counts": daily_counts,
        }

    def analytics_export_rows(self, *, days: int | None = None) -> list[dict]:
        self.initialize_analytics_schema()
        sql = f"""
            select
                asked_at,
                session_id,
                question_text,
                question_normalized,
                had_image,
                top_k,
                success,
                latency_ms,
                answer_model,
                top_source_path,
                top_section_path,
                retrieved_count,
                error_message
            from {self.settings.chat_events_table}
        """
        binds: dict[str, int] = {}
        if days is not None:
            sql += " where asked_at >= current_timestamp - numtodsinterval(:days, 'DAY')"
            binds["days"] = days
        sql += " order by asked_at desc"

        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, binds)
            rows = cursor.fetchall()

        return [
            {
                "asked_at": _timestamp_to_iso(asked_at),
                "session_id": session_id or "",
                "question_text": question_text or "",
                "question_normalized": question_normalized or "",
                "had_image": "yes" if int(had_image or 0) else "no",
                "top_k": int(top_k or 0),
                "success": "yes" if int(success or 0) else "no",
                "latency_ms": int(latency_ms or 0),
                "answer_model": answer_model or "",
                "top_source_path": top_source_path or "",
                "top_section_path": top_section_path or "",
                "retrieved_count": int(retrieved_count or 0),
                "error_message": error_message or "",
            }
            for (
                asked_at,
                session_id,
                question_text,
                question_normalized,
                had_image,
                top_k,
                success,
                latency_ms,
                answer_model,
                top_source_path,
                top_section_path,
                retrieved_count,
                error_message,
            ) in rows
        ]

    def _constraint_name(self, table_name: str, suffix: str) -> str:
        return _normalize_identifier(_table_base_name(table_name), suffix)

    def _index_name(self, table_name: str, suffix: str) -> str:
        return _normalize_identifier(_table_base_name(table_name), suffix)

    def _insert_chunks(
        self,
        cursor,
        chunks: list[ChunkRecord],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks:
            return
        cursor.executemany(
            f"""
            insert into {self.settings.chunks_table} (
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

    def _insert_images(
        self,
        cursor,
        images: list[ImageRecord],
        image_embeddings: list[list[float]],
    ) -> None:
        if not images:
            return
        cursor.executemany(
            f"""
            insert into {self.settings.images_table} (
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


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ", ".join(f"{value:.9f}" for value in embedding) + "]"


def _timestamp_to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="seconds")


def _normalize_identifier(base: str, suffix: str) -> str:
    name = f"{base}_{suffix}".lower()
    sanitized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    if len(sanitized) <= 30:
        return sanitized
    keep = max(1, 30 - len(suffix) - 1)
    return f"{sanitized[:keep]}_{suffix}"


def _table_base_name(table_name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in table_name.lower())[:20]
