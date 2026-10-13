from __future__ import annotations

from insight_engine.analysis.rules import analyze_document_rules
from insight_engine.models.analysis import DocumentAnalysisResult, IntentLabel, StancePolarity


def test_intent_payment_and_price_extraction():
    result = analyze_document_rules(
        document_id="doc-1",
        title="付款记录",
        content="昨天付款定制了两只猫的毛发祈福绳，商家报价 128 元。",
    )
    assert result.intent == IntentLabel.PAYMENT
    assert 128.0 in result.prices
    assert result.topic == "living_blessing"
    kinds = {c.claim_type: c.claim_value for c in result.claims if c.claim_type in {
        "content_kind", "research_topic", "behavior_stage", "demand_subtype"
    }}
    assert kinds.get("research_topic") == "living_blessing"
    assert kinds.get("demand_subtype") == "living_blessing"
    assert kinds.get("behavior_stage") == "payment"
    assert all(c.evidence for c in result.claims)
    assert all(ev.document_id == "doc-1" for c in result.claims for ev in c.evidence)
    # schema roundtrip
    DocumentAnalysisResult.model_validate(result.model_dump())


def test_negative_stance_and_interest():
    result = analyze_document_rules(
        document_id="doc-2",
        title="顾虑",
        content="把掉毛编成饰品听着不卫生，我不会买。",
    )
    assert result.stance == StancePolarity.NEGATIVE
    assert result.intent in {IntentLabel.INTEREST, IntentLabel.UNKNOWN, IntentLabel.INQUIRY}


def test_schema_rejects_foreign_document_evidence():
    payload = {
        "document_id": "doc-a",
        "claims": [
            {
                "claim_type": "topic",
                "claim_value": "other",
                "evidence": [{"document_id": "doc-b", "excerpt": "x"}],
            }
        ],
    }
    try:
        DocumentAnalysisResult.model_validate(payload)
        assert False, "should have raised"
    except Exception as exc:  # noqa: BLE001
        assert "document_id" in str(exc)
