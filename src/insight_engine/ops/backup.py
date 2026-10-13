"""SQLite backup, integrity check, and restore helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from insight_engine.config import Settings, get_settings


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def integrity_check(db_path: Path | str) -> tuple[bool, str]:
    path = Path(db_path)
    if not path.exists():
        return False, f"database not found: {path}"
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        msg = row[0] if row else "unknown"
        return msg == "ok", str(msg)
    finally:
        conn.close()


def backup_database(
    settings: Settings | None = None,
    *,
    label: str | None = None,
) -> Path:
    """
    Create a consistent backup using SQLite online backup API.
    Returns backup file path.
    """
    settings = settings or get_settings()
    settings.ensure_directories()
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    src = settings.db_path
    if not src.exists():
        raise FileNotFoundError(f"database not found: {src}")

    ok, msg = integrity_check(src)
    if not ok:
        raise RuntimeError(f"refusing to backup corrupt database: {msg}")

    stamp = _utc_stamp()
    suffix = f"_{label}" if label else ""
    dest = backup_dir / f"insight_{stamp}{suffix}.db"

    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    ok2, msg2 = integrity_check(dest)
    if not ok2:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"backup failed integrity_check: {msg2}")
    return dest


def restore_database(
    backup_path: Path | str,
    settings: Settings | None = None,
    *,
    safety_backup: bool = True,
) -> Path:
    """
    Restore db_path from a backup file.
    Optionally creates a safety backup of the current DB first.
    """
    settings = settings or get_settings()
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"backup not found: {backup_path}")

    ok, msg = integrity_check(backup_path)
    if not ok:
        raise RuntimeError(f"backup failed integrity_check: {msg}")

    settings.ensure_directories()
    target = settings.db_path
    if safety_backup and target.exists():
        safety = backup_database(settings, label="pre_restore")
    else:
        safety = None

    # In-place restore via SQLite backup API (avoids WinError 32 on unlink).
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        sqlite3.connect(str(target)).close()
    src_conn = sqlite3.connect(str(backup_path))
    try:
        dst_conn = sqlite3.connect(str(target))
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    ok2, msg2 = integrity_check(target)
    if not ok2:
        raise RuntimeError(f"restored database failed integrity_check: {msg2}")
    return safety if safety else target