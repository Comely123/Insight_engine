from insight_engine.product.analysis_profile import (
    detect_analysis_profile,
    profile_section_labels,
)
from insight_engine.db.connection import get_connection
from insight_engine.product.narrative import build_rule_narrative


def test_detect_literature_vs_market_vs_video():
    assert (
        detect_analysis_profile(
            mode="upload",
            content_kind_counts={"academic": 10},
            content_types=["academic_document"] * 10,
            document_count=10,
        )
        == "literature"
    )
    # PDF format alone must NOT force literature posture
    assert (
        detect_analysis_profile(
            mode="upload",
            content_kind_counts={"market_report": 8},
            content_types=["market_report"] * 8,
            document_count=8,
        )
        == "market"
    )
    assert (
        detect_analysis_profile(
            mode="upload",
            content_kind_counts={},
            content_types=["literature_pdf"] * 5,  # legacy format tag ignored
            document_count=5,
        )
        != "literature"
    )
    assert (
        detect_analysis_profile(
            mode="collect",
            content_kind_counts={"news": 8, "consumer_comment": 2},
            content_types=["rss"] * 10,
            document_count=10,
        )
        == "market"
    )
    assert (
        detect_analysis_profile(
            mode="upload",
            content_kind_counts={"video_meta": 6},
            content_types=["video_meta"] * 6,
            document_count=6,
        )
        == "video"
    )
    # Scholarly API collect still literature when papers dominate
    assert (
        detect_analysis_profile(
            mode="collect",
            content_kind_counts={"academic": 20},
            content_types=["literature"] * 20,
            document_count=20,
        )
        == "literature"
    )


def test_market_narrative_not_literature_framed(tmp_settings) -> None:
    with get_connection(tmp_settings.db_path) as conn:
        narrative = build_rule_narrative(
            conn=conn,
            document_ids=[],
            keywords=["毛发祈福", "价格"],
            brief="看市场热度与成交信号",
            trend={
                "raw_documents": 40,
                "unique_documents": 36,
                "duplicate_documents": 4,
                "retention_rate": 0.9,
                "dedup_deletion_rate": 0.1,
                "independent_sources": 6,
                "platform_count": 6,
                "domain_count": 10,
                "independent_events": 12,
                "content_kind_counts": {"news": 20, "consumer_comment": 10},
                "behavior_stage_counts": {"interest": 10, "price_inquiry": 4},
                "research_topic_counts": {"living_blessing": 15},
                "stance_counts": {"neutral": 20},
                "price_values": [99.0],
                "price_buckets": {"50-99": 1},
                "warnings": [],
            },
            alerts=[],
            mode="collect",
            literature={"rows": [], "commonality": [], "differences": [], "innovations": []},
        )
    assert narrative["analysis_profile"] == "market"
    assert "市场" in narrative["one_liner"]
    assert "文献批次" not in narrative["one_liner"]
    assert "文献分析" not in narrative["one_liner"]
    labels = profile_section_labels("market")
    assert labels["commonality"] != "文献共性"


def test_literature_narrative_keeps_lit_framing(tmp_settings) -> None:
    with get_connection(tmp_settings.db_path) as conn:
        narrative = build_rule_narrative(
            conn=conn,
            document_ids=[],
            keywords=["祈福"],
            brief="文献综述",
            trend={
                "unique_documents": 5,
                "raw_documents": 5,
                "content_kind_counts": {"academic": 5},
                "research_topic_counts": {"living_blessing": 3},
                "relevance_counts": {"direct": 3, "edge": 2},
                "independent_sources": 2,
                "platform_count": 2,
                "warnings": [],
            },
            alerts=[],
            mode="upload",
            literature={
                "rows": [
                    {
                        "document_id": "d1",
                        "title": "paper",
                        "content_type": "literature_pdf",
                        "excerpt": "提出创新方法",
                    }
                ]
                * 5,
                "commonality": ["共现：祈福"],
                "differences": ["差异：A"],
                "innovations": ["创新：方法"],
            },
        )
    assert narrative["analysis_profile"] == "literature"
    assert "文献" in narrative["one_liner"]
    assert narrative["section_labels"]["commonality"] == "文献共性"
