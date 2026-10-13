"""Choose report posture from content genre — format (PDF) never forces literature."""

from __future__ import annotations

from typing import Any, Literal

AnalysisProfile = Literal["literature", "market", "video", "mixed"]

# Only true scholarly / academic labels
_LIT_KINDS = frozenset({"academic"})
_LIT_TYPES = frozenset({"literature", "academic", "academic_document"})

_VIDEO_KINDS = frozenset({"video_meta"})
_VIDEO_TYPES = frozenset(
    {"video_meta", "media_stub", "subtitle", "video", "audio", "media"}
)

# Market-facing genres (includes non-academic PDF reports)
_MARKET_KINDS = frozenset(
    {
        "news",
        "product_page",
        "consumer_comment",
        "activity_page",
        "market_report",
        "survey_report",
        "inspection_report",
    }
)
_MARKET_TYPES = frozenset(
    {
        "rss",
        "news",
        "html",
        "webpage",
        "product_page",
        "consumer_comment",
        "image_ocr",
        "source_code",
        "text",
        "csv",
        "json",
        "market_report",
        "survey_report",
        "inspection_report",
        "document",  # generic PDF/DOCX role — market-leaning, not literature
        "pdf_document",
    }
)

# Format-only leftovers that must NEVER boost literature share
_FORMAT_ONLY_TYPES = frozenset(
    {"pdf", "literature_pdf", "docx", "upload", "file"}
)


def _share(n: int, total: int) -> float:
    return (n / total) if total > 0 else 0.0


def detect_analysis_profile(
    *,
    mode: str,
    content_kind_counts: dict[str, Any] | None = None,
    content_types: list[str] | None = None,
    document_count: int = 0,
) -> AnalysisProfile:
    """
    Infer how the public report should be framed.

    - literature: only when content is judged academic (not because files are PDF)
    - market: reports / news / comments / generic docs / collect
    - video: media
    - mixed: no clear majority
    """
    kinds = {str(k): int(v) for k, v in (content_kind_counts or {}).items() if int(v) > 0}
    types = [
        str(t or "").lower()
        for t in (content_types or [])
        if t and str(t).lower() not in _FORMAT_ONLY_TYPES
    ]

    kind_total = sum(kinds.values()) or 0
    type_total = len(types)
    total = kind_total or type_total or max(document_count, 0)

    lit_n = sum(v for k, v in kinds.items() if k in _LIT_KINDS)
    video_n = sum(v for k, v in kinds.items() if k in _VIDEO_KINDS)
    market_n = sum(v for k, v in kinds.items() if k in _MARKET_KINDS)

    if type_total and kind_total == 0:
        lit_n = sum(1 for t in types if t in _LIT_TYPES)
        video_n = sum(1 for t in types if t in _VIDEO_TYPES)
        market_n = sum(1 for t in types if t in _MARKET_TYPES)
        total = type_total
    elif types:
        # Reinforce from types, but never let bare PDF inflate literature
        lit_n = max(lit_n, sum(1 for t in types if t in _LIT_TYPES))
        video_n = max(video_n, sum(1 for t in types if t in _VIDEO_TYPES))
        market_n = max(market_n, sum(1 for t in types if t in _MARKET_TYPES))
        total = max(total, type_total, document_count)

    lit_s = _share(lit_n, total)
    video_s = _share(video_n, total)
    market_s = _share(market_n, total)

    if lit_s >= 0.55:
        return "literature"
    if video_s >= 0.40 and video_s >= lit_s and video_s >= market_s:
        return "video"
    if mode == "collect" and lit_s < 0.45:
        if video_s >= 0.35:
            return "video"
        return "market"
    if market_s >= 0.35 and market_s >= lit_s:
        return "market"
    if lit_n and (video_n or market_n):
        return "mixed"
    if mode == "collect":
        return "market"
    if lit_n:
        return "literature"
    if video_n:
        return "video"
    # Upload of generic PDFs / docs without academic labels → market/mixed, not literature
    return "market" if mode == "collect" else "mixed"


def profile_section_labels(profile: AnalysisProfile) -> dict[str, str]:
    if profile == "literature":
        return {
            "commonality": "文献共性",
            "differences": "文献差异",
            "innovations": "创新点线索",
            "table": "文献拆解表",
            "csv": "导出文献表 CSV（动态表头）",
            "csv_name": "literature_breakdown.csv",
        }
    if profile == "video":
        return {
            "commonality": "视频主题共性",
            "differences": "视频内容差异",
            "innovations": "内容亮点 / 创新表述",
            "table": "视频样本对照表",
            "csv": "导出视频表 CSV（动态表头）",
            "csv_name": "video_breakdown.csv",
        }
    if profile == "market":
        return {
            "commonality": "样本共性（用语/主题）",
            "differences": "来源与观点差异",
            "innovations": "值得关注的新说法（非文献创新）",
            "table": "市场样本对照表",
            "csv": "导出市场表 CSV（动态表头）",
            "csv_name": "market_sample_breakdown.csv",
        }
    return {
        "commonality": "样本共性",
        "differences": "样本差异",
        "innovations": "创新 / 亮点线索",
        "table": "混合样本对照表",
        "csv": "导出样本表 CSV（动态表头）",
        "csv_name": "sample_breakdown.csv",
    }


def profile_show_batch_table(profile: AnalysisProfile) -> bool:
    return profile in {"literature", "video", "mixed", "market"}


def profile_emphasize_innovation(profile: AnalysisProfile) -> bool:
    return profile in {"literature", "mixed"}
