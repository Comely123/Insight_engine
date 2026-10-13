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
                "raw_documents": 3,
                "unique_documents": 3,
                "independent_sources": 2,
                "independent_events": 1,
                "behavior_stage_counts": {"interest": 2, "price_inquiry": 1},
                "demand_subtype_counts": {"living_blessing": 2},
                "stance_counts": {"neutral": 2, "negative": 1},
                "price_values": [99.0],
                "price_buckets": {"50-99": 1},
                "warnings": [],
            },
            alerts=[],
            mode="upload",
        )
    assert narrative["recommendations"]
    assert narrative["findings"]
    md = narrative_to_markdown(narrative)
    assert "参考建议" in md
