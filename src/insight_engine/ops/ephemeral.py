"""Wipe raw source text/media after analysis — keep structured outcomes only."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def wipe_raw_document_bodies(conn: sqlite3.Connection, document_ids: list[str] | None = None) -> int:
    """
    Clear raw/normalized full text from documents.
    Evidence excerpts in evidence_links are retained.
    """
    if document_ids is not None and not document_ids:
        return 0
    if document_ids is None:
        cur = conn.execute(
            """
            UPDATE documents
            SET raw_content = NULL,
                normalized_content = '[ephemeral:cleared]',
                processing_status = 'analyzed_ephemeral',
                updated_at = datetime('now')
            WHERE raw_content IS NOT NULL
               OR (normalized_content IS NOT NULL AND normalized_content != '[ephemeral:cleared]')
            """
        )
    else:
        placeholders = ",".join("?" for _ in document_ids)
        cur = conn.execute(
            f"""
            UPDATE documents
            SET raw_content = NULL,
                normalized_content = '[ephemeral:cleared]',
                processing_status = 'analyzed_ephemeral',
                updated_at = datetime('now')
            WHERE document_id IN ({placeholders})
            """,
            document_ids,
        )
    # FTS: remove full text for wiped docs
    if document_ids is None:
        conn.execute("DELETE FROM documents_fts")
    else:
        for doc_id in document_ids:
            conn.execute("DELETE FROM documents_fts WHERE document_id = ?", (doc_id,))
    return cur.rowcount


def delete_path_quietly(path: Path | str | None) -> None:
    if not path:
        return
    p = Path(path)
    try:
        if p.is_file():
            p.unlink(missing_ok=True)
    except OSError:
        pass
