"""Exact content hashing and duplicate lookup."""

from __future__ import annotations

import hashlib
import sqlite3

from insight_engine.normalize.pipeline import normalize_text


def content_hash(
    text: str | None,
    *,
    lowercase: bool = True,
    collapse_whitespace: bool = True,
) -> str:
    normalized = normalize_text(text, lowercase=lowercase, collapse=collapse_whitespace)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest


def find_duplicate_id(conn: sqlite3.Connection, hash_value: str) -> str | None:
    row = conn.execute(
        """
        SELECT document_id
        FROM documents
        WHERE content_hash = ? AND is_duplicate = 0
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (hash_value,),
    ).fetchone()
    return row["document_id"] if row else None
