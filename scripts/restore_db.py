#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.config import get_settings
from insight_engine.ops.backup import restore_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore SQLite DB from backup")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--no-safety-backup", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    safety = restore_database(
        args.backup,
        settings,
        safety_backup=not args.no_safety_backup,
    )
    print(f"restored: {settings.db_path}")
    print(f"safety_backup_or_target: {safety}")


if __name__ == "__main__":
    main()
