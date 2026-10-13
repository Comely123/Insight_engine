"""Turn research brief into concrete analysis asks (not keyword restrictions)."""

from __future__ import annotations

import re
from typing import Any


_SPLIT = re.compile(r"[\n\r；;。！？?!]+|(?<=\d)[\.、]\s*")


def split_brief_asks(brief: str, *, limit: int = 24) -> list[str]:
    text = (brief or "").strip()
    if not text:
        return []
    asks: list[str] = []
    for part in _SPLIT.split(text):
        s = part.strip(" \t-•*·")
        s = re.sub(r"^\d+[\.\)、]\s*", "", s).strip()
        if len(s) < 4:
            continue
        asks.append(s)
        if len(asks) >= limit:
            break
    if not asks and text:
        asks = [text[:220]]
    return asks


def _haystack_from_context(
    *,
    keywords: list[str],
    themes: list[str],
    titles: list[str],
    findings: list[str],
    literature: dict[str, Any] | None,
) -> str:
    bits = [
        " ".join(keywords or []),
        " ".join(themes or []),
        " ".join(titles or []),
        " ".join(findings or []),
    ]
    for r in (literature or {}).get("rows") or []:
        bits.append(str(r.get("title") or ""))
        bits.append(str(r.get("top_terms") or ""))
        bits.append(str(r.get("excerpt") or ""))
        bits.append(str(r.get("innovation_hints") or ""))
    for key in ("commonality", "differences", "innovations"):
        for x in (literature or {}).get(key) or []:
            bits.append(str(x))
    return "\n".join(bits).lower()


def _tokens(ask: str) -> list[str]:
    # CJK bigrams/trigrams + ascii words (not whole clauses)
    toks: list[str] = []
    for m in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", ask):
        t = m.lower()
        if t not in toks:
            toks.append(t)
    cjk = re.findall(r"[\u4e00-\u9fff]+", ask)
    for run in cjk:
        if len(run) <= 4:
            if run not in toks:
                toks.append(run)
            continue
        for i in range(0, len(run) - 1):
            bi = run[i : i + 2]
            if bi not in toks:
                toks.append(bi)
        for i in range(0, len(run) - 2):
            tri = run[i : i + 3]
            if tri not in toks:
                toks.append(tri)
    # Prefer informative tokens first
    stop = {"如何", "什么", "哪些", "是否", "怎样", "以及", "还有", "这个", "那个"}
    toks = [t for t in toks if t not in stop]
    return toks[:16]


def cover_brief_asks(
    brief: str,
    *,
    keywords: list[str] | None = None,
    themes: list[str] | None = None,
    titles: list[str] | None = None,
    findings: list[str] | None = None,
    literature: dict[str, Any] | None = None,
) -> dict[str, Any]:
    asks = split_brief_asks(brief)
    if not asks:
        return {"asks": [], "rows": [], "coverage_lines": []}

    hay = _haystack_from_context(
        keywords=list(keywords or []),
        themes=list(themes or []),
        titles=list(titles or []),
        findings=list(findings or []),
        literature=literature,
    )
    rows: list[dict[str, Any]] = []
    lines: list[str] = []
    for ask in asks:
        toks = _tokens(ask)
        hits = [t for t in toks if t.lower() in hay or t in hay]
        if len(toks) == 0:
            status = "noted"
            note = "已记录该问题；样本中暂无清晰关键词锚点，结论保持审慎。"
        elif len(hits) >= max(1, (len(toks) + 1) // 2):
            status = "addressed"
            note = "样本中出现相关表述，已纳入本报告发现/对照。"
        elif hits:
            status = "partial"
            note = f"部分相关（命中：{'、'.join(hits[:6])}），证据仍薄。"
        else:
            status = "gap"
            note = "当前样本未直接覆盖该问题——已点名缺口，而非忽略。"
        rows.append({"ask": ask, "status": status, "hits": hits, "note": note})
        label = {
            "addressed": "已覆盖",
            "partial": "部分覆盖",
            "gap": "待补证据",
            "noted": "已记录",
        }.get(status, status)
        lines.append(f"[{label}] {ask} — {note}")

    return {"asks": asks, "rows": rows, "coverage_lines": lines}
