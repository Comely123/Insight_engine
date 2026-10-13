"""Batch A: retention wording metrics + confirmed prices only in buckets."""

from __future__ import annotations

import json

from insight_engine.analysis.rules import analyze_document_rules, reset_rules_cache
from insight_engine.db.analysis_repository import AnalysisRepository
from insight_engine.ingest.service import ImportService
from insight_engine.models.documents import PermissionStatus
from insight_engine.trends.metrics import compute_trend_metrics


def test_metrics_rates_and_confirmed_prices(db_conn, tmp_settings, tmp_path):
    reset_rules_cache()
    sample = tmp_path / "batch_a.json"
    sample.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "title": "A",
                        "content": "报名费 128 元，欢迎咨询。",
                        "source_name": "OpenAlex",
                        "original_url": "https://doi.org/10.1/x",
                    },
                    {
                        "title": "A-dup",
                        "content": "报名费 128 元，欢迎咨询。",
                        "source_name": "OpenAlex",
                        "original_url": "https://doi.org/10.1/x",
                    },
                    {
                        "title": "B",
                        "content": "Li Wenyu (1840-1911) and date 2026-05-10. Also ¥99 ok.",
                        "source_name": "Crossref",
                        "original_url": "https://example.org/paper",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    importer = ImportService(db_conn, tmp_settings)
    result = importer.import_file(
        sample,
        permission_status=PermissionStatus.USER_OWNED,
        save_copy=False,
        dedupe_scope="global",
    )
    assert result.row_count_imported == 3
    assert result.row_count_dupes == 1

    docs = db_conn.execute(
        "SELECT document_id, title, is_duplicate FROM documents"
    ).fetchall()
    ids = [d["document_id"] for d in docs]
    repo = AnalysisRepository(db_conn)
    run_id = "run-batch-a"
    repo.create_run(
        run_id=run_id,
        analyzer_type="rules",
        model_name=None,
        prompt_version="rules-v1",
    )
    for d in docs:
        if d["is_duplicate"]:
            continue
        body = db_conn.execute(
            "SELECT title, normalized_content FROM documents WHERE document_id=?",
            (d["document_id"],),
        ).fetchone()
        analyzed = analyze_document_rules(
            document_id=d["document_id"],
            title=body["title"],
            content=body["normalized_content"],
        )
        repo.persist_document_analysis(run_id=run_id, result=analyzed, event_time=None)
    db_conn.commit()

    report = compute_trend_metrics(
        db_conn, document_ids=ids, ignore_time_window=True, persist=False
    )
    assert report.raw_documents == 3
    assert report.unique_documents == 2
    assert report.duplicate_documents == 1
    assert abs((report.retention_rate or 0) - 2 / 3) < 1e-9
    assert abs((report.dedup_deletion_rate or 0) - 1 / 3) < 1e-9
    assert report.platform_count >= 2
    assert report.domain_count >= 2
    # 128 and 99 confirmed; years must not enter price_values
    assert 128.0 in report.price_values
    assert 99.0 in report.price_values
    assert 1840.0 not in report.price_values
    assert 1911.0 not in report.price_values
    assert 2026.0 not in report.price_values
