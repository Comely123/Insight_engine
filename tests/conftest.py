from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from insight_engine.config import Settings, reset_settings_cache
from insight_engine.db.connection import get_connection, initialize_database


@pytest.fixture()
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("INSIGHT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("INSIGHT_DB_PATH", str(data_dir / "test.db"))
    reset_settings_cache()
    settings = Settings()
    initialize_database(settings)
    yield settings
    reset_settings_cache()


@pytest.fixture()
def db_conn(tmp_settings: Settings):
    conn = get_connection(tmp_settings.db_path)
    try:
        yield conn
    finally:
        conn.close()
