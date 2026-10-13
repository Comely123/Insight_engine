from insight_engine.analysis.rules import analyze_document_rules, reset_rules_cache
from insight_engine.analysis.taxonomy import reset_taxonomy_cache
from insight_engine.product.doc_genre import (
    classify_document_genre,
    genre_to_content_type,
)


def setup_function() -> None:
    reset_rules_cache()
    reset_taxonomy_cache()


def test_pdf_market_report_not_literature():
    text = (
        "宠物毛发祈福市场调研报告。本报告分析市场规模、竞争格局与付费意愿，"
        "并给出市场份额与渗透率估算。竞品分析见第三章。"
    )
    assert classify_document_genre(text, title="市场检验报告") == "market_report"
    assert genre_to_content_type("market_report") == "market_report"

    result = analyze_document_rules(
        document_id="m1",
        title="市场调研报告",
        content=text,
        content_type="pdf",
    )
    kinds = {c.claim_type: c.claim_value for c in result.claims}
    assert kinds["content_kind"] == "market_report"
    assert kinds["content_kind"] != "academic"


def test_pdf_survey_and_inspection():
    assert (
        classify_document_genre("本次问卷调查回收有效问卷 320 份，回收率 64%。")
        == "survey_report"
    )
    assert (
        classify_document_genre("产品质量检验报告：检测结果符合标准，不合格项为 0。")
        == "inspection_report"
    )


def test_academic_still_detected_from_text():
    text = (
        "Abstract. We propose a novel framework. DOI 10.1234/x. "
        "References include et al. journal articles."
    )
    assert classify_document_genre(text) == "academic"
