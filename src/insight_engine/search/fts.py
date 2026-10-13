"""Full-text search over documents_fts with optional filters."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from insight_engine.search.cjk_fts import to_fts_match


@dataclass
class SearchFilters:
    query: str = ""
    source_name: str | None = None
    content_type: str | None = None
    published_from: str | None = None  # ISO date/datetime inclusive
    published_to: str | None = None
    include_duplicates: bool = False
    limit: int = 50


def search_documents(conn: sqlite3.Connection, filters: SearchFilters) -> list[dict[str, Any]]:
    limit = max(1, min(filters.limit, 500))
    params: list[Any] = []
    where: list[str] = []

    match_expr = to_fts_match(filters.query)
    if match_expr:
        sql = """
            SELECT d.document_id, d.title, d.normalized_content, d.source_name,
                   d.content_type, d.original_url, d.published_at, d.collected_at,
                   d.is_duplicate, d.duplicate_of, d.permission_status, d.processing_status,
                   bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON d.document_id = documents_fts.document_id
            WHERE documents_fts MATCH ?
        """
        params.append(match_expr)
    else:
        sql = """
            SELECT d.document_id, d.title, d.normalized_content, d.source_name,
                   d.content_type, d.original_url, d.published_at, d.collected_at,
                   d.is_duplicate, d.duplicate_of, d.permission_status, d.processing_status,
                   0.0 AS rank
            FROM documents d
            WHERE 1=1
        """

    if not filters.include_duplicates:
        where.append("d.is_duplicate = 0")
    if filters.source_name:
        where.append("d.source_name = ?")
        params.append(filters.source_name)
    if filters.content_type:
        where.append("d.content_type = ?")
        params.append(filters.content_type)
    if filters.published_from:
        where.append("d.published_at IS NOT NULL AND d.published_at >= ?")
        params.append(filters.published_from)
    if filters.published_to:
        where.append("d.published_at IS NOT NULL AND d.published_at <= ?")
        params.append(filters.published_to)

    if where:
        sql += " AND " + " AND ".join(where)

    if match_expr:
        sql += " ORDER BY rank ASC, d.published_at DESC"
    else:
        sql += " ORDER BY d.published_at DESC, d.collected_at DESC"

    sql += " LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_source_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT source_name
        FROM documents
        WHERE source_name IS NOT NULL AND source_name != ''
        ORDER BY source_name
        """
    ).fetchall()
    return [r["source_name"] for r in rows]


def list_content_types(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT content_type
        FROM documents
        WHERE content_type IS NOT NULL AND content_type != ''
        ORDER BY content_type
        """
    ).fetchall()
    return [r["content_type"] for r in rows]
