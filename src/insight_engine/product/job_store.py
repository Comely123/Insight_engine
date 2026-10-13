"""Persist async analysis job status/results in SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from insight_engine.config import Settings, get_settings
from insight_engine.db.connection import get_connection, initialize_database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        initialize_database(self.settings)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.settings.db_path)

    def create(
        self,
        *,
        job_id: str,
        anonymous_id: str | None,
        mode: str,
        params: dict[str, Any],
        message: str = "已排队",
    ) -> None:
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO analysis_jobs (
                  job_id, anonymous_id, status, message, mode, params_json,
                  result_json, error_message, created_at, updated_at, finished_at
                ) VALUES (?, ?, 'queued', ?, ?, ?, NULL, NULL, ?, ?, NULL)
                """,
                (
                    job_id,
                    anonymous_id,
                    message,
                    mode,
                    json.dumps(params, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        finished: bool = False,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_utc_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if message is not None:
            fields.append("message = ?")
            values.append(message)
        if result is not None:
            fields.append("result_json = ?")
            values.append(json.dumps(result, ensure_ascii=False))
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if finished:
            fields.append("finished_at = ?")
            values.append(_utc_now())
        values.append(job_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE analysis_jobs SET {', '.join(fields)} WHERE job_id = ?",
                values,
            )
            conn.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row(row)

    def latest_for_anonymous(self, anonymous_id: str | None) -> dict[str, Any] | None:
        if not anonymous_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM analysis_jobs
                WHERE anonymous_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (anonymous_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row(row)

    def list_active(self, anonymous_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM analysis_jobs WHERE status IN ('queued', 'running')"
        args: list[Any] = []
        if anonymous_id:
            sql += " AND anonymous_id = ?"
            args.append(anonymous_id)
        sql += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["params"] = json.loads(d.pop("params_json") or "{}")
        raw = d.pop("result_json")
        d["result"] = json.loads(raw) if raw else None
        return d
