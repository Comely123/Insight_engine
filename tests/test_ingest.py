from __future__ import annotations

from pathlib import Path

from insight_engine.db.repository import DocumentRepository
from insight_engine.ingest.field_map import build_column_map
from insight_engine.ingest.service import ImportService, detect_format
from insight_engine.models.documents import PermissionStatus
from insight_engine.search.fts import SearchFilters, search_documents

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"


def test_detect_format():
    assert detect_format(Path("a.csv")) == "csv"
    assert detect_format(Path("a.json")) == "json"
    assert detect_format(Path("a.txt")) == "txt"
    assert detect_format(Path("a.md")) == "txt"


def test_field_map_aliases():
    mapping = build_column_map(["标题", "正文", "链接", "发布时间", "来源"])
    assert mapping["title"] == "标题"
    assert mapping["content"] == "正文"
    assert mapping["original_url"] == "链接"
    assert mapping["published_at"] == "发布时间"
    assert mapping["source_name"] == "来源"


def test_import_csv_sample(db_conn, tmp_settings):
    service = ImportService(db_conn, tmp_settings)
    result = service.import_file(
        SAMPLES / "pet_blessing_sample.csv",
        source_name="csv-sample",
        permission_status=PermissionStatus.USER_OWNED,
        save_copy=False,
    )
    assert result.status in {"succeeded", "partial"}
    assert result.row_count_imported >= 9
    assert result.row_count_dupes >= 1
    # bad date should produce an error but not block the row
    assert any(e.field_name == "published_at" for e in result.errors)

    stats = DocumentRepository(db_conn).overview_stats()
    assert stats["document_count"] == result.row_count_imported


def test_import_json_and_txt(db_conn, tmp_settings):
    service = ImportService(db_conn, tmp_settings)
    r1 = service.import_file(SAMPLES / "pet_blessing_sample.json", save_copy=False)
    r2 = service.import_file(SAMPLES / "notes_sample.txt", save_copy=False)
    assert r1.row_count_imported == 3
    assert r2.row_count_imported >= 1
    assert r1.status == "succeeded"
    assert r2.status == "succeeded"


def test_search_after_import(db_conn, tmp_settings):
    service = ImportService(db_conn, tmp_settings)
    service.import_file(SAMPLES / "pet_blessing_sample.csv", save_copy=False)
    hits = search_documents(db_conn, SearchFilters(query="祈福 手绳", limit=20))
    assert len(hits) >= 1
    assert all(h["is_duplicate"] == 0 for h in hits)


def test_missing_content_recorded_as_error(db_conn, tmp_settings, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("title,published_at\n只有标题,2025-01-01\n", encoding="utf-8")
    service = ImportService(db_conn, tmp_settings)
    result = service.import_file(bad, save_copy=False)
    # title falls back as content in our service — actually we fallback title to content
    # So craft a truly empty row
    bad2 = tmp_path / "bad2.csv"
    bad2.write_text("title,content\n,\n", encoding="utf-8")
    result2 = service.import_file(bad2, save_copy=False)
    assert result2.row_count_imported == 0
    assert result2.status == "failed"
    assert any(e.field_name == "content" for e in result2.errors)
