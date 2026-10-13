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


def test_session_scope_allows_reupload_against_prior_global(db_conn, tmp_settings, tmp_path):
    """Re-uploading the same literature must not zero-out a new public analysis batch."""
    import json

    body = "文献正文用于会话级去重测试 " * 20
    service = ImportService(db_conn, tmp_settings)

    def write_doc(name: str, title: str) -> Path:
        path = tmp_path / name
        path.write_text(
            json.dumps({"documents": [{"title": title, "content": body}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    r1 = service.import_file(
        write_doc("first.json", "Paper"),
        permission_status=PermissionStatus.USER_OWNED,
        save_copy=False,
        dedupe_scope="global",
    )
    assert r1.row_count_imported == 1
    assert r1.row_count_dupes == 0

    peers: list[str] = []
    r2 = service.import_file(
        write_doc("second.json", "Paper again"),
        permission_status=PermissionStatus.USER_OWNED,
        save_copy=False,
        dedupe_scope="session",
        session_document_ids=peers,
    )
    assert r2.row_count_imported == 1
    assert r2.row_count_dupes == 0
    assert len(peers) == 1

    # Same content again inside the same session → soft-dup
    r3 = service.import_file(
        write_doc("third.json", "Paper copy"),
        permission_status=PermissionStatus.USER_OWNED,
        save_copy=False,
        dedupe_scope="session",
        session_document_ids=peers,
    )
    assert r3.row_count_imported == 1
    assert r3.row_count_dupes == 1
    assert len(peers) == 1
