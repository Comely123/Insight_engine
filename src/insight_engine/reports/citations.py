"""Validate that report citations refer to real DB records."""

from __future__ import annotations

import sqlite3
from typing import Any


def validate_citations(
    conn: sqlite3.Connection,
    citations: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for i, cite in enumerate(citations):
        doc_id = cite.get("document_id")
        if not doc_id:
            errors.append(f"citation[{i}]: missing document_id")
            continue
        row = conn.execute(
            "SELECT document_id, original_url FROM documents WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            errors.append(f"citation[{i}]: document_id not found: {doc_id}")
            continue
        url = cite.get("original_url")
        if url and row["original_url"] and url != row["original_url"]:
            # allow cite without url; if provided must match stored
            errors.append(f"citation[{i}]: original_url mismatch for {doc_id}")
        seg_id = cite.get("segment_id")
        if seg_id:
            seg = conn.execute(
                "SELECT segment_id, media_id, start_time, end_time FROM media_segments WHERE segment_id = ?",
                (seg_id,),
            ).fetchone()
            if seg is None:
                errors.append(f"citation[{i}]: segment_id not found: {seg_id}")
            else:
                st = cite.get("start_time")
                if st is not None and seg["start_time"] is not None:
                    if abs(float(st) - float(seg["start_time"])) > 0.05:
                        errors.append(
                            f"citation[{i}]: start_time does not match segment timeline"
                        )
        excerpt = (cite.get("excerpt") or "").strip()
        if not excerpt:
            errors.append(f"citation[{i}]: empty excerpt")
    return (len(errors) == 0), errors
