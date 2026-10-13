"""Exact content hashing and duplicate lookup."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Iterable, Literal

from insight_engine.normalize.pipeline import normalize_text

DedupScope = Literal["global", "session", "none"]


def content_hash(
    text: str | None,
    *,
    lowercase: bool = True,
    collapse_whitespace: bool = True,
) -> str:
    normalized = normalize_text(text, lowercase=lowercase, collapse=collapse_whitespace)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest


def find_duplicate_id(
    conn: sqlite3.Connection,
    hash_value: str,
    *,
    scope: DedupScope = "global",
    peer_document_ids: Iterable[str] | None = None,
) -> str | None:
    """
    Find a canonical document with the same content hash.

    scope:
      - global: any non-ephemeral, non-duplicate doc (historical default)
      - session: only among peer_document_ids (this upload/run); empty peers → no match
      - none: never treat as duplicate
    """
    if scope == "none":
        return None

    if scope == "session":
        peers = [p for p in (peer_document_ids or []) if p]
        if not peers:
            return None
        placeholders = ",".join("?" for _ in peers)
        row = conn.execute(
            f"""
            SELECT document_id
            FROM documents
            WHERE content_hash = ?
              AND is_duplicate = 0
              AND document_id IN ({placeholders})
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (hash_value, *peers),
        ).fetchone()
        return row["document_id"] if row else None

    # global — ignore wiped ephemeral bodies so re-uploads can analyze again
    row = conn.execute(
        """
        SELECT document_id
        FROM documents
        WHERE content_hash = ?
          AND is_duplicate = 0
          AND COALESCE(processing_status, '') != 'analyzed_ephemeral'
          AND COALESCE(normalized_content, '') != '[ephemeral:cleared]'
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (hash_value,),
    ).fetchone()
    return row["document_id"] if row else None
