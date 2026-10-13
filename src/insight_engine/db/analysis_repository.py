"""Persistence for analysis runs, events, claims, evidence, reviews."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from insight_engine.models.analysis import DocumentAnalysisResult, ReviewStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AnalysisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_run(
        self,
        *,
        run_id: str,
        analyzer_type: str,
        model_name: str | None,
        prompt_version: str | None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO analysis_runs (
              run_id, started_at, status, analyzer_type, model_name, prompt_version, config_json
            ) VALUES (?, ?, 'running', ?, ?, ?, ?)
            """,
            (
                run_id,
                _utc_now(),
                analyzer_type,
                model_name,
                prompt_version,
                json.dumps(config or {}, ensure_ascii=False),
            ),
        )

    def finalize_run(
        self,
        *,
        run_id: str,
        status: str,
        document_count: int,
        error_summary: str | None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE analysis_runs
            SET finished_at = ?, status = ?, document_count = ?, error_summary = ?
            WHERE run_id = ?
            """,
            (_utc_now(), status, document_count, error_summary, run_id),
        )

    def insert_model_output(
        self,
        *,
        run_id: str,
        document_id: str | None,
        output_type: str,
        raw_output: str | None,
        validated_json: str | None,
        validation_status: str,
        error_message: str | None = None,
    ) -> str:
        output_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO model_outputs (
              output_id, run_id, document_id, output_type, raw_output,
              validated_json, validation_status, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                output_id,
                run_id,
                document_id,
                output_type,
                raw_output,
                validated_json,
                validation_status,
                error_message,
                _utc_now(),
            ),
        )
        return output_id

    def persist_document_analysis(
        self,
        *,
        run_id: str,
        result: DocumentAnalysisResult,
        event_time: str | None,
    ) -> tuple[str, list[str]]:
        now = _utc_now()
        event_key = f"{result.topic}|{(event_time or '')[:10]}"
        event_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO events (
              event_id, event_key, title, topic, event_time, summary, confidence,
              review_status, created_by, run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_key,
                result.event_title,
                result.topic,
                event_time,
                result.event_summary,
                result.confidence,
                ReviewStatus.UNREVIEWED.value,
                result.analyzer,
                run_id,
                now,
                now,
            ),
        )

        claim_ids: list[str] = []
        for claim in result.claims:
            claim_id = str(uuid.uuid4())
            claim_ids.append(claim_id)
            self.conn.execute(
                """
                INSERT INTO claims (
                  claim_id, event_id, document_id, claim_type, claim_value, polarity,
                  confidence, is_inference, review_status, created_by, run_id,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    event_id,
                    result.document_id,
                    claim.claim_type,
                    claim.claim_value,
                    claim.polarity.value if claim.polarity else None,
                    claim.confidence,
                    int(claim.is_inference),
                    ReviewStatus.UNREVIEWED.value,
                    result.analyzer,
                    run_id,
                    now,
                    now,
                ),
            )
            for ev in claim.evidence:
                self.conn.execute(
                    """
                    INSERT INTO evidence_links (
                      link_id, claim_id, document_id, segment_id, excerpt,
                      char_start, char_end, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        claim_id,
                        ev.document_id,
                        ev.segment_id,
                        ev.excerpt,
                        ev.char_start,
                        ev.char_end,
                        now,
                    ),
                )

        self.conn.execute(
            """
            UPDATE documents
            SET processing_status = 'analyzed', updated_at = ?
            WHERE document_id = ?
            """,
            (now, result.document_id),
        )
        self.insert_model_output(
            run_id=run_id,
            document_id=result.document_id,
            output_type="document_analysis",
            raw_output=None,
            validated_json=result.model_dump_json(),
            validation_status="valid",
        )
        return event_id, claim_ids

    def list_claims_with_evidence(
        self,
        *,
        review_status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql = """
            SELECT c.claim_id, c.event_id, c.document_id, c.claim_type, c.claim_value,
                   c.polarity, c.confidence, c.is_inference, c.review_status, c.created_by,
                   c.created_at, d.title AS document_title, d.source_name, d.original_url,
                   d.published_at
            FROM claims c
            JOIN documents d ON d.document_id = c.document_id
        """
        if review_status:
            sql += " WHERE c.review_status = ?"
            params.append(review_status)
        sql += " ORDER BY c.created_at DESC LIMIT ?"
        params.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, params).fetchall()]
        for row in rows:
            evs = self.conn.execute(
                """
                SELECT link_id, excerpt, char_start, char_end, document_id
                FROM evidence_links WHERE claim_id = ?
                """,
                (row["claim_id"],),
            ).fetchall()
            row["evidence"] = [dict(e) for e in evs]
        return rows

    def list_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT event_id, event_key, title, topic, event_time, summary, confidence,
                   review_status, created_by, run_id, created_at
            FROM events
            ORDER BY COALESCE(event_time, created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def apply_review(
        self,
        *,
        target_type: str,
        target_id: str,
        action: str,
        new_value: str | None = None,
        note: str | None = None,
        reviewer: str = "local_user",
    ) -> None:
        now = _utc_now()
        table = "claims" if target_type == "claim" else "events"
        id_col = "claim_id" if target_type == "claim" else "event_id"
        row = self.conn.execute(
            f"SELECT * FROM {table} WHERE {id_col} = ?",
            (target_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"{target_type} not found: {target_id}")

        previous = None
        if target_type == "claim":
            previous = row["claim_value"]
        else:
            previous = row["summary"]

        if action == "confirm":
            status = ReviewStatus.CONFIRMED.value
        elif action == "reject":
            status = ReviewStatus.REJECTED.value
        elif action == "correct":
            status = ReviewStatus.CORRECTED.value
        else:
            raise ValueError(f"unsupported review action: {action}")

        if target_type == "claim":
            if action == "correct" and new_value is not None:
                self.conn.execute(
                    """
                    UPDATE claims SET claim_value = ?, review_status = ?, updated_at = ?
                    WHERE claim_id = ?
                    """,
                    (new_value, status, now, target_id),
                )
            else:
                self.conn.execute(
                    "UPDATE claims SET review_status = ?, updated_at = ? WHERE claim_id = ?",
                    (status, now, target_id),
                )
        else:
            if action == "correct" and new_value is not None:
                self.conn.execute(
                    """
                    UPDATE events SET summary = ?, review_status = ?, updated_at = ?
                    WHERE event_id = ?
                    """,
                    (new_value, status, now, target_id),
                )
            else:
                self.conn.execute(
                    "UPDATE events SET review_status = ?, updated_at = ? WHERE event_id = ?",
                    (status, now, target_id),
                )

        self.conn.execute(
            """
            INSERT INTO human_reviews (
              review_id, target_type, target_id, action, previous_value, new_value,
              note, reviewer, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                target_type,
                target_id,
                action,
                previous,
                new_value,
                note,
                reviewer,
                now,
            ),
        )

    def overview_analysis_stats(self) -> dict[str, Any]:
        return {
            "analysis_runs": self.conn.execute(
                "SELECT COUNT(*) AS c FROM analysis_runs"
            ).fetchone()["c"],
            "events": self.conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"],
            "claims": self.conn.execute("SELECT COUNT(*) AS c FROM claims").fetchone()["c"],
            "unreviewed_claims": self.conn.execute(
                "SELECT COUNT(*) AS c FROM claims WHERE review_status = 'unreviewed'"
            ).fetchone()["c"],
            "evidence_links": self.conn.execute(
                "SELECT COUNT(*) AS c FROM evidence_links"
            ).fetchone()["c"],
        }
