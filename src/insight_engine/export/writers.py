"""Export helpers for search/document results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


EXPORT_FIELDS = [
    "document_id",
    "title",
    "normalized_content",
    "source_name",
    "content_type",
    "original_url",
    "published_at",
    "collected_at",
    "is_duplicate",
    "duplicate_of",
    "permission_status",
    "processing_status",
]


def export_documents_csv(path: Path | str, rows: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    materialised = list(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in materialised:
            writer.writerow({k: row.get(k) for k in EXPORT_FIELDS})
    return path


def export_documents_json(path: Path | str, rows: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    materialised = [{k: row.get(k) for k in EXPORT_FIELDS} for row in rows]
    with path.open("w", encoding="utf-8") as f:
        json.dump({"documents": materialised}, f, ensure_ascii=False, indent=2)
    return path
