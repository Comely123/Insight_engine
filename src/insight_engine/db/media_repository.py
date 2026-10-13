"""Persistence for media assets, segments, runs, and links."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from insight_engine.models.media import MediaAssetCreate, MediaSegmentCreate


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MediaRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def find_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM media_assets
            WHERE file_hash = ? AND is_duplicate = 0
            ORDER BY imported_at ASC LIMIT 1
            """,
            (file_hash,),
        ).fetchone()
        return dict(row) if row else None

    def insert_asset(self, asset: MediaAssetCreate) -> None:
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO media_assets (
              media_id, source_id, document_id, file_type, original_filename, local_path,
              file_hash, file_size_bytes, duration_seconds, width, height, permission_status,
              allowed_processing, retention_policy, processing_status, duplicate_of,
              is_duplicate, error_message, imported_at, updated_at, provenance_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.media_id,
                asset.source_id,
                asset.document_id,
                asset.file_type,
                asset.original_filename,
                asset.local_path,
                asset.file_hash,
                asset.file_size_bytes,
                asset.duration_seconds,
                asset.width,
                asset.height,
                asset.permission_status,
                json.dumps(asset.allowed_processing, ensure_ascii=False),
                asset.retention_policy,
                asset.processing_status.value,
                asset.duplicate_of,
                int(asset.is_duplicate),
                asset.error_message,
                now,
                now,
                json.dumps(asset.provenance_metadata, ensure_ascii=False),
            ),
        )

    def update_asset_metadata(
        self,
        media_id: str,
        *,
        duration_seconds: float | None = None,
        width: int | None = None,
        height: int | None = None,
        processing_status: str | None = None,
        error_message: str | None = None,
        document_id: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [_utc_now()]
        if duration_seconds is not None:
            fields.append("duration_seconds = ?")
            params.append(duration_seconds)
        if width is not None:
            fields.append("width = ?")
            params.append(width)
        if height is not None:
            fields.append("height = ?")
            params.append(height)
        if processing_status is not None:
            fields.append("processing_status = ?")
            params.append(processing_status)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if document_id is not None:
            fields.append("document_id = ?")
            params.append(document_id)
        params.append(media_id)
        self.conn.execute(
            f"UPDATE media_assets SET {', '.join(fields)} WHERE media_id = ?",
            params,
        )

    def create_processing_run(
        self,
        *,
        media_id: str,
        params: dict[str, Any] | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO media_processing_runs (
              processing_run_id, media_id, started_at, status, params_json,
              model_name, model_version, steps_json
            ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
            """,
            (
                run_id,
                media_id,
                _utc_now(),
                json.dumps(params or {}, ensure_ascii=False),
                model_name,
                model_version,
                json.dumps([], ensure_ascii=False),
            ),
        )
        return run_id

    def finalize_processing_run(
        self,
        run_id: str,
        *,
        status: str,
        steps: list[dict[str, Any]],
        error_summary: str | None,
        duration_ms: int | None,
        model_name: str | None = None,
        model_version: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE media_processing_runs
            SET finished_at = ?, status = ?, steps_json = ?, error_summary = ?,
                duration_ms = ?, model_name = COALESCE(?, model_name),
                model_version = COALESCE(?, model_version)
            WHERE processing_run_id = ?
            """,
            (
                _utc_now(),
                status,
                json.dumps(steps, ensure_ascii=False),
                error_summary,
                duration_ms,
                model_name,
                model_version,
                run_id,
            ),
        )

    def insert_segment(self, segment: MediaSegmentCreate) -> None:
        self.conn.execute(
            """
            INSERT INTO media_segments (
              segment_id, media_id, modality, start_time, end_time, transcript_text,
              subtitle_text, ocr_text, keyframe_path, analysis_model, confidence,
              evidence_status, source_reference, processing_run_id, content_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                segment.segment_id,
                segment.media_id,
                segment.modality.value,
                segment.start_time,
                segment.end_time,
                segment.transcript_text,
                segment.subtitle_text,
                segment.ocr_text,
                segment.keyframe_path,
                segment.analysis_model,
                segment.confidence,
                segment.evidence_status.value,
                segment.source_reference,
                segment.processing_run_id,
                segment.content_hash,
                _utc_now(),
            ),
        )

    def insert_link(
        self,
        *,
        media_id: str,
        from_segment_id: str | None,
        to_segment_id: str | None,
        link_type: str,
        reason: str,
        score: float | None,
        created_by: str = "rules",
        review_status: str = "auto",
    ) -> str:
        link_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO media_links (
              link_id, media_id, from_segment_id, to_segment_id, link_type, reason,
              score, review_status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                media_id,
                from_segment_id,
                to_segment_id,
                link_type,
                reason,
                score,
                review_status,
                created_by,
                _utc_now(),
            ),
        )
        return link_id

    def revoke_link(self, link_id: str) -> None:
        self.conn.execute(
            """
            UPDATE media_links
            SET review_status = 'revoked', revoked_at = ?
            WHERE link_id = ?
            """,
            (_utc_now(), link_id),
        )

    def confirm_link(self, link_id: str) -> None:
        self.conn.execute(
            "UPDATE media_links SET review_status = 'confirmed' WHERE link_id = ?",
            (link_id,),
        )

    def list_assets(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM media_assets
            ORDER BY imported_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_asset(self, media_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM media_assets WHERE media_id = ?", (media_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_segments(self, media_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM media_segments
            WHERE media_id = ?
            ORDER BY COALESCE(start_time, 0), modality
            """,
            (media_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_links(self, media_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM media_links
            WHERE media_id = ?
            ORDER BY created_at DESC
            """,
            (media_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_runs(self, media_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM media_processing_runs
            WHERE media_id = ?
            ORDER BY started_at DESC
            """,
            (media_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_segment_status(
        self,
        segment_id: str,
        *,
        evidence_status: str,
        corrected_text: str | None = None,
        modality: str | None = None,
    ) -> None:
        if corrected_text is not None and modality == "subtitle":
            self.conn.execute(
                """
                UPDATE media_segments
                SET evidence_status = ?, subtitle_text = ?
                WHERE segment_id = ?
                """,
                (evidence_status, corrected_text, segment_id),
            )
        elif corrected_text is not None and modality == "asr":
            self.conn.execute(
                """
                UPDATE media_segments
                SET evidence_status = ?, transcript_text = ?
                WHERE segment_id = ?
                """,
                (evidence_status, corrected_text, segment_id),
            )
        elif corrected_text is not None and modality == "ocr":
            self.conn.execute(
                """
                UPDATE media_segments
                SET evidence_status = ?, ocr_text = ?
                WHERE segment_id = ?
                """,
                (evidence_status, corrected_text, segment_id),
            )
        else:
            self.conn.execute(
                "UPDATE media_segments SET evidence_status = ? WHERE segment_id = ?",
                (evidence_status, segment_id),
            )

    def overview_stats(self) -> dict[str, Any]:
        return {
            "media_count": self.conn.execute(
                "SELECT COUNT(*) AS c FROM media_assets"
            ).fetchone()["c"],
            "segment_count": self.conn.execute(
                "SELECT COUNT(*) AS c FROM media_segments"
            ).fetchone()["c"],
            "failed_media": self.conn.execute(
                "SELECT COUNT(*) AS c FROM media_assets WHERE processing_status = 'failed'"
            ).fetchone()["c"],
        }
