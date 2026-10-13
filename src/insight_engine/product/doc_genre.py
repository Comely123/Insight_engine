"""Genre from document *text*, not file extension. PDF ≠ literature."""

from __future__ import annotations

from typing import Literal

DocGenre = Literal[
    "academic",
    "market_report",
    "survey_report",
    "inspection_report",
    "generic",
]

# Strong scholarly cues (need enough hits to call it academic literature)
_ACADEMIC_CUES = (
    "doi",
    "arxiv",
    "pubmed",
    "et al",
    "references",
    "bibliography",
    "proceedings",
    "journal",
    "abstract",
    "参考文献",
    "peer-reviewed",
    "hypothesis",
    "实验方法",
    "研究方法",
)

# Industry / market / ops reports — NOT literature analysis posture
_MARKET_REPORT_CUES = (
    "市场调研",
    "市场分析",
    "市场规模",
    "市场检验",
    "行业报告",
    "产业报告",
    "竞争格局",
    "渗透率",
    "cagr",
    "同比",
    "环比",
    "市场份额",
    "商业计划",
    "可行性分析",
    "swot",
    "pest",
    "竞品分析",
    "用户画像",
    "付费意愿",
    "价格带",
)

_SURVEY_CUES = (
    "调查报告",
    "问卷调查",
    "调研问卷",
    "样本结构",
    "有效问卷",
    "回收率",
    "访谈提纲",
    "焦点小组",
    "survey report",
    "questionnaire",
    "respondent",
)

_INSPECTION_CUES = (
    "检验报告",
    "检测报告",
    "质检",
    "合格证",
    "抽检",
    "送检",
    "检验结论",
    "检测结果",
    "符合标准",
    "不合格项",
    "lab report",
    "test report",
    "inspection report",
)


def _score(text: str, cues: tuple[str, ...]) -> int:
    lower = text.lower()
    hits = 0
    for c in cues:
        if not c:
            continue
        if c.isascii():
            if c.lower() in lower:
                hits += 1
        elif c in text:
            hits += 1
    return hits


def classify_document_genre(text: str, *, title: str | None = None) -> DocGenre:
    """
    Decide analysis genre from content.
    File format (PDF/DOCX/…) is irrelevant here.
    """
    blob = f"{title or ''}\n{text or ''}".strip()
    if len(blob) < 20:
        return "generic"

    academic = _score(blob, _ACADEMIC_CUES)
    market = _score(blob, _MARKET_REPORT_CUES)
    survey = _score(blob, _SURVEY_CUES)
    inspect = _score(blob, _INSPECTION_CUES)

    # Highest score wins among non-academic report genres (avoid title substring traps).
    report_scores = {
        "market_report": market,
        "survey_report": survey,
        "inspection_report": inspect,
    }
    best_report, best_report_score = max(report_scores.items(), key=lambda x: x[1])
    if best_report_score >= 1 and best_report_score >= academic:
        return best_report  # type: ignore[return-value]

    # Need clearer scholarly signal — not "any PDF with one abstract-ish word"
    if academic >= 2 and academic > best_report_score:
        return "academic"
    if academic >= 3:
        return "academic"
    return "generic"


def genre_to_content_type(genre: DocGenre) -> str:
    """Ingest content_type stored on documents (format-agnostic role)."""
    return {
        "academic": "academic_document",
        "market_report": "market_report",
        "survey_report": "survey_report",
        "inspection_report": "inspection_report",
        "generic": "document",
    }[genre]


def genre_to_content_kind(genre: DocGenre) -> str:
    """Preferred content_kind when text match is weak."""
    return {
        "academic": "academic",
        "market_report": "market_report",
        "survey_report": "survey_report",
        "inspection_report": "inspection_report",
        "generic": "unknown",
    }[genre]
