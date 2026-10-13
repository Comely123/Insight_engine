"""Sanitize LLM narrative output — block invented dedup/repost claims (Batch A)."""

from __future__ import annotations

import re
from typing import Any

# Phrases that over-claim beyond exact-hash soft-dedup evidence.
_BLOCK_PATTERNS = [
    re.compile(r"去重率\s*约?\s*\d", re.I),
    re.compile(r"去重率"),
    re.compile(r"同源重复"),
    re.compile(r"同事件多篇转载"),
    re.compile(r"转载占比较高"),
    re.compile(r"转载占比"),
    re.compile(r"说明同源"),
]


def finding_is_blocked(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return any(p.search(t) for p in _BLOCK_PATTERNS)


def sanitize_narrative_lists(narrative: dict[str, Any]) -> dict[str, Any]:
    """Drop or neutralize LLM lines that invent dedup-rate / reprint assertions."""
    for key in ("findings", "recommendations", "literature_commonality", "literature_differences"):
        rows = narrative.get(key)
        if not isinstance(rows, list):
            continue
        cleaned = []
        for row in rows:
            s = str(row).strip()
            if finding_is_blocked(s):
                continue
            cleaned.append(s)
        narrative[key] = cleaned
    one = str(narrative.get("one_liner") or "")
    if finding_is_blocked(one):
        narrative["one_liner"] = "样本描述性统计（已过滤不当去重/转载表述）"
    return narrative


LLM_SYSTEM_GUARD = (
    "你是严谨的中文研究助理。只根据给定材料归纳，不要编造不存在的数据或引用。"
    "严禁使用「去重率」称呼样本保留率；去重删除率= (原始-保留)/原始。"
    "严禁在仅有精确重复删除时推断「同源转载/同事件转载占比较高」。"
    "没有转载图谱或事件归并证据时，不要写转载结论。"
    "价格未确认金额不得当作成交价。"
    "输出 JSON，键：summary(string), insights(array of string), "
    "recommendations(array of string), literature_commonality(array of string), "
    "literature_differences(array of string), literature_innovations(array of string)。"
)
