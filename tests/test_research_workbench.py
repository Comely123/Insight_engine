from __future__ import annotations

from pathlib import Path

from insight_engine.analysis.pipeline import AnalysisService
from insight_engine.db.research_repository import ResearchRepository
from insight_engine.ingest.service import ImportService
from insight_engine.llm.null_provider import NullLLMProvider
from insight_engine.reports.citations import validate_citations
from insight_engine.research.behavior import classify_behavior_and_subtype
from insight_engine.research.keywords import document_matches_keywords
from insight_engine.research.service import ResearchWorkbenchService

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_keyword_filter_and_versioning(db_conn, tmp_settings):
    ImportService(db_conn, tmp_settings).import_file(
        SAMPLES / "pet_blessing_sample.csv", save_copy=False
    )
    svc = ResearchWorkbenchService(db_conn, tmp_settings)
    created = svc.create_project(
        name="t1",
        research_question="q",
        keywords=["祈福", "编织"],
        synonyms=["手绳"],
        exclude_keywords=["免费教程"],
    )
    pid = created["project_id"]
    v2 = svc.add_keyword_version(
        pid,
        keywords=["祈福"],
        synonyms=[],
        exclude_keywords=[],
        change_note="narrow scope",
    )
    assert v2["version_number"] == 2
    versions = ResearchRepository(db_conn).list_keyword_versions(pid)
    assert len(versions) == 2
    docs = svc.search_project_documents(pid)
    assert len(docs) >= 1
    assert document_matches_keywords(
        "祈福手绳", keywords=["祈福"], synonyms=[], exclude_keywords=["免费教程"]
    )
    assert not document_matches_keywords(
        "免费教程祈福", keywords=["祈福"], synonyms=[], exclude_keywords=["免费教程"]
    )


def test_behavior_stage_and_memorial_split():
    living = classify_behavior_and_subtype(
        document_id="d1",
        title="询价",
        content="想给家里狗做毛发祈福编织物，预算 128 元，请问报价。",
    )
    by_type = {c.claim_type: c.claim_value for c in living}
    assert by_type["behavior_stage"] in {"price_inquiry", "purchase_intent", "inquiry"}
    # price_inquiry or purchase_intent depending on keyword order
    assert by_type["demand_subtype"] == "living_blessing"

    memorial = classify_behavior_and_subtype(
        document_id="d2",
        title="纪念",
        content="猫咪离世后想做毛发纪念编织物怀念它。",
    )
    assert {c.claim_type: c.claim_value for c in memorial}["demand_subtype"] == "memorial"


def test_project_run_alerts_and_report(db_conn, tmp_settings):
    ImportService(db_conn, tmp_settings).import_file(
        SAMPLES / "pet_blessing_sample.csv", save_copy=False
    )
    ImportService(db_conn, tmp_settings).import_file(
        SAMPLES / "pet_blessing_sample.json", save_copy=False
    )
    AnalysisService(db_conn, llm=NullLLMProvider()).analyze_documents()

    svc = ResearchWorkbenchService(db_conn, tmp_settings)
    created = svc.create_project(
        name="宠物研究",
        research_question="需求与纪念如何分布",
        keywords=["祈福", "编织", "毛发", "纪念", "价格"],
        time_start="2025-01-01",
        time_end="2026-12-31",
    )
    result = svc.run_project(created["project_id"], window_days=90, export=True)
    assert result["document_count"] >= 1
    assert "behavior_stage_counts" in result["trend"]
    assert "demand_subtype_counts" in result["trend"]
    assert result["trend"]["raw_documents"] >= result["trend"]["unique_documents"]
    assert result["alerts"]  # at least low sample or other
    assert result["report"]["citation_validation"]["ok"] is True
    assert result["report_path"]
    assert Path(result["report_path"]).exists()
    ok, errors = validate_citations(db_conn, result["report"]["citations"])
    assert ok, errors

    # alert review audit
    alert_id = result["alerts"][0]["alert_id"]
    svc.review_alert(alert_id, "confirmed", note="checked")
    alerts = ResearchRepository(db_conn).list_alerts(created["project_id"])
    assert any(a["alert_id"] == alert_id and a["review_status"] == "confirmed" for a in alerts)
