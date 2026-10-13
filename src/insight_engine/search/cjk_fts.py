"""CJK-aware helpers for SQLite FTS5 unicode61 tokenizer.

Without spaces, contiguous Chinese characters become one oversized token,
so substring queries never match. We index/query with spaces between CJK chars.
"""

from __future__ import annotations

import re

_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_TOKEN_SPLIT = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def space_cjk_chars(text: str) -> str:
    """Insert spaces around each CJK character for FTS tokenization."""
    if not text:
        return ""
    parts: list[str] = []
    for ch in text:
        if _CJK_CHAR.match(ch):
            parts.append(f" {ch} ")
        else:
            parts.append(ch)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def prepare_fts_field(*parts: str | None) -> str:
    return space_cjk_chars(" ".join(p for p in parts if p))


def to_fts_match(query: str) -> str | None:
    """Build FTS5 MATCH expression from a user query."""
    text = query.strip()
    if not text:
        return None
    # Split on punctuation/whitespace; \w includes letters/digits (and some unicode)
    raw_parts = [p for p in _TOKEN_SPLIT.split(text) if p]
    if not raw_parts:
        safe = text.replace('"', " ")
        spaced = space_cjk_chars(safe)
        return f'"{spaced}"' if spaced else None

    clauses: list[str] = []
    for part in raw_parts:
        spaced = space_cjk_chars(part.replace('"', " "))
        if not spaced:
            continue
        # Phrase match preserves character order for multi-char CJK terms
        clauses.append(f'"{spaced}"')
    if not clauses:
        return None
    return " AND ".join(clauses)
