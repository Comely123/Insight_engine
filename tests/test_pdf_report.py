from insight_engine.export.pdf_report import markdown_to_pdf_bytes, report_to_pdf_bytes


def test_markdown_to_pdf_bytes_chinese() -> None:
    data = markdown_to_pdf_bytes(
        "# 标题\n\n这是一段中文报告内容，包含价格 99 元与祈福关键词。\n",
        title="活动洞察报告",
    )
    assert data[:4] == b"%PDF"
    assert len(data) > 500


def test_report_to_pdf_includes_charts_not_csv_table() -> None:
    narrative = {
        "one_liner": "样本以新闻与视频为主",
        "analysis_profile": "mixed",
        "degree_positioning": "中等规模混合样本",
        "findings": ["新闻报道占多数"],
        "recommendations": ["继续扩大视频样本"],
        "disclaimer": "仅供研究参考",
        "stats": {
            "content_kind_counts": {"news": 12, "video_meta": 5},
            "relevance_counts": {
                "direct": 4,
                "edge": 3,
                "unrelated": 6,
                "pending_review": 4,
            },
            "research_topic_counts": {
                "religious_ritual": 5,
                "memorial": 3,
                "living_blessing": 2,
                "unknown": 4,
                "unrelated": 3,
            },
            "behavior_stage_counts": {"discussion": 8, "inquiry": 3},
        },
        # CSV table must NOT appear in PDF body
        "literature_table": [
            {"标题": "不应出现在PDF", "摘要": "secret-row"},
        ],
    }
    data = report_to_pdf_bytes(narrative, title="分析报告", include_charts=True)
    assert data[:4] == b"%PDF"
    assert len(data) > 1200
    # Ensure CSV table row payload did not leak into PDF bytes
    assert b"secret-row" not in data
    assert "不应出现在PDF".encode("utf-8") not in data
