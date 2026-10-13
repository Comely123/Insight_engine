from __future__ import annotations

from insight_engine.analysis.innovation import (
    detect_innovation,
    reset_innovation_cache,
)
from insight_engine.analysis.relevance import (
    classify_relevance,
    reset_relevance_cache,
)
from insight_engine.analysis.rules import analyze_document_rules, reset_rules_cache
from insight_engine.analysis.taxonomy import reset_taxonomy_cache


def setup_function() -> None:
    reset_rules_cache()
    reset_taxonomy_cache()
    reset_relevance_cache()
    reset_innovation_cache()


def test_relevance_four_tiers():
    tier, _, _ = classify_relevance(
        "宠物毛发祈福活动欢迎养宠家庭参加平安结编织。",
        research_topic="living_blessing",
    )
    assert tier == "direct"

    tier_e, _, _ = classify_relevance(
        "可以定制宠物毛发编织手绳纪念品，包邮发货。",
        research_topic="souvenir",
    )
    assert tier_e == "edge"

    long_unrelated = (
        "Abstract. We evaluate econometric forecast models for stock returns "
        "using out-of-sample panels across OECD markets and ESG ratings. "
        "Keywords: forecast evaluation, asset pricing."
    )
    tier_u, _, _ = classify_relevance(
        long_unrelated,
        research_topic="unrelated",
    )
    assert tier_u == "unrelated"

    tier_p, _, _ = classify_relevance("短", research_topic="unknown")
    assert tier_p == "pending_review"


def test_innovation_requires_cue_and_substance_and_relevance():
    ok_text = "本文提出一种创新方法用于宠物毛发祈福服务设计，并完成问卷验证。"
    claim, reason = detect_innovation(ok_text, relevance_tier="direct")
    assert claim is not None
    assert "|" in claim.claim_value
    assert len(claim.evidence) == 2
    assert reason.startswith("ok:")

    gated, g_reason = detect_innovation(ok_text, relevance_tier="unrelated")
    assert gated is None
    assert g_reason.startswith("gated_by_relevance")

    cue_only = "本文强调创新与突破，但未说明具体内容。"
    no_sub, ns = detect_innovation(cue_only, relevance_tier="direct")
    assert no_sub is None
    assert "cue_without_substance" in ns


def test_rules_emit_relevance_and_gate_innovation():
    living = analyze_document_rules(
        document_id="r1",
        title="祈福创新",
        content="本文提出一种创新方法用于宠物毛发祈福编织，并首次用问卷验证价格。",
        content_type="literature_pdf",
        research_keywords=["毛发祈福"],
    )
    by_type = {}
    for c in living.claims:
        by_type.setdefault(c.claim_type, []).append(c.claim_value)
    assert by_type["relevance"] == ["direct"]
    assert by_type.get("innovation")

    academic = analyze_document_rules(
        document_id="r2",
        title="Machine learning forecast evaluation",
        content=(
            "Abstract. We propose a novel econometric framework for out-of-sample "
            "prediction of stock returns. References include et al. journal articles. "
            "DOI 10.1234/example. Keywords: forecast, ESG ratings, model."
        ),
        content_type="literature_pdf",
    )
    a_by = {c.claim_type: c.claim_value for c in academic.claims}
    assert a_by["relevance"] == "unrelated"
    assert "innovation" not in a_by
