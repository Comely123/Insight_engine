"""Explainable rule-based trend alerts — 'worth further research', not market certainty."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from insight_engine.models.research import TrendAlertRecord
from insight_engine.research.behavior import load_research_rules
from insight_engine.trends.metrics import TrendReport


def _evidence_samples(
    conn: sqlite3.Connection,
    document_ids: list[str],
    *,
    polarity: str | None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not document_ids:
        return []
    placeholders = ",".join("?" for _ in document_ids[:200])
    params: list[Any] = list(document_ids[:200])
    sql = f"""
        SELECT c.claim_id, c.claim_type, c.claim_value, c.polarity, c.document_id,
               d.title, d.original_url, e.excerpt, e.segment_id
        FROM claims c
        JOIN documents d ON d.document_id = c.document_id
        LEFT JOIN evidence_links e ON e.claim_id = c.claim_id
        WHERE c.document_id IN ({placeholders})
    """
    if polarity:
        sql += " AND (c.polarity = ? OR c.claim_value = ?)"
        params.extend([polarity, polarity])
    sql += " LIMIT ?"
    params.append(limit * 3)
    rows = conn.execute(sql, params).fetchall()
    out = []
    seen = set()
    for r in rows:
        if r["claim_id"] in seen:
            continue
        seen.add(r["claim_id"])
        out.append(
            {
                "claim_id": r["claim_id"],
                "document_id": r["document_id"],
                "title": r["title"],
                "claim_type": r["claim_type"],
                "claim_value": r["claim_value"],
                "excerpt": r["excerpt"],
                "segment_id": r["segment_id"],
                "original_url": r["original_url"],
            }
        )
        if len(out) >= limit:
            break
    return out


def generate_alerts(
    conn: sqlite3.Connection,
    report: TrendReport,
    *,
    project_id: str | None,
    run_id: str | None,
) -> list[TrendAlertRecord]:
    cfg = (load_research_rules().get("alerts") or {})
    growth_th = float(cfg.get("growth_threshold", 0.5))
    min_docs = int(cfg.get("min_unique_docs", 5))
    max_share = float(cfg.get("max_source_share", 0.7))
    require_source_growth = bool(cfg.get("require_source_growth", True))

    alerts: list[TrendAlertRecord] = []
    supporting = _evidence_samples(conn, report.document_ids, polarity="positive")
    opposing = _evidence_samples(conn, report.document_ids, polarity="negative")
    # also stance claim_value
    if not opposing:
        opposing = _evidence_samples(conn, report.document_ids, polarity="negative")

    base_quality = "; ".join(report.warnings[:3]) if report.warnings else "无额外质量警告"

    if (
        report.growth_rate is not None
        and report.growth_rate >= growth_th
        and report.unique_documents >= min_docs
    ):
        source_ok = True
        reason = (
            f"去重文档相对前窗增长 {report.growth_rate:.0%} "
            f"（阈值 {growth_th:.0%}），样本量={report.unique_documents}。"
        )
        if require_source_growth and (
            report.source_growth_rate is None or report.source_growth_rate <= 0
        ):
            source_ok = False
            reason += " 但独立来源未同步增长，可能由转载/单源驱动。"
        alerts.append(
            TrendAlertRecord(
                alert_id=str(uuid.uuid4()),
                project_id=project_id,
                run_id=run_id,
                alert_type="volume_growth",
                severity="medium" if source_ok else "low",
                title="内容量相对历史基准上升（值得进一步研究）",
                trigger_reason=reason,
                metric_values={
                    "unique_documents": report.unique_documents,
                    "prior_unique_documents": report.prior_window_unique_docs,
                    "growth_rate": report.growth_rate,
                    "independent_sources": report.independent_sources,
                    "source_growth_rate": report.source_growth_rate,
                    "independent_events": report.independent_events,
                },
                compare_window_days=report.window_days,
                sample_size=report.unique_documents,
                supporting_evidence=supporting,
                opposing_evidence=opposing,
                quality_notes=base_quality,
                review_suggestion="核验是否由重复转载或采集规则变化导致；检查独立来源与事件是否同步。",
            )
        )

    if report.top_source_share is not None and report.top_source_share >= max_share:
        alerts.append(
            TrendAlertRecord(
                alert_id=str(uuid.uuid4()),
                project_id=project_id,
                run_id=run_id,
                alert_type="source_concentration",
                severity="high",
                title="来源过度集中（值得进一步研究 / 数据质量风险）",
                trigger_reason=(
                    f"头部来源占比 {report.top_source_share:.0%} ≥ {max_share:.0%}，"
                    "趋势可能不具代表性。"
                ),
                metric_values={
                    "top_source_share": report.top_source_share,
                    "independent_sources": report.independent_sources,
                    "unique_documents": report.unique_documents,
                },
                compare_window_days=report.window_days,
                sample_size=report.unique_documents,
                supporting_evidence=supporting[:3],
                opposing_evidence=opposing[:3],
                quality_notes=base_quality,
                review_suggestion="补充更多独立来源后再解释趋势。",
            )
        )

    if report.unique_documents < min_docs:
        alerts.append(
            TrendAlertRecord(
                alert_id=str(uuid.uuid4()),
                project_id=project_id,
                run_id=run_id,
                alert_type="low_sample",
                severity="high",
                title="低样本量警告",
                trigger_reason=(
                    f"去重文档 {report.unique_documents} < {min_docs}，"
                    "不得表述为已确认市场趋势。"
                ),
                metric_values={"unique_documents": report.unique_documents, "min_docs": min_docs},
                compare_window_days=report.window_days,
                sample_size=report.unique_documents,
                supporting_evidence=supporting[:2],
                opposing_evidence=opposing[:2],
                quality_notes=base_quality,
                review_suggestion="扩大样本或缩短结论力度。",
            )
        )

    # Behavior signal: payment/fulfillment present
    paid = report.behavior_stage_counts.get("payment", 0) + report.behavior_stage_counts.get(
        "fulfillment", 0
    )
    if paid > 0 and report.unique_documents >= min_docs:
        alerts.append(
            TrendAlertRecord(
                alert_id=str(uuid.uuid4()),
                project_id=project_id,
                run_id=run_id,
                alert_type="behavior_evidence",
                severity="medium",
                title="出现付款/履约类行为证据（值得进一步研究）",
                trigger_reason=f"behavior_stage 中 payment+fulfillment 计数={paid}。非市场规模估计。",
                metric_values={
                    "payment_fulfillment_claims": paid,
                    "behavior_stage_counts": report.behavior_stage_counts,
                    "demand_subtype_counts": report.demand_subtype_counts,
                },
                compare_window_days=report.window_days,
                sample_size=report.unique_documents,
                supporting_evidence=supporting,
                opposing_evidence=opposing,
                quality_notes=base_quality,
                review_suggestion="人工核验付款/履约主张的证据摘录与视频时间戳。",
            )
        )

    return alerts
