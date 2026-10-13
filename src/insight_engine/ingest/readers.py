"""File readers for CSV / JSON / TXT."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterator


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        columns = [c for c in reader.fieldnames if c is not None]
        rows: list[dict[str, Any]] = []
        for row in reader:
            rows.append({k: (v if v is not None else "") for k, v in row.items() if k is not None})
        return columns, rows


def read_json_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        if "documents" in data and isinstance(data["documents"], list):
            records = data["documents"]
        elif "items" in data and isinstance(data["items"], list):
            records = data["items"]
        elif "data" in data and isinstance(data["data"], list):
            records = data["data"]
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("JSON root must be an object or array")

    rows: list[dict[str, Any]] = []
    for i, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"JSON item at index {i} is not an object")
        rows.append(item)

    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                columns.append(str(key))
    return columns, rows


def read_txt_as_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    # Split on blank lines into documents; if none, whole file is one doc
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    if not chunks:
        chunks = [text.strip()] if text.strip() else []
    rows = []
    for idx, chunk in enumerate(chunks, start=1):
        lines = chunk.splitlines()
        title = lines[0][:200] if lines else f"document_{idx}"
        rows.append(
            {
                "title": title,
                "content": chunk,
                "content_type": "text",
            }
        )
    return ["title", "content", "content_type"], rows


def iter_preview(rows: list[dict[str, Any]], limit: int = 5) -> Iterator[dict[str, Any]]:
    for row in rows[:limit]:
        yield row
