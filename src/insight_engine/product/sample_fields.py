"""Deep per-document field mining for adaptive CSV columns."""

from __future__ import annotations

import re
from typing import Any

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", re.I)
_DATE_RE = re.compile(
    r"(20\d{2}[-/.年]\d{1,2}([-/.月]\d{1,2})?|20\d{2}\s*年\s*\d{1,2}\s*月)"
)

_FUTURE_CUES = (
    "未来",
    "展望",
    "进一步",
    "后续",
    "可发展",
    "发展方向",
    "future work",
    "further research",
    "outlook",
    "建议下一步",
    "下一步",
    "有待",
)
_LIMIT_CUES = ("局限", "不足", "limitation", "缺点", "风险", "挑战", "顾虑")
_STATUS_CUES = ("现状", "目前", "当前", "已有", "现有", "as of", "currently", "市场现状")
_TREND_CUES = (
    "趋势",
    "增长",
    "上升",
    "下滑",
    "渗透率",
    "同比",
    "环比",
    "cagr",
    "热度",
    "trend",
    "growth",
)
_COMPETE_CUES = ("竞品", "竞争", "对手", "替代", "comparable", "competitor", "格局")
_DEMAND_CUES = ("需求", "意愿", "付费", "询价", "痛点", "刚需", "demand", "willingness")
_PRICE_CUES = ("价格", "定价", "元", "￥", "$", "报价", "客单价", "price", "pricing")
_METHOD_CUES = ("方法", "问卷", "访谈", "实验", "模型", "框架", "method", "survey", "interview")
_FINDING_CUES = ("结论", "发现", "结果表明", "显示", "finding", "result", "表明")
_VC_POS = ("融资", "风投", "投资机会", "高增长", "蓝海", "可规模化", "护城河", "赛道")
_VC_NEG = ("饱和", "红海", "亏损", "监管风险", "难变现", "伪需求", "同质化严重")


