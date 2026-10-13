from insight_engine.product.literature import literature_rows_to_csv
from insight_engine.product.sample_fields import project_rows_for_export


def test_literature_csv_headers_chinese():
    rows = [
        {
            "title": "A paper",
            "year": "2024",
            "doi": "10.1/x",
            "innovation_hints": "提出|方法",
            "future_directions": "未来可扩展到…",
            "research_topic": "living_blessing",
            "relevance_tier": "direct",
            "content_kind": "academic",
            "document_id": "d1",
        }
    ]
    headers, projected = project_rows_for_export(rows, profile="literature")
    assert "年份" in headers
    assert "DOI" in headers
    assert "创新点" in headers
    assert "可发展方向/未来工作" in headers
    assert projected[0]["标题"] == "A paper"
    csv_text = literature_rows_to_csv(rows, profile="literature")
    assert "年份" in csv_text
    assert "DOI" in csv_text


def test_market_csv_has_trend_and_vc_columns():
    rows = [
        {
            "title": "市场调研",
            "status_quo": "现状：渗透率低",
            "market_trend": "趋势：增长",
            "future_directions": "可拓展下沉市场",
            "vc_note": "信号混杂",
            "innovation_hints": "新模式",
            "content_kind": "market_report",
            "document_id": "d2",
        }
    ]
    headers, projected = project_rows_for_export(rows, profile="market")
    assert "现状" in headers
    assert "市场趋势线索" in headers
    assert "未来可发展方向" in headers
    assert "风投视角线索（非投资建议）" in headers
    assert "创新点/新说法" in headers
    assert projected[0]["现状"]
    csv_text = literature_rows_to_csv(rows, profile="market")
    assert "市场趋势线索" in csv_text


def test_profiles_use_different_header_sets():
    h_lit, _ = project_rows_for_export([], profile="literature")
    h_mkt, _ = project_rows_for_export([], profile="market")
    assert "DOI" in h_lit
    assert "DOI" not in h_mkt
    assert "风投视角线索（非投资建议）" in h_mkt
    assert "风投视角线索（非投资建议）" not in h_lit
