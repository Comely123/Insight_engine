from __future__ import annotations

from insight_engine.analysis.rules import analyze_document_rules, reset_rules_cache
from insight_engine.analysis.taxonomy import (
    build_taxonomy_claims,
    reset_taxonomy_cache,
)


def setup_function() -> None:
    reset_rules_cache()
    reset_taxonomy_cache()


def test_souvenir_not_memorial():
    claims, meta = build_taxonomy_claims(
        document_id="d1",
        title="毛发手绳纪念品",
        content="可以定制宠物毛发编织手绳纪念品，包邮发货。",
        ingest_content_type="product_page",
    )
    assert meta["research_topic"] == "souvenir"
    by = {c.claim_type: c.claim_value for c in claims}
    assert by["research_topic"] == "souvenir"
    assert by["content_kind"] in {"product_page", "unknown"}


def test_memorial_requires_loss_cue():
    _, meta = build_taxonomy_claims(
        document_id="d2",
        title="纪念册",
        content="这是一本旅行纪念册，记录风景。",
    )
    assert meta["research_topic"] != "memorial"

    _, meta2 = build_taxonomy_claims(
        document_id="d3",
        title="告别",
        content="猫咪离世后，用毛发做离世纪念手绳。",
    )
    assert meta2["research_topic"] == "memorial"


def test_academic_unrelated_without_domain_anchor():
    result = analyze_document_rules(
        document_id="d4",
        title="Machine learning forecast evaluation",
        content=(
            "Abstract. We propose a novel econometric framework for out-of-sample "
            "prediction of stock returns. References include et al. journal articles. "
            "DOI 10.1234/example. Keywords: forecast, ESG ratings, model."
        ),
        content_type="pdf",  # format only — genre must come from text
    )
    topics = {c.claim_type: c.claim_value for c in result.claims}
    assert topics["content_kind"] == "academic"
    assert topics["research_topic"] == "unrelated"
    assert topics["demand_subtype"] == "unknown"
    assert topics["behavior_stage"] == "unknown"
    assert topics["relevance"] == "unrelated"
    assert "innovation" not in topics


def test_unknown_behavior_not_forced():
    result = analyze_document_rules(
        document_id="d5",
        title="祈福活动说明",
        content="宠物毛发祈福活动将在周末举行，欢迎了解仪式感。",
        content_type="rss",
    )
    topics = {c.claim_type: c.claim_value for c in result.claims}
    assert topics["research_topic"] == "living_blessing"
    # May be interest or discussion or unknown — never force payment
    assert topics["behavior_stage"] not in {"payment", "fulfillment"}
