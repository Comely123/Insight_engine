from __future__ import annotations

from pathlib import Path

from insight_engine.analysis.pipeline import AnalysisService
from insight_engine.db.analysis_repository import AnalysisRepository
from insight_engine.ingest.service import ImportService
from insight_engine.llm.null_provider import NullLLMProvider
from insight_engine.trends.metrics import compute_trend_metrics

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_pipeline_rules_without_api_key(db_conn, tmp_settings, monkeypatch):
    monkeypatch.delenv("INSIGHT_LLM_API_KEY", raising=False)
    ImportService(db_conn, tmp_settings).import_file(
        SAMPLES / "pet_blessing_sample.csv",
        save_copy=False,
    )
    service = AnalysisService(db_conn, llm=NullLLMProvider())
    summary = service.analyze_documents(use_llm=True)  # requested but unavailable
    assert summary.status in {"succeeded", "partial"}
    assert summary.events_created >= 1
    assert summary.claims_created >= 1
    assert any("LLM requested" in e for e in summary.errors)

    repo = AnalysisRepository(db_conn)
    claims = repo.list_claims_with_evidence(limit=50)
    assert claims
    assert all(c.get("evidence") for c in claims)

    # human review
    claim_id = claims[0]["claim_id"]
    repo.apply_review(target_type="claim", target_id=claim_id, action="confirm")
    db_conn.commit()
    updated = [
        c for c in repo.list_claims_with_evidence(review_status="confirmed") if c["claim_id"] == claim_id
    ]
    assert updated


def test_trend_metrics_warn_on_small_sample(db_conn, tmp_settings):
    ImportService(db_conn, tmp_settings).import_file(
        SAMPLES / "pet_blessing_sample.json",
        save_copy=False,
    )
    AnalysisService(db_conn, llm=NullLLMProvider()).analyze_documents()
    report = compute_trend_metrics(db_conn, window_days=90, persist=True)
    assert report.warnings
    assert report.confirmed_market_trend is False
    snap = db_conn.execute("SELECT COUNT(*) AS c FROM trend_snapshots").fetchone()["c"]
    assert snap == 1
