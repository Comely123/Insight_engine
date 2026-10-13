"""Persistence helpers for sources, batches, documents, and FTS."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from insight_engine.models.documents import (
    DocumentCreate,
    ImportBatchResult,
    ImportErrorRecord,
    SourceCreate,
)
from insight_engine.search.cjk_fts import prepare_fts_field


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DocumentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_source(self, source: SourceCreate) -> None:
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO sources (
              source_id, source_name, source_type, original_url, acquisition_method,
              permission_status, license_note, allow_local_store, allow_model_process,
              allow_report_export, retention_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              source_name=excluded.source_name,
              source_type=excluded.source_type,
              original_url=excluded.original_url,
              acquisition_method=excluded.acquisition_method,
              permission_status=excluded.permission_status,
              license_note=excluded.license_note,
              allow_local_store=excluded.allow_local_store,
              allow_model_process=excluded.allow_model_process,
              allow_report_export=excluded.allow_report_export,
              retention_policy=excluded.retention_policy,
              updated_at=excluded.updated_at
            """,
            (
                source.source_id,
                source.source_name,
                source.source_type,
                source.original_url,
                source.acquisition_method,
                source.permission_status.value,
                source.license_note,
                int(source.allow_local_store),
                int(source.allow_model_process),
                int(source.allow_report_export),
                source.retention_policy,
                now,
                now,
            ),
        )

    def create_batch(
        self,
        *,
        batch_id: str,
        source_id: str,
        filename: str | None,
        content_type: str | None,
        started_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO import_batches (
              batch_id, source_id, filename, content_type, started_at, status
            ) VALUES (?, ?, ?, ?, ?, 'running')
            """,
            (batch_id, source_id, filename, content_type, started_at),
        )

    def finalize_batch(self, result: ImportBatchResult) -> None:
        self.conn.execute(
            """
            UPDATE import_batches
            SET finished_at = ?, status = ?, row_count_input = ?,
                row_count_imported = ?, row_count_dupes = ?, error_summary = ?
            WHERE batch_id = ?
            """,
            (
                result.finished_at,
                result.status,
                result.row_count_input,
                result.row_count_imported,
                result.row_count_dupes,
                result.error_summary,
                result.batch_id,
            ),
        )

    def insert_error(self, err: ImportErrorRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO import_errors (
              error_id, batch_id, row_number, field_name, message, raw_snippet, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                err.error_id,
                err.batch_id,
                err.row_number,
                err.field_name,
                err.message,
                err.raw_snippet,
                err.created_at,
            ),
        )

    def insert_document(self, doc: DocumentCreate) -> None:
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO documents (
              document_id, source_id, batch_id, source_type, source_name, original_url,
              title, published_at, collected_at, content_type, raw_content, normalized_content,
              content_hash, url_normalized, permission_status, processing_status,
              provenance_metadata, is_duplicate, duplicate_of, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.document_id,
                doc.source_id,
                doc.batch_id,
                doc.source_type,
                doc.source_name,
                doc.original_url,
                doc.title,
                doc.published_at,
                doc.collected_at,
                doc.content_type,
                doc.raw_content,
                doc.normalized_content,
                doc.content_hash,
                doc.url_normalized,
                doc.permission_status.value,
                doc.processing_status,
                json.dumps(doc.provenance_metadata, ensure_ascii=False),
                int(doc.is_duplicate),
                doc.duplicate_of,
                now,
                now,
            ),
        )
        if not doc.is_duplicate:
            self.conn.execute(
                """
                INSERT INTO documents_fts (document_id, title, normalized_content, source_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    doc.document_id,
                    prepare_fts_field(doc.title),
                    prepare_fts_field(doc.normalized_content),
                    prepare_fts_field(doc.source_name),
                ),
            )

    def overview_stats(self) -> dict[str, Any]:
        doc_count = self.conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        unique_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE is_duplicate = 0"
        ).fetchone()["c"]
        dupe_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE is_duplicate = 1"
        ).fetchone()["c"]
        source_count = self.conn.execute("SELECT COUNT(*) AS c FROM sources").fetchone()["c"]
        batch_count = self.conn.execute("SELECT COUNT(*) AS c FROM import_batches").fetchone()["c"]
        error_count = self.conn.execute("SELECT COUNT(*) AS c FROM import_errors").fetchone()["c"]
        recent_batches = self.conn.execute(
            """
            SELECT batch_id, filename, content_type, status, started_at, finished_at,
                   row_count_input, row_count_imported, row_count_dupes, error_summary
            FROM import_batches
            ORDER BY started_at DESC
            LIMIT 20
            """
        ).fetchall()
        return {
            "document_count": doc_count,
            "unique_document_count": unique_count,
            "duplicate_count": dupe_count,
            "source_count": source_count,
            "batch_count": batch_count,
            "error_count": error_count,
            "recent_batches": [dict(r) for r in recent_batches],
        }

    def list_import_errors(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT error_id, batch_id, row_number, field_name, message, raw_snippet, created_at
            FROM import_errors
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
