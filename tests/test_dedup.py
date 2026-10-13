from __future__ import annotations

from insight_engine.dedup.hasher import content_hash, find_duplicate_id
from insight_engine.ingest.service import ImportService
from insight_engine.models.documents import PermissionStatus


def test_content_hash_stable_for_whitespace_variants():
    a = content_hash("Hello   World")
    b = content_hash("hello world")
    assert a == b


def test_exact_duplicate_marked(db_conn, tmp_settings, tmp_path):
    sample = tmp_path / "dup.csv"
    sample.write_text(
        "title,content,published_at,source_name\n"
        "A,完全相同的一段正文内容,2025-01-01,S1\n"
        "B,完全相同的一段正文内容,2025-01-02,S2\n",
        encoding="utf-8",
    )
    service = ImportService(db_conn, tmp_settings)
    result = service.import_file(
        sample,
        permission_status=PermissionStatus.USER_OWNED,
        save_copy=False,
    )
    assert result.row_count_imported == 2
    assert result.row_count_dupes == 1

    rows = db_conn.execute(
        "SELECT document_id, title, is_duplicate, duplicate_of, content_hash "
        "FROM documents ORDER BY title"
    ).fetchall()
    by_title = {r["title"]: r for r in rows}
    assert by_title["A"]["is_duplicate"] == 0
    assert by_title["B"]["is_duplicate"] == 1
    assert by_title["B"]["duplicate_of"] == by_title["A"]["document_id"]
    assert find_duplicate_id(db_conn, by_title["A"]["content_hash"]) == by_title["A"]["document_id"]
