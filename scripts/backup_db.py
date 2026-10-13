#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.db.connection import initialize_database
from insight_engine.ops.backup import backup_database, integrity_check
from insight_engine.config import get_settings


def main() -> None:
    initialize_database()
    settings = get_settings()
    ok, msg = integrity_check(settings.db_path)
    print(f"integrity_check: {msg}")
    if not ok:
        sys.exit(1)
    path = backup_database(settings)
    print(f"backup_written: {path}")


if __name__ == "__main__":
    main()
