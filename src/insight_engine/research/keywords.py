"""Keyword version filtering for research projects."""

from __future__ import annotations

import sqlite3
from typing import Any


def document_matches_keywords(
    text: str,
    *,
    keywords: list[str],
    synonyms: list[str],
    exclude_keywords: list[str],
) -> bool:
    body = text or ""
    for ex in exclude_keywords:
        if ex and ex in body:
            return False
    terms = [t for t in (keywords + synonyms) if t]
    if not terms:
        return True  # no positive filter = all (after excludes)
    return any(t in body for t in terms)


def filter_document_ids(
    conn: sqlite3.Connection,
    *,
    keywords: list[str],
    synonyms: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    source_names: list[str] | None = None,
    include_duplicates: bool = False,
) -> list[str]:
    synonyms = synonyms or []
    exclude_keywords = exclude_keywords or []
    sql = """
        SELECT document_id, title, normalized_content, raw_content,
               published_at, collected_at, source_name, is_duplicate
        FROM documents
    """
    rows = conn.execute(sql).fetchall()
    ids: list[str] = []
    for row in rows:
        if not include_duplicates and row["is_duplicate"]:
            continue
        if source_names and (row["source_name"] or "") not in source_names:
            continue
        ts = row["published_at"] or row["collected_at"] or ""
        if time_start and ts and ts < time_start:
            continue
        if time_end and ts and ts > time_end:
            continue
        text = " ".join(
            x for x in [row["title"] or "", row["normalized_content"] or "", row["raw_content"] or ""]
        )
        if document_matches_keywords(
            text,
            keywords=keywords,
            synonyms=synonyms,
            exclude_keywords=exclude_keywords,
        ):
            ids.append(row["document_id"])
    return ids


def fetch_documents_by_ids(conn: sqlite3.Connection, document_ids: list[str]) -> list[dict[str, Any]]:
    if not document_ids:
        return []
    out: list[dict[str, Any]] = []
    # sqlite variable limit — chunk
    chunk = 400
    for i in range(0, len(document_ids), chunk):
        part = document_ids[i : i + chunk]
        placeholders = ",".join("?" for _ in part)
        rows = conn.execute(
            f"""
            SELECT document_id, title, normalized_content, raw_content, source_name,
                   original_url, published_at, collected_at, content_type, is_duplicate
            FROM documents WHERE document_id IN ({placeholders})
            """,
            part,
        ).fetchall()
        out.extend(dict(r) for r in rows)
    return out
