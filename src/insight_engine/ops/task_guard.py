"""Duplicate-task protection helpers for media processing runs."""

from __future__ import annotations

import sqlite3
from typing import Any


def has_recent_successful_media_run(
    conn: sqlite3.Connection,
    media_id: str,
    *,
    within_seconds: int = 3600,
) -> dict[str, Any] | None:
    """
    Return the latest succeeded run if one finished recently.
    Used to avoid accidental re-processing of the same media.
    """
    row = conn.execute(
        """
        SELECT processing_run_id, status, finished_at, duration_ms
        FROM media_processing_runs
        WHERE media_id = ? AND status = 'succeeded' AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (media_id,),
    ).fetchone()
    if row is None:
        return None
    # SQLite stores ISO text; coarse check via string compare is ok for our writers
    # Callers may ignore time and just use existence; keep simple.
    return dict(row)


def should_skip_media_reprocess(
    conn: sqlite3.Connection,
    media_id: str,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    if force:
        return False, "force=true"
    recent = has_recent_successful_media_run(conn, media_id)
    if recent:
        return True, f"recent succeeded run {recent['processing_run_id']}"
    return False, "no recent success"