def _window(text: str, cue: str, *, radius: int = 70) -> str | None:
    if not text or not cue:
        return None
    idx = text.lower().find(cue.lower()) if cue.isascii() else text.find(cue)
    if idx < 0:
        return None
    start = max(0, idx - radius // 3)
    end = min(len(text), idx + len(cue) + radius)
    snip = re.sub(r"\s+", " ", text[start:end]).strip()
    return snip


def _collect_windows(text: str, cues: tuple[str, ...], *, limit: int = 3) -> str:
    hits: list[str] = []
    for c in cues:
        w = _window(text, c)
        if w and w not in hits:
            hits.append(w)
        if len(hits) >= limit:
            break
    return " | ".join(hits)


def _first_year(text: str) -> str:
    m = _YEAR_RE.search(text or "")
    return m.group(0) if m else ""


def _first_doi(text: str) -> str:
    m = _DOI_RE.search(text or "")
    return m.group(0) if m else ""


def _first_date(text: str) -> str:
    m = _DATE_RE.search(text or "")
    return m.group(0) if m else ""


def _authors_guess(text: str) -> str:
    # Very light heuristic — do not invent
    for pat in (
        r"作者[:：]\s*([^\n]{2,80})",
        r"Authors?[:：]\s*([^\n]{2,80})",
        r"^([A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z]+)(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z]+)){0,4})",
    ):
        m = re.search(pat, text or "", re.M)
        if m:
            return m.group(1).strip()[:120]
    return ""


def vc_signal(text: str) -> str:
    """Descriptive investment-readiness note — not financial advice."""
    pos = sum(1 for c in _VC_POS if c.lower() in text.lower() or c in text)
    neg = sum(1 for c in _VC_NEG if c.lower() in text.lower() or c in text)
    demand = _collect_windows(text, _DEMAND_CUES, limit=1)
    price = _collect_windows(text, _PRICE_CUES, limit=1)
    if pos >= 2 and neg == 0:
        note = "样本出现偏积极的增长/融资语境；需另核验交易与合规证据"
    elif neg >= 2 and pos == 0:
        note = "样本偏谨慎/饱和/风险语境；不宜直接视为可投信号"
    elif pos or neg or demand or price:
        note = "信号混杂：可见需求/价格或风险表述，仅作线索、非投资建议"
    else:
        note = "样本未给出清晰投融资判断依据"
    return note


def mine_document_fields(
    *,
    title: str,
    body: str,
    source_name: str = "",
    content_type: str = "",
    published_at: str | None = None,
    original_url: str | None = None,
) -> dict[str, Any]:
    text = " ".join(x for x in [title or "", body or ""] if x)
    year = _first_year(published_at or "") or _first_year(text)
    date = (published_at or "").strip() or _first_date(text)
    doi = _first_doi(text)
    return {
        "year": year,
        "date": date[:40],
        "authors": _authors_guess(text),
        "doi": doi,
        "url": (original_url or "").strip(),
        "source_name": source_name or "",
        "content_type": content_type or "",
        "method_signals": _collect_windows(text, _METHOD_CUES),
        "finding_signals": _collect_windows(text, _FINDING_CUES),
        "status_quo": _collect_windows(text, _STATUS_CUES),
        "market_trend": _collect_windows(text, _TREND_CUES),
        "competition": _collect_windows(text, _COMPETE_CUES),
        "demand_signals": _collect_windows(text, _DEMAND_CUES),
        "price_signals": _collect_windows(text, _PRICE_CUES),
        "risks": _collect_windows(text, _LIMIT_CUES),
        "future_directions": _collect_windows(text, _FUTURE_CUES),
        "vc_note": vc_signal(text),
    }


# Profile → ordered (internal_key, chinese_header)
PROFILE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "literature": [
        ("year", "年份"),
        ("date", "日期"),
        ("title", "标题"),
        ("authors", "作者"),
        ("doi", "DOI"),
        ("source_name", "来源"),
        ("url", "链接"),
        ("research_topic", "研究主题"),
        ("relevance_tier", "相关度"),
        ("method_signals", "方法线索"),
        ("finding_signals", "发现/结论线索"),
        ("innovation_hints", "创新点"),
        ("innovation_evidence", "创新证据"),
        ("future_directions", "可发展方向/未来工作"),
        ("risks", "局限与风险"),
        ("top_terms", "高频词"),
        ("excerpt", "摘要摘录"),
        ("document_id", "文档ID"),
    ],
    "market": [
        ("title", "标题"),
        ("date", "日期"),
        ("year", "年份"),
        ("source_name", "来源/平台"),
        ("content_kind_label", "内容类型"),
        ("content_type", "入库类型"),
        ("research_topic", "研究主题"),
        ("relevance_tier", "相关度"),
        ("status_quo", "现状"),
        ("market_trend", "市场趋势线索"),
        ("demand_signals", "需求信号"),
        ("price_signals", "价格信号"),
        ("competition", "竞争/格局"),
        ("innovation_hints", "创新点/新说法"),
        ("innovation_evidence", "创新证据"),
        ("future_directions", "未来可发展方向"),
        ("risks", "风险与顾虑"),
        ("vc_note", "风投视角线索（非投资建议）"),
        ("top_terms", "高频词"),
        ("excerpt", "要点摘录"),
        ("url", "链接"),
        ("document_id", "文档ID"),
    ],
    "video": [
        ("title", "标题"),
        ("date", "日期"),
        ("source_name", "平台/来源"),
        ("content_type", "类型"),
        ("research_topic", "主题"),
        ("relevance_tier", "相关度"),
        ("top_terms", "主题词"),
        ("innovation_hints", "亮点/创新表述"),
        ("innovation_evidence", "证据摘录"),
        ("market_trend", "趋势线索"),
        ("demand_signals", "需求信号"),
        ("future_directions", "可发展方向"),
        ("risks", "顾虑"),
        ("excerpt", "内容摘要"),
        ("url", "链接"),
        ("document_id", "文档ID"),
    ],
    "mixed": [
        ("title", "标题"),
        ("year", "年份"),
        ("date", "日期"),
        ("source_name", "来源"),
        ("content_kind_label", "内容类型"),
        ("content_type", "入库类型"),
        ("research_topic", "研究主题"),
        ("relevance_tier", "相关度"),
        ("status_quo", "现状"),
        ("market_trend", "市场趋势"),
        ("method_signals", "方法线索"),
        ("finding_signals", "发现线索"),
        ("innovation_hints", "创新点"),
        ("innovation_evidence", "创新证据"),
        ("future_directions", "可发展方向"),
        ("demand_signals", "需求信号"),
        ("price_signals", "价格信号"),
        ("competition", "竞争"),
        ("risks", "风险顾虑"),
        ("vc_note", "风投视角线索（非投资建议）"),
        ("doi", "DOI"),
        ("top_terms", "高频词"),
        ("excerpt", "摘录"),
        ("url", "链接"),
        ("document_id", "文档ID"),
    ],
}

_KIND_ZH = {
    "academic": "学术论文",
    "market_report": "市场/行业报告",
    "survey_report": "调查报告",
    "inspection_report": "检验报告",
    "news": "新闻",
    "video_meta": "视频",
    "unknown": "未知",
}


def project_rows_for_export(
    rows: list[dict[str, Any]],
    *,
    profile: str,
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Returns (chinese_headers, projected_rows) for CSV / UI.
    Headers adapt to analysis profile; empty cells allowed.
    """
    cols = PROFILE_COLUMNS.get(profile) or PROFILE_COLUMNS["mixed"]
    headers = [zh for _, zh in cols]
    out: list[dict[str, str]] = []
    for r in rows:
        kind = str(r.get("content_kind") or r.get("content_type") or "")
        base = dict(r)
        base["content_kind_label"] = _KIND_ZH.get(kind, kind)
        row = {zh: str(base.get(key) or "") for key, zh in cols}
        out.append(row)
    return headers, out
