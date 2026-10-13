"""Anonymous search session archive for secondary analysis."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SessionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert_session(self, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO search_sessions (
              session_id, anonymous_id, mode, keywords_json, research_brief,
              collector_ids_json, document_count, unique_document_count,
              report_run_id, report_summary, metrics_json, llm_mode,
              created_at, client_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["session_id"],
                payload.get("anonymous_id"),
                payload["mode"],
                json.dumps(payload.get("keywords") or [], ensure_ascii=False),
                payload.get("research_brief"),
                json.dumps(payload.get("collector_ids") or [], ensure_ascii=False),
                payload.get("document_count"),
                payload.get("unique_document_count"),
                payload.get("report_run_id"),
                payload.get("report_summary"),
                json.dumps(payload.get("metrics") or {}, ensure_ascii=False),
                payload.get("llm_mode"),
                payload.get("created_at") or _utc_now(),
                json.dumps(payload.get("client_meta") or {}, ensure_ascii=False),
            ),
        )

    def list_sessions(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT session_id, anonymous_id, mode, keywords_json, research_brief,
                   document_count, unique_document_count, report_summary, llm_mode, created_at
            FROM search_sessions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["keywords"] = json.loads(d.pop("keywords_json") or "[]")
            out.append(d)
        return out
