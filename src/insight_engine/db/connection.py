"""SQLite connection helpers and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from insight_engine.config import Settings, get_settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    settings = get_settings()
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(settings: Settings | None = None) -> Path:
    """Create directories and apply schema.sql. Returns db path."""
    settings = settings or get_settings()
    settings.ensure_directories()
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(settings.db_path) as conn:
        conn.executescript(schema_sql)
        conn.commit()
    return settings.db_path
