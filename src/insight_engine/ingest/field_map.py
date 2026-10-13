"""Flexible field mapping for tabular imports."""

from __future__ import annotations

from typing import Any

# Canonical field -> accepted aliases (lowercase)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "标题", "headline", "name", "subject"),
    "content": (
        "content",
        "正文",
        "text",
        "body",
        "raw_content",
        "normalized_content",
        "description",
        "内容",
    ),
    "original_url": ("original_url", "url", "link", "source_url", "链接", "网址"),
    "published_at": (
        "published_at",
        "publish_time",
        "published",
        "date",
        "datetime",
        "时间",
        "发布日期",
        "发布时间",
    ),
    "source_name": ("source_name", "source", "来源", "channel", "platform"),
    "content_type": ("content_type", "type", "类型"),
}


def _normalize_key(key: str) -> str:
    return str(key).strip().lower().replace(" ", "_")


def build_column_map(columns: list[str]) -> dict[str, str]:
    """Map canonical field name -> actual column name present in data."""
    normalized = {_normalize_key(c): c for c in columns}
    mapping: dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            key = _normalize_key(alias)
            if key in normalized:
                mapping[canonical] = normalized[key]
                break
    return mapping


def row_get(row: dict[str, Any], column_map: dict[str, str], field: str) -> Any:
    col = column_map.get(field)
    if col is None:
        return None
    return row.get(col)
