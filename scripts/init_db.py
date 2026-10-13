#!/usr/bin/env python3
"""Initialize the local SQLite database."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.config import get_settings
from insight_engine.db.connection import initialize_database


def main() -> None:
    settings = get_settings()
    db_path = initialize_database(settings)
    print(f"Database ready: {db_path}")


if __name__ == "__main__":
    main()
