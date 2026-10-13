"""Rule-based public narrative + optional LLM enrichment."""

from __future__ import annotations

import sqlite3
from typing import Any

from insight_engine.llm.base import LLMProvider
from insight_engine.ui.charts import LABEL_ZH


def _zh_count(counts: dict[str, Any] | None) -> list[str]:
    if not counts:
        return []
    items = sorted(counts.items(), key=lambda x: int(x[1]), reverse=True)
    return [f"{LABEL_ZH.get(str(k), str(k))}（{int(v)}）" for k, v in items if int(v) > 0]


def _top_claim_themes(conn: sqlite3.Connection, document_ids: list[str], limit: int = 8) -> list[str]:
    if not document_ids:
        return []
    ph = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"""
        SELECT claim_type, claim_value, COUNT(*) AS c
        FROM claims
        WHERE document_id IN ({ph})
          AND claim_value IS NOT NULL AND TRIM(claim_value) != ''
        GROUP BY claim_type, claim_value
        ORDER BY c DESC
        LIMIT ?
        """,
        [*document_ids, limit],
    ).fetchall()
    out = []
    for r in rows:
        label = LABEL_ZH.get(str(r["claim_value"]), str(r["claim_value"]))
        out.append(f"{r['claim_type']}: {label} ×{r['c']}")
    return out


def _doc_titles(conn: sqlite3.Connection, document_ids: list[str], limit: int = 12) -> list[str]:
    if not document_ids:
        return []
    ph = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"""
        SELECT title FROM documents
        WHERE document_id IN ({ph}) AND is_duplicate = 0
        ORDER BY collected_at DESC
        LIMIT ?
        """,
        [*document_ids, limit],
    ).fetchall()
    return [str(r["title"] or "（无标题）") for r in rows]


