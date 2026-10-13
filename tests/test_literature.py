import sqlite3

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.product.literature import analyze_literature_batch, literature_rows_to_csv


def _insert_doc(conn: sqlite3.Connection, doc_id: str, title: str, body: str) -> None:
    conn.execute(
        """
        INSERT INTO sources (
          source_id, source_name, source_type, acquisition_method,
          permission_status, allow_local_store, allow_model_process, allow_report_export,
          created_at, updated_at
        ) VALUES (?, 'u', 'upload', 'user_upload', 'user_owned', 1, 0, 1, datetime('now'), datetime('now'))
        ON CONFLICT(source_id) DO NOTHING
        """,
        ("s1",),
    )
    conn.execute(
        """
        INSERT INTO documents (
          document_id, source_id, source_type, source_name, title,
          collected_at, content_type, raw_content, normalized_content,
          content_hash, is_duplicate, permission_status, processing_status,
          created_at, updated_at
        ) VALUES (?, 's1', 'upload', 'u', ?, datetime('now'), 'literature_pdf', ?, ?, ?, 0, 'user_owned', 'normalized', datetime('now'), datetime('now'))
        """,
        (doc_id, title, body, body, f"hash-{doc_id}"),
    )


def test_literature_common_diff_innov(tmp_settings) -> None:
    initialize_database(tmp_settings)
    with get_connection(tmp_settings.db_path) as conn:
        _insert_doc(
            conn,
            "d1",
            "paper-A",
            "本文提出一种创新方法用于宠物毛发祈福编织，并首次验证价格接受度。",
        )
        _insert_doc(
            conn,
            "d2",
            "paper-B",
            "本研究讨论宠物毛发祈福与离世纪念差异，强调卫生与隐私风险，未涉及创新算法。",
        )
        conn.commit()
        lit = analyze_literature_batch(conn, ["d1", "d2"])

    assert len(lit["rows"]) == 2
    assert lit["commonality"]
    assert lit["differences"]
    assert lit["relevance_counts"]
    row_a = next(r for r in lit["rows"] if r["document_id"] == "d1")
    assert row_a["relevance_tier"] in {"direct", "edge"}
    assert row_a["innovation_hints"]
    assert row_a["innovation_evidence"]
    assert any("创新" in x or "首次" in x or "提出" in x for x in lit["innovations"])
    csv_text = literature_rows_to_csv(lit["rows"], profile="literature")
    assert "标题" in csv_text
    assert "创新点" in csv_text
    assert "paper-A" in csv_text
    # Deep fields present on rows
    assert "future_directions" in row_a
    assert "year" in row_a
