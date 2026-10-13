"""Rule-based public narrative + optional LLM enrichment (profile-adaptive)."""

from __future__ import annotations

import sqlite3
from typing import Any

from insight_engine.llm.base import LLMProvider
from insight_engine.product.analysis_profile import (
    detect_analysis_profile,
    profile_emphasize_innovation,
    profile_section_labels,
)
from insight_engine.product.brief_coverage import cover_brief_asks
from insight_engine.product.literature import build_export_table
from insight_engine.product.narrative_guards import (
    LLM_SYSTEM_GUARD,
    sanitize_narrative_lists,
)
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


def _doc_content_types(conn: sqlite3.Connection, document_ids: list[str]) -> list[str]:
    if not document_ids:
        return []
    ph = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"""
        SELECT content_type FROM documents
        WHERE document_id IN ({ph}) AND is_duplicate = 0
        """,
        document_ids,
    ).fetchall()
    return [str(r["content_type"] or "") for r in rows]


def _video_summaries(literature: dict[str, Any] | None, limit: int = 8) -> list[str]:
    rows = (literature or {}).get("rows") or []
    out: list[str] = []
    for r in rows:
        ctype = str(r.get("content_type") or "").lower()
        if ctype not in {"video_meta", "media_stub", "subtitle", "video", "media", "audio"}:
            # still allow when profile is video but type missing
            if not ctype:
                pass
            else:
                continue
        title = str(r.get("title") or "未命名")
        excerpt = str(r.get("excerpt") or "").strip()
        terms = str(r.get("top_terms") or "").strip()
        bit = f"《{title}》"
        if excerpt:
            bit += f"：{excerpt[:140]}"
        elif terms:
            bit += f"：关键词 {terms[:80]}"
        out.append(bit)
        if len(out) >= limit:
            break
    if not out:
        for r in rows[:limit]:
            title = str(r.get("title") or "未命名")
            excerpt = str(r.get("excerpt") or "").strip()
            if excerpt:
                out.append(f"《{title}》：{excerpt[:140]}")
            else:
                out.append(f"《{title}》")
    return out