def build_rule_narrative(
    *,
    conn: sqlite3.Connection,
    document_ids: list[str],
    keywords: list[str],
    brief: str,
    trend: dict[str, Any],
    alerts: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    unique = int(trend.get("unique_documents") or 0)
    sources = int(trend.get("independent_sources") or 0)
    behavior = trend.get("behavior_stage_counts") or {}
    subtype = trend.get("demand_subtype_counts") or {}
    stance = trend.get("stance_counts") or {}
    prices = trend.get("price_values") or []
    buckets = trend.get("price_buckets") or {}

    if unique < 5 or sources <= 1:
        tier = "样本不足：仅能看作零星线索，尚不足以支撑规模化判断"
    elif behavior.get("payment", 0) + behavior.get("fulfillment", 0) > 0 and sources >= 3:
        tier = "已出现付款/履约类证据，但仍偏小众验证阶段"
    elif behavior.get("purchase_intent", 0) + behavior.get("price_inquiry", 0) > 0:
        tier = "以兴趣与询价为主，商业化仍处早期试探"
    else:
        tier = "以一般讨论/兴趣表达为主，尚未形成稳定交易证据链"

    findings: list[str] = [
        f"本次纳入去重样本 {unique} 条，独立来源约 {sources} 个，独立事件约 {trend.get('independent_events') or 0} 个。",
    ]
    if keywords:
        findings.append("关注关键词：" + "、".join(keywords[:12]) + "。")
    if brief.strip():
        findings.append(f"研究焦点：{brief.strip()[:220]}{'…' if len(brief.strip()) > 220 else ''}")

    beh = _zh_count(behavior)
    if beh:
        findings.append("行为阶段分布靠前：" + "、".join(beh[:5]) + "。")
    sub = _zh_count(subtype)
    if sub:
        findings.append("需求类型分布：" + "、".join(sub[:5]) + "。")
    stc = _zh_count(stance)
    if stc:
        findings.append("情绪/立场分布：" + "、".join(stc[:5]) + "。")
    if buckets:
        findings.append("价格线索区间：" + "、".join(_zh_count(buckets)[:5]) + "。")
    elif prices:
        findings.append(f"抽到价格样本 {len(prices)} 个，中位数附近可参考区间需结合原文核验。")

    themes = _top_claim_themes(conn, document_ids)
    titles = _doc_titles(conn, document_ids)

    recommendations: list[str] = []
    if unique < 5:
        recommendations.append("先补充更多独立来源样本（上传文献/材料或扩大采集关键词），再做趋势判断。")
    if behavior.get("price_inquiry", 0) or behavior.get("purchase_intent", 0):
        recommendations.append("已有询价/意向信号：建议整理可核验的价格与交付说明，便于对照付费门槛。")
    if behavior.get("payment", 0) + behavior.get("fulfillment", 0) == 0:
        recommendations.append("当前缺少付款/履约硬证据：不宜把讨论热度直接等同于可规模化成交。")
    if (stance.get("negative", 0) or 0) >= max(1, (stance.get("positive", 0) or 0)):
        recommendations.append("负面/顾虑声音不少：报告中应单独列出顾虑点（卫生、隐私、信任、价格等）并对照证据。")
    if mode == "upload" and unique >= 2:
        recommendations.append("上传批次请对照「文献/样本共性」：区分高频共性与个别文档特有观点。")
    if not recommendations:
        recommendations.append("保持描述性结论：区分「讨论热度」与「交易证据」，下一步优先补齐独立来源与价格履约线索。")

    literature: list[str] = []
    if titles:
        literature.append("样本标题摘录：" + "；".join(titles[:8]))
    if themes:
        literature.append("结构化主题频次：" + "；".join(themes[:8]))
    # Simple co-occurrence style note for literature batches
    if unique >= 3 and themes:
        literature.append(
            "共性观察：高频主张重复出现，说明主题集中；若高频项几乎来自同一来源，需降低外推强度。"
        )
    elif unique >= 3:
        literature.append("共性观察：主题标签较分散，当前更适合做探索性归纳，不宜给出单一结论。")

    return {
        "one_liner": tier,
        "scope": "用户上传 + 已开放公开资讯（分析后原文清除）",
        "keywords": keywords,
        "research_brief": brief,
        "degree_positioning": tier,
        "findings": findings,
        "recommendations": recommendations,
        "literature_commonality": literature,
        "themes": themes,
        "sample_titles": titles,
        "stats": {
            "raw_documents": trend.get("raw_documents"),
            "unique_documents": unique,
            "independent_sources": sources,
            "independent_events": trend.get("independent_events"),
            "behavior_stage_counts": behavior,
            "demand_subtype_counts": subtype,
            "stance_counts": stance,
            "price_values": prices,
            "price_buckets": buckets,
        },
        "alerts": [
            {
                "title": a.get("title"),
                "reason": a.get("trigger_reason"),
                "severity": a.get("severity"),
            }
            for a in alerts
        ],
        "warnings": trend.get("warnings") or [],
        "llm_enrichment": None,
        "disclaimer": (
            "结论基于本次样本的描述性统计与证据结构；不是投资建议，也不提供主观创新打分。"
            "原文在分析完成后已按策略清除。"
        ),
    }


def enrich_narrative_with_llm(
    narrative: dict[str, Any],
    *,
    llm: LLMProvider,
) -> dict[str, Any]:
    if not llm.available():
        narrative["llm_enrichment"] = {"status": "skipped", "reason": "模型不可用或未填 Key"}
        return narrative
    system = (
        "你是严谨的中文研究助理。只根据给定统计与主题做归纳，不要编造不存在的数据。"
        "输出 JSON，键：summary(string), insights(array of string), "
        "recommendations(array of string), literature_commonality(array of string)。"
    )
    user = (
        f"程度定位: {narrative.get('degree_positioning')}\n"
        f"发现: {narrative.get('findings')}\n"
        f"主题: {narrative.get('themes')}\n"
        f"标题: {narrative.get('sample_titles')}\n"
        f"统计: {narrative.get('stats')}\n"
        "请给出更充分的文字分析与可执行参考建议；若像文献批次，强调共性与分歧。"
    )
    try:
        data = llm.complete_json(system_prompt=system, user_prompt=user, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        narrative["llm_enrichment"] = {"status": "failed", "reason": str(exc)}
        return narrative

    if data.get("summary"):
        narrative["one_liner"] = str(data["summary"])[:300]
    if isinstance(data.get("insights"), list) and data["insights"]:
        narrative["findings"] = [str(x) for x in data["insights"] if str(x).strip()]
    if isinstance(data.get("recommendations"), list) and data["recommendations"]:
        narrative["recommendations"] = [str(x) for x in data["recommendations"] if str(x).strip()]
    if isinstance(data.get("literature_commonality"), list) and data["literature_commonality"]:
        narrative["literature_commonality"] = [
            str(x) for x in data["literature_commonality"] if str(x).strip()
        ]
    narrative["llm_enrichment"] = {"status": "ok"}
    return narrative


def narrative_to_markdown(narrative: dict[str, Any]) -> str:
    lines = [
        f"# {narrative.get('one_liner') or '分析报告'}",
        "",
        "## 程度定位",
        narrative.get("degree_positioning") or "",
        "",
        "## 主要发现",
    ]
    for x in narrative.get("findings") or []:
        lines.append(f"- {x}")
    lines += ["", "## 参考建议"]
    for x in narrative.get("recommendations") or []:
        lines.append(f"- {x}")
    lines += ["", "## 文献/样本共性"]
    for x in narrative.get("literature_commonality") or []:
        lines.append(f"- {x}")
    if narrative.get("alerts"):
        lines += ["", "## 关注点"]
        for a in narrative["alerts"]:
            lines.append(f"- {a.get('title')}: {a.get('reason')}")
    lines += ["", "## 说明", narrative.get("disclaimer") or ""]
    return "\n".join(lines)
