from __future__ import annotations

from pathlib import Path

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.ingest.service import ImportService
from insight_engine.ops.backup import backup_database, integrity_check, restore_database
from insight_engine.ops.logging_util import redact_secrets

SAMPLES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def test_backup_restore_roundtrip(tmp_settings):
    initialize_database(tmp_settings)
    with get_connection(tmp_settings.db_path) as conn:
        ImportService(conn, tmp_settings).import_file(
            SAMPLES / "pet_blessing_sample.json", save_copy=False
        )
        before = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]

    ok, msg = integrity_check(tmp_settings.db_path)
    assert ok, msg
    backup = backup_database(tmp_settings, label="test")
    assert backup.exists()

    # Clear dependent rows then documents
    with get_connection(tmp_settings.db_path) as conn:
        conn.executescript(
            """
            DELETE FROM evidence_links;
            DELETE FROM claims;
            DELETE FROM events;
            DELETE FROM model_outputs;
            DELETE FROM analysis_runs;
            DELETE FROM documents_fts;
            DELETE FROM documents;
            """
        )
        conn.commit()
        mid = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
    assert mid == 0

    restore_database(backup, tmp_settings, safety_backup=True)
    with get_connection(tmp_settings.db_path) as conn:
        after = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
    assert after == before


def test_redact_secrets():
    text = "INSIGHT_LLM_API_KEY=sk-abcdefghijklmnop token=secret"
    red = redact_secrets(f"api_key={text}")
    assert "sk-abcdefghijklmnop" not in red
    assert "[REDACTED]" in red
