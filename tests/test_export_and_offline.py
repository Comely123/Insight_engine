from __future__ import annotations

import os
from pathlib import Path

from insight_engine.export.writers import export_documents_csv, export_documents_json
from insight_engine.ingest.service import ImportService
from insight_engine.search.fts import SearchFilters, search_documents


def test_no_api_key_required_for_import_search_export(db_conn, tmp_settings, tmp_path, monkeypatch):
    monkeypatch.delenv("INSIGHT_LLM_API_KEY", raising=False)
    assert os.environ.get("INSIGHT_LLM_API_KEY") in (None, "")

    sample = Path(__file__).resolve().parents[1] / "data" / "samples" / "pet_blessing_sample.json"
    service = ImportService(db_conn, tmp_settings)
    result = service.import_file(sample, save_copy=False)
    assert result.row_count_imported == 3

    rows = search_documents(db_conn, SearchFilters(query="祈福", limit=10))
    assert rows

    csv_path = export_documents_csv(tmp_path / "out.csv", rows)
    json_path = export_documents_json(tmp_path / "out.json", rows)
    assert csv_path.exists() and csv_path.stat().st_size > 0
    assert json_path.exists() and json_path.stat().st_size > 0
