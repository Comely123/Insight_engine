from insight_engine.db.connection import get_connection
from insight_engine.product.narrative import build_rule_narrative, narrative_to_markdown


def test_rule_narrative_has_recommendations(tmp_settings) -> None:
    with get_connection(tmp_settings.db_path) as conn:
        narrative = build_rule_narrative(
            conn=conn,
            document_ids=[],
            keywords=[],
            brief="文献共性测试",
            trend={
                "raw_documents": 162,
                "unique_documents": 159,
                "duplicate_documents": 3,
                "retention_rate": 159 / 162,
                "dedup_deletion_rate": 3 / 162,
                "independent_sources": 4,
                "platform_count": 4,
                "domain_count": 12,
                "independent_events": 90,
                "content_kind_counts": {"news": 4, "consumer_comment": 2},
                "behavior_stage_counts": {"interest": 2, "price_inquiry": 1},
                "demand_subtype_counts": {"living_blessing": 2},
                "stance_counts": {"neutral": 2, "negative": 1},
                "price_values": [99.0],
                "price_buckets": {"50-99": 1},
                "price_pending_review": [{"amount": 2026, "is_confirmed_price": False}],
                "warnings": [],
            },
            alerts=[],
            mode="collect",
        )
    assert narrative["recommendations"]
    assert narrative["findings"]
    assert narrative["analysis_profile"] == "market"
    joined = " ".join(narrative["findings"])
    assert "样本保留率" in joined
    assert "去重删除率" in joined
    assert "去重率约" not in joined
    assert "转载占比较高" not in joined
    assert "待审核" in joined
    md = narrative_to_markdown(narrative)
    assert "参考建议" in md
