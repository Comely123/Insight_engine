"""Build and export cite-checked research reports."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from insight_engine.reports.citations import validate_citations
from insight_engine.trends.metrics import TrendReport


def _collect_citations(
    conn: sqlite3.Connection,
    document_ids: list[str],
    limit: int = 40,
) -> list[dict[str, Any]]:
    if not document_ids:
        return []
    citations: list[dict[str, Any]] = []
    for doc_id in document_ids[:200]:
        row = conn.execute(
            """
            SELECT c.claim_id, c.claim_type, c.claim_value, c.polarity, c.is_inference,
                   d.document_id, d.title, d.original_url, d.source_name,
                   e.excerpt, e.segment_id, e.char_start, e.char_end
            FROM claims c
            JOIN documents d ON d.document_id = c.document_id
            LEFT JOIN evidence_links e ON e.claim_id = c.claim_id
            WHERE c.document_id = ?
            LIMIT 5
            """,
            (doc_id,),
        ).fetchall()
        for r in row:
            cite = {
                "document_id": r["document_id"],
                "claim_id": r["claim_id"],
                "claim_type": r["claim_type"],
                "claim_value": r["claim_value"],
                "polarity": r["polarity"],
                "is_inference": bool(r["is_inference"]),
                "title": r["title"],
                "source_name": r["source_name"],
                "original_url": r["original_url"],
                "excerpt": r["excerpt"] or (r["title"] or "")[:120],
                "segment_id": r["segment_id"],
            }
            if r["segment_id"]:
                seg = conn.execute(
                    "SELECT start_time, end_time FROM media_segments WHERE segment_id = ?",
                    (r["segment_id"],),
                ).fetchone()
                if seg:
                    cite["start_time"] = seg["start_time"]
                    cite["end_time"] = seg["end_time"]
            citations.append(cite)
            if len(citations) >= limit:
                return citations
    return citations


def build_research_report(
    conn: sqlite3.Connection,
    *,
    project: dict[str, Any],
    keyword_version: dict[str, Any] | None,
    report: TrendReport,
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    citations = _collect_citations(conn, report.document_ids)
    ok, errors = validate_citations(conn, citations)

    facts = [
        f"去重文档数={report.unique_documents}（原始={report.raw_documents}）",
        f"独立来源={report.independent_sources}，独立事件键={report.independent_events}",
        f"窗口={report.window_days}日，as_of={report.as_of}",
    ]
    inferences = [
        "增长率与主题占比为描述性统计，不表示因果关系。",
        "行为阶段为规则抽取，未核验前不得视为真实转化。",
    ]
    hypotheses = [
        "若独立来源与付款/履约证据同步增加，可能值得加深访谈与样本扩充。",
    ]
    pending = list(report.warnings) + [
        "预警含义是「值得进一步研究」，不是市场即将爆发的断言。"
    ]

    positive = [c for c in citations if c.get("polarity") == "positive"]
    negative = [c for c in citations if c.get("polarity") == "negative"]

    return {
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "research_question": project.get("research_question"),
            "target_market": project.get("target_market"),
            "geo_scope": project.get("geo_scope"),
            "time_start": project.get("time_start"),
            "time_end": project.get("time_end"),
        },
        "keyword_version": {
            "version_number": (keyword_version or {}).get("version_number"),
            "keywords": (keyword_version or {}).get("keywords"),
            "synonyms": (keyword_version or {}).get("synonyms"),
            "exclude_keywords": (keyword_version or {}).get("exclude_keywords"),
            "change_note": (keyword_version or {}).get("change_note"),
        },
        "data_scope": {
            "sample_unique_docs": report.unique_documents,
            "sample_raw_docs": report.raw_documents,
            "window_days": report.window_days,
            "as_of": report.as_of,
            "dedup_policy": "content_hash exact soft-dedup; media file_hash soft-dedup",
        },
        "metrics": report.to_dict(),
        "metric_definitions": report.definitions,
        "alerts": alerts,
        "positive_evidence": positive,
        "negative_evidence": negative,
        "citations": citations,
        "citation_validation": {"ok": ok, "errors": errors},
        "epistemics": {
            "facts": facts,
            "inferences": inferences,
            "hypotheses": hypotheses,
            "pending": pending,
        },
        "limitations": pending,
        "next_steps": [
            "人工核验付款/履约与正反证据摘录",
            "必要时新增关键词版本并注明变更原因",
            "补充独立来源后再解释增长",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    p = payload["project"]
    lines = [
        f"# 研究报告：{p.get('name')}",
        "",
        "## 1. 研究问题与范围",
        f"- 问题：{p.get('research_question') or '（未填写）'}",
        f"- 市场：{p.get('target_market') or '—'}",
        f"- 地理：{p.get('geo_scope') or '—'}",
        f"- 时间：{p.get('time_start') or '—'} ~ {p.get('time_end') or '—'}",
        "",
        "## 2. 数据来源及获取方式",
        "- 本地导入文本/媒体 + 规则/可选模型分析（见库内 sources）。",
        "",
        "## 3. 样本数量与时间覆盖",
        f"- 去重文档：{payload['data_scope']['sample_unique_docs']}",
        f"- 原始文档：{payload['data_scope']['sample_raw_docs']}",
        f"- 窗口：{payload['data_scope']['window_days']} 日，as_of={payload['data_scope']['as_of']}",
        "",
        "## 4. 清洗和去重口径",
        f"- {payload['data_scope']['dedup_policy']}",
        f"- 关键词版本：v{payload['keyword_version'].get('version_number')}",
        f"- 关键词：{payload['keyword_version'].get('keywords')}",
        "",
        "## 5. 需求类别和行为阶段",
        f"- behavior_stage：{payload['metrics'].get('behavior_stage_counts')}",
        f"- demand_subtype：{payload['metrics'].get('demand_subtype_counts')}",
        f"- intent（兼容）：{payload['metrics'].get('intent_counts')}",
        "",
        "## 6. 趋势指标与变化",
        f"- 独立来源：{payload['metrics'].get('independent_sources')}",
        f"- 独立事件：{payload['metrics'].get('independent_events')}",
        f"- 增长率：{payload['metrics'].get('growth_rate')}",
        f"- 主题：{payload['metrics'].get('topic_counts')}",
        "",
        "## 7. 价格和交易证据",
        f"- 价格样本：{payload['metrics'].get('price_values')}",
        f"- 价格区间：{payload['metrics'].get('price_buckets')}",
        "",
        "## 8. 正向证据",
    ]
    for c in payload.get("positive_evidence") or []:
        lines.append(
            f"- [{c.get('document_id')}] {c.get('excerpt')} "
            f"(url={c.get('original_url')}, t={c.get('start_time')})"
        )
    lines += ["", "## 9. 反向证据"]
    for c in payload.get("negative_evidence") or []:
        lines.append(
            f"- [{c.get('document_id')}] {c.get('excerpt')} "
            f"(url={c.get('original_url')}, t={c.get('start_time')})"
        )
    lines += ["", "## 10. 数据限制"]
    for x in payload.get("limitations") or []:
        lines.append(f"- {x}")
    lines += ["", "## 11. 结论与下一步（区分事实/推断/假设/待验证）"]
    epi = payload.get("epistemics") or {}
    lines.append("### 事实")
    for x in epi.get("facts") or []:
        lines.append(f"- {x}")
    lines.append("### 推断")
    for x in epi.get("inferences") or []:
        lines.append(f"- {x}")
    lines.append("### 假设")
    for x in epi.get("hypotheses") or []:
        lines.append(f"- {x}")
    lines.append("### 待验证")
    for x in epi.get("pending") or []:
        lines.append(f"- {x}")
    lines += ["", "### 下一步"]
    for x in payload.get("next_steps") or []:
        lines.append(f"- {x}")
    cite_ok = payload.get("citation_validation", {}).get("ok")
    lines += [
        "",
        f"## 引用校验：{'通过' if cite_ok else '失败'}",
    ]
    for err in payload.get("citation_validation", {}).get("errors") or []:
        lines.append(f"- {err}")
    lines.append("")
    return "\n".join(lines)


def export_report(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    out_dir: Path,
    basename: str = "research_report",
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    md_path = out_dir / f"{basename}.md"
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    paths["markdown"] = md_path

    json_path = out_dir / f"{basename}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["json"] = json_path

    csv_path = out_dir / f"{basename}_citations.csv"
    citations = payload.get("citations") or []
    fields = [
        "document_id",
        "claim_id",
        "claim_type",
        "claim_value",
        "polarity",
        "title",
        "source_name",
        "original_url",
        "excerpt",
        "segment_id",
        "start_time",
        "end_time",
        "is_inference",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in citations:
            writer.writerow(row)
    paths["csv"] = csv_path
    return paths