def build_rule_narrative(
    *,
    conn: sqlite3.Connection,
    document_ids: list[str],
    keywords: list[str],
    brief: str,
    trend: dict[str, Any],
    alerts: list[dict[str, Any]],
    mode: str,
    literature: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unique = int(trend.get("unique_documents") or 0)
    sources = int(trend.get("independent_sources") or 0)
    behavior = trend.get("behavior_stage_counts") or {}
    subtype = trend.get("demand_subtype_counts") or {}
    content_kinds = trend.get("content_kind_counts") or {}
    research_topics = trend.get("research_topic_counts") or trend.get("topic_counts") or {}
    relevance = trend.get("relevance_counts") or (literature or {}).get("relevance_counts") or {}
    innovations_metric = trend.get("innovation_counts") or {}
    stance = trend.get("stance_counts") or {}
    prices = trend.get("price_values") or []
    buckets = trend.get("price_buckets") or {}
    tax_conflicts = trend.get("taxonomy_conflict_notes") or []
    lit_rows = (literature or {}).get("rows") or []
    content_types = _doc_content_types(conn, document_ids)
    if not content_types and lit_rows:
        content_types = [str(r.get("content_type") or "") for r in lit_rows]

    profile = detect_analysis_profile(
        mode=mode,
        content_kind_counts=content_kinds,
        content_types=content_types,
        document_count=unique or len(lit_rows),
    )
    labels = profile_section_labels(profile)
    show_innovation = profile_emphasize_innovation(profile)

    raw_n = int(trend.get("raw_documents") or unique or 0)
    dup_n = int(trend.get("duplicate_documents") or max(raw_n - unique, 0))
    retention = trend.get("retention_rate")
    deletion = trend.get("dedup_deletion_rate")
    if retention is None and raw_n:
        retention = unique / raw_n
    if deletion is None and raw_n:
        deletion = dup_n / raw_n
    platforms = int(trend.get("platform_count") or sources or 0)
    domains = int(trend.get("domain_count") or 0)
    pending_prices = trend.get("price_pending_review") or []
    growth = trend.get("growth_rate")

    # --- one-liner / degree positioning by profile ---
    if profile == "literature" and lit_rows:
        tier = f"文献分析：{len(lit_rows)} 篇样本，聚焦共性 / 差异 / 创新线索"
    elif profile == "video":
        tier = f"视频内容分析：{unique or len(lit_rows)} 条，聚焦主题共性、差异与要点摘要"
    elif profile == "market":
        if unique < 5 or sources <= 1:
            tier = (
                f"小样本市场趋势（n={unique}）：按现有材料做探索性归纳，"
                "证据强度随样本量缩放，不是「无法分析」"
            )
        elif behavior.get("payment", 0) + behavior.get("fulfillment", 0) > 0 and sources >= 3:
            tier = "市场趋势：已出现付款/履约类证据，仍偏小众验证阶段"
        elif behavior.get("purchase_intent", 0) + behavior.get("price_inquiry", 0) > 0:
            tier = "市场趋势：以兴趣与询价为主，商业化仍处早期试探"
        else:
            tier = "市场趋势：以公开讨论/资讯热度为主，交易证据链仍在形成中"
    else:
        tier = (
            f"混合样本分析：文献/资讯/媒体并存（保留 {unique} 条），"
            "报告按内容类型分块，避免一律按文献解读"
        )

    findings: list[str] = [
        (
            f"原始记录 {raw_n} 条，精确重复 {dup_n} 条，最终保留 {unique} 条"
            f"（样本保留率 {retention:.1%}，去重删除率 {deletion:.1%}）。"
            if raw_n and retention is not None and deletion is not None
            else f"最终保留样本 {unique} 条（原始 {raw_n}）。"
        ),
        f"本次报告画像：{ {'literature': '文献', 'market': '市场趋势', 'video': '视频', 'mixed': '混合'}[profile] }。",
    ]

    if profile in {"market", "mixed", "video"}:
        findings.append(
            f"采集平台约 {platforms} 个"
            + (f"，URL 域名约 {domains} 个" if domains else "")
            + f"；独立事件键约 {trend.get('independent_events') or 0} 个"
            "（事件键≠已核验现实事件；平台名≠媒体机构数）。"
        )
        if growth is not None:
            findings.append(f"相对前窗文档量变化率：{growth:.1%}（描述性，非爆发断言）。")
    elif profile == "literature":
        findings.append(
            f"来源通道约 {platforms} 个"
            + (f"，域名约 {domains} 个" if domains else "")
            + "；文献解读以正文证据与相关度为准。"
        )

    if dup_n and dup_n <= 5 and profile != "literature":
        findings.append(
            f"本次仅精确删除 {dup_n} 条重复，不足以推断同源转载或同事件多篇转载占比。"
        )

    if keywords:
        findings.append("关注关键词：" + "、".join(keywords[:12]) + "。")
    if brief.strip():
        findings.append(f"研究焦点：{brief.strip()[:220]}{'…' if len(brief.strip()) > 220 else ''}")

    ck = _zh_count(content_kinds)
    if ck:
        findings.append("内容类型：" + "、".join(ck[:6]) + "。")
    rt = _zh_count(research_topics)
    if rt:
        findings.append("研究主题：" + "、".join(rt[:6]) + "。")

    if profile in {"literature", "mixed"}:
        rel = _zh_count(relevance)
        if rel:
            findings.append("研究相关度：" + "、".join(rel[:6]) + "。")
        if innovations_metric and show_innovation:
            findings.append(
                f"创新主张（相关度门控+实质证据）"
                f"{sum(int(v) for v in innovations_metric.values())} 条。"
            )

    if profile in {"market", "mixed", "video"}:
        beh = _zh_count(behavior)
        if beh:
            findings.append("行为/意向阶段：" + "、".join(beh[:6]) + "。")
        sub = _zh_count(subtype)
        if sub:
            findings.append("需求子集：" + "、".join(sub[:5]) + "。")
        stc = _zh_count(stance)
        if stc:
            findings.append("立场分布（中性≠无购买意向）：" + "、".join(stc[:5]) + "。")
        if buckets:
            findings.append(
                "已确认价格分布（未确认金额未计入）：" + "、".join(_zh_count(buckets)[:5]) + "。"
            )
        elif prices:
            findings.append(f"已确认价格样本 {len(prices)} 个；仍建议对照原文核验。")
        if pending_prices:
            findings.append(
                f"另有 {len(pending_prices)} 条疑似金额进入待审核区，未计入价格分布。"
            )

    if tax_conflicts:
        findings.append("分类冲突提示：" + "；".join(str(x) for x in tax_conflicts[:5]) + "。")

    themes = _top_claim_themes(conn, document_ids)
    titles = _doc_titles(conn, document_ids)
    video_sums = _video_summaries(literature) if profile in {"video", "mixed"} else []

    recommendations: list[str] = []
    if profile == "literature":
        recommendations.append(
            "对照拆解表：先看相关度四档与共现主题词，再核验创新是否同时具备措辞+实质证据。"
        )
        if unique < 3:
            recommendations.append(
                "文献篇数偏少：已做小样本对照；补充同主题论文可提高共性稳定性。"
            )
    elif profile == "video":
        recommendations.append(
            "优先看视频主题共性与单条摘要；有字幕/转写时再下沉到行为与价格信号。"
        )
        if unique < 5:
            recommendations.append(
                "视频样本偏少：已基于现有材料归纳；扩大采集或补传可增强趋势可信度。"
            )
    else:  # market / mixed
        if unique < 5:
            recommendations.append(
                "小样本不妨碍趋势归纳：结论已按证据强度降级表述；"
                "扩大关键词或补传可把探索性观察升级为更稳的市场判断。"
            )
        if behavior.get("price_inquiry", 0) or behavior.get("purchase_intent", 0):
            recommendations.append(
                "已有询价/意向信号：整理可核验的价格与交付说明，对照付费门槛。"
            )
        if behavior.get("payment", 0) + behavior.get("fulfillment", 0) == 0:
            recommendations.append(
                "缺少付款/履约硬证据：讨论热度≠可规模化成交，但可作为下一步验证清单。"
            )
        if (stance.get("negative", 0) or 0) >= max(1, (stance.get("positive", 0) or 0)):
            recommendations.append(
                "负面/顾虑声音不少：单独列出卫生、隐私、信任、价格等顾虑并对照证据。"
            )
        if profile == "mixed":
            recommendations.insert(
                0,
                "混合样本：文献块看共性/创新，资讯/视频块看市场信号与摘要，勿混为一谈。",
            )
    if not recommendations:
        recommendations.append(
            "保持描述性结论：区分「讨论热度」与「交易证据」，并按样本类型选择解读框架。"
        )

    # Batch breakdown text — only attach lit-style innovation emphasis for literature
    commonality = list((literature or {}).get("commonality") or [])
    differences = list((literature or {}).get("differences") or [])
    innovations = list((literature or {}).get("innovations") or []) if show_innovation else []
    if profile == "market":
        # Soften literature-specific innovation boilerplate
        innovations = [
            x
            for x in list((literature or {}).get("innovations") or [])
            if "未检出" not in x and "门控" not in x
        ][:5]
    if profile == "video" and video_sums:
        commonality = [f"视频要点摘录（{len(video_sums)}）："] + video_sums[:5] + commonality[:3]
    if titles and not commonality:
        commonality.append("样本标题摘录：" + "；".join(titles[:8]))
    if themes and profile != "video":
        commonality.append("结构化主题频次：" + "；".join(themes[:8]))

    # Research brief = analysis agenda (expand, do not restrict keywords)
    brief_cov = cover_brief_asks(
        brief,
        keywords=keywords,
        themes=themes,
        titles=titles,
        findings=findings,
        literature=literature,
    )
    if brief_cov.get("coverage_lines"):
        findings.append(
            "研究说明逐条对照（说明用于「要分析什么」，不收缩检索范围）："
        )
        findings.extend(brief_cov["coverage_lines"][:16])
        gap_n = sum(1 for r in brief_cov.get("rows") or [] if r.get("status") == "gap")
        if gap_n:
            recommendations.insert(
                0,
                f"研究说明中有 {gap_n} 条在当前样本中证据不足：优先补采/补传对应材料后再下强结论。",
            )

    scope = {
        "literature": "用户上传文献 / 学术采集（分析后原文清除）",
        "video": "视频与媒体样本（分析后原文清除）",
        "market": "公开资讯采集 / 非文献上传（分析后原文清除）",
        "mixed": "混合样本（文献+资讯/媒体；分析后原文清除）",
    }[profile]

    disclaimer = {
        "literature": "结论基于本次文献样本的描述性对照与证据结构；不提供主观创新打分。原文已按策略清除。",
        "video": "结论基于视频元数据/字幕/转写可提取文本；不是播放量或完播率审计。原文已按策略清除。",
        "market": "结论为描述性市场线索，不是投资建议或规模化成交断言。原文已按策略清除。",
        "mixed": "混合样本请分块阅读；勿把文献创新表述直接当成市场趋势。原文已按策略清除。",
    }[profile]

    export_tbl = build_export_table(lit_rows, profile=profile)

    return {
        "one_liner": tier,
        "analysis_profile": profile,
        "section_labels": labels,
        "scope": scope,
        "keywords": keywords,
        "research_brief": brief,
        "degree_positioning": tier,
        "findings": findings,
        "recommendations": recommendations,
        "literature_commonality": commonality,
        "literature_differences": differences,
        "literature_innovations": innovations,
        "literature_table": export_tbl["rows"],
        "literature_table_raw": lit_rows,
        "csv_headers": export_tbl["headers"],
        "video_summaries": video_sums,
        "brief_coverage": brief_cov,
        "show_batch_sections": True,
        "show_innovation_section": bool(innovations) and (
            show_innovation or profile in {"market", "video", "mixed"}
        ),
        "themes": themes,
        "sample_titles": titles,
        "stats": {
            "raw_documents": raw_n,
            "unique_documents": unique,
            "duplicate_documents": dup_n,
            "retention_rate": retention,
            "dedup_deletion_rate": deletion,
            "independent_sources": sources,
            "platform_count": platforms,
            "domain_count": domains,
            "platform_counts": trend.get("platform_counts"),
            "domain_counts": trend.get("domain_counts"),
            "independent_events": trend.get("independent_events"),
            "growth_rate": growth,
            "content_kind_counts": content_kinds,
            "research_topic_counts": research_topics,
            "relevance_counts": relevance,
            "innovation_counts": innovations_metric if show_innovation else {},
            "behavior_stage_counts": behavior,
            "demand_subtype_counts": subtype,
            "stance_counts": stance,
            "taxonomy_conflict_notes": tax_conflicts,
            "price_values": prices,
            "price_buckets": buckets,
            "price_pending_review": pending_prices,
            "analysis_profile": profile,
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
        "disclaimer": disclaimer,
    }


def enrich_narrative_with_llm(
    narrative: dict[str, Any],
    *,
    llm: LLMProvider,
) -> dict[str, Any]:
    if not llm.available():
        narrative["llm_enrichment"] = {"status": "skipped", "reason": "模型不可用或未填 Key"}
        return narrative
    profile = str(narrative.get("analysis_profile") or "market")
    labels = narrative.get("section_labels") or profile_section_labels(
        profile if profile in {"literature", "market", "video", "mixed"} else "market"
    )
    system = LLM_SYSTEM_GUARD
    if profile == "literature":
        system += (
            "本次画像=文献：强化共性、差异、创新点/贡献点；不要写成市场爆发或成交趋势。"
        )
        task = "请强化文献共性、差异点、创新点；并给出可执行的文献阅读/对照建议。"
    elif profile == "video":
        system += "本次画像=视频：总结主题共性、差异与单条要点；可提市场信号但勿夸大。"
        task = "请强化视频主题共性、内容差异与要点摘要；建议侧重补字幕/扩大样本。"
    elif profile == "mixed":
        system += "本次画像=混合：分块写文献与市场/视频，禁止把论文创新直接写成市场趋势。"
        task = "请分块归纳：文献块与市场/视频块分开；给出分类型的下一步建议。"
    else:
        system += (
            "本次画像=市场趋势：聚焦来源结构、讨论/意向/价格证据与风险顾虑；"
            "不要输出「文献创新点」口吻，除非材料明确是论文。"
            "样本少也要给出与证据强度匹配的趋势归纳，禁止写「无法分析」。"
        )
        task = "请强化市场趋势判断、需求信号、价格与顾虑；给出可执行的市场验证建议。"

    brief_asks = (narrative.get("brief_coverage") or {}).get("asks") or []
    if brief_asks:
        system += "必须逐条回应研究说明中的每个问题；证据不足就标明缺口，不可跳过。"
        task += "并逐条覆盖研究说明问题：" + " | ".join(str(x) for x in brief_asks[:20])

    table_brief = [
        {
            "title": r.get("title"),
            "top_terms": r.get("top_terms"),
            "innovation_hints": r.get("innovation_hints"),
            "relevance_tier": r.get("relevance_tier"),
            "content_type": r.get("content_type"),
            "char_count": r.get("char_count"),
        }
        for r in (narrative.get("literature_table") or [])[:12]
    ]
    user = (
        f"分析画像: {profile}\n"
        f"程度定位: {narrative.get('degree_positioning')}\n"
        f"发现: {narrative.get('findings')}\n"
        f"主题: {narrative.get('themes')}\n"
        f"标题: {narrative.get('sample_titles')}\n"
        f"视频摘要: {narrative.get('video_summaries')}\n"
        f"统计: {narrative.get('stats')}\n"
        f"样本表摘要: {table_brief}\n"
        f"已有{labels.get('commonality')}: {narrative.get('literature_commonality')}\n"
        f"已有{labels.get('differences')}: {narrative.get('literature_differences')}\n"
        f"已有{labels.get('innovations')}: {narrative.get('literature_innovations')}\n"
        f"{task}"
    )
    try:
        data = llm.complete_json(system_prompt=system, user_prompt=user, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        narrative["llm_enrichment"] = {"status": "failed", "reason": str(exc)}
        return narrative

    if data.get("summary"):
        narrative["one_liner"] = str(data["summary"])[:300]
        narrative["degree_positioning"] = narrative["one_liner"]
    if isinstance(data.get("insights"), list) and data["insights"]:
        narrative["findings"] = [str(x) for x in data["insights"] if str(x).strip()]
    if isinstance(data.get("recommendations"), list) and data["recommendations"]:
        narrative["recommendations"] = [str(x) for x in data["recommendations"] if str(x).strip()]
    if isinstance(data.get("literature_commonality"), list) and data["literature_commonality"]:
        narrative["literature_commonality"] = [
            str(x) for x in data["literature_commonality"] if str(x).strip()
        ]
    if isinstance(data.get("literature_differences"), list) and data["literature_differences"]:
        narrative["literature_differences"] = [
            str(x) for x in data["literature_differences"] if str(x).strip()
        ]
    if isinstance(data.get("literature_innovations"), list) and data["literature_innovations"]:
        narrative["literature_innovations"] = [
            str(x) for x in data["literature_innovations"] if str(x).strip()
        ]
    sanitize_narrative_lists(narrative)
    narrative["llm_enrichment"] = {"status": "ok", "profile": profile}
    return narrative


def narrative_to_markdown(narrative: dict[str, Any]) -> str:
    labels = narrative.get("section_labels") or profile_section_labels("mixed")
    profile = narrative.get("analysis_profile") or ""
    lines = [
        f"# {narrative.get('one_liner') or '分析报告'}",
        "",
        f"分析画像：{profile}",
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
    if narrative.get("video_summaries"):
        lines += ["", "## 视频要点"]
        for x in narrative["video_summaries"]:
            lines.append(f"- {x}")
    if narrative.get("literature_commonality"):
        lines += ["", f"## {labels.get('commonality', '样本共性')}"]
        for x in narrative["literature_commonality"]:
            lines.append(f"- {x}")
    if narrative.get("literature_differences"):
        lines += ["", f"## {labels.get('differences', '样本差异')}"]
        for x in narrative["literature_differences"]:
            lines.append(f"- {x}")
    if narrative.get("literature_innovations") and narrative.get("show_innovation_section", True):
        lines += ["", f"## {labels.get('innovations', '亮点线索')}"]
        for x in narrative["literature_innovations"]:
            lines.append(f"- {x}")
    if narrative.get("alerts"):
        lines += ["", "## 关注点"]
        for a in narrative["alerts"]:
            lines.append(f"- {a.get('title')}: {a.get('reason')}")
    lines += ["", "## 说明", narrative.get("disclaimer") or ""]
    return "\n".join(lines)
