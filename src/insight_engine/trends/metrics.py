"""Transparent, explainable trend metrics (Phase 2+4)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from insight_engine.analysis.price_extract import parse_price_claim_value
from insight_engine.analysis.rules import load_rules
from insight_engine.analysis.taxonomy import detect_taxonomy_conflicts


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class TrendReport:
    window_days: int
    as_of: str
    raw_documents: int = 0
    unique_documents: int = 0
    duplicate_documents: int = 0
    retention_rate: float | None = None
    dedup_deletion_rate: float | None = None
    independent_events: int = 0
    independent_sources: int = 0
    platform_count: int = 0
    domain_count: int = 0
    platform_counts: dict[str, int] = field(default_factory=dict)
    domain_counts: dict[str, int] = field(default_factory=dict)
    topic_counts: dict[str, int] = field(default_factory=dict)
    content_kind_counts: dict[str, int] = field(default_factory=dict)
    research_topic_counts: dict[str, int] = field(default_factory=dict)
    relevance_counts: dict[str, int] = field(default_factory=dict)
    innovation_counts: dict[str, int] = field(default_factory=dict)
    intent_counts: dict[str, int] = field(default_factory=dict)
    behavior_stage_counts: dict[str, int] = field(default_factory=dict)
    demand_subtype_counts: dict[str, int] = field(default_factory=dict)
    stance_counts: dict[str, int] = field(default_factory=dict)
    taxonomy_conflict_notes: list[str] = field(default_factory=list)
    price_values: list[float] = field(default_factory=list)
    price_buckets: dict[str, int] = field(default_factory=dict)
    price_pending_review: list[dict[str, Any]] = field(default_factory=list)
    daily_unique_docs: dict[str, int] = field(default_factory=dict)
    weekly_unique_docs: dict[str, int] = field(default_factory=dict)
    monthly_unique_docs: dict[str, int] = field(default_factory=dict)
    prior_window_unique_docs: int = 0
    prior_window_sources: int = 0
    growth_rate: float | None = None
    source_growth_rate: float | None = None
    top_source_share: float | None = None
    definitions: dict[str, str] = field(default_factory=dict)
    composition: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    confirmed_market_trend: bool = False
    document_ids: list[str] = field(default_factory=list)
    project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


METRIC_DEFINITIONS = {
    "raw_documents": "本批/窗口内匹配的全部文档数（含重复标记）。",
    "unique_documents": "is_duplicate=0 的最终可分析文档数（样本保留数）。",
    "duplicate_documents": "精确内容 hash 标记为完全重复的文档数。",
    "retention_rate": "unique_documents / raw_documents（样本保留率）。勿称为「去重率」。",
    "dedup_deletion_rate": "(raw - unique) / raw（去重删除率）。仅精确重复，不含近似重复。",
    "independent_sources": "兼容字段：distinct(source_name or source_id)，≈采集通道/平台名，不等于媒体机构数。",
    "platform_count": "distinct 采集平台名（source_name）数量。",
    "domain_count": "distinct URL 域名数量。",
    "independent_events": "distinct event_key（默认 topic|日期），不是已核验的现实事件数。",
    "price_values": "仅 is_confirmed_price=true 的金额，进入价格分布。",
    "price_pending_review": "未能确认语义的金额候选，不进入价格分布。",
    "growth_rate": "(本窗去重文档 - 前窗去重文档) / 前窗去重文档；前窗为0时为 null。",
    "content_kind_counts": "Batch B 维度1：内容类型/文体（新闻/学术/视频等），不是需求。",
    "research_topic_counts": "Batch B 维度2：研究主题（活体祈福/离世纪念/纪念品等）；纪念品≠离世纪念。",
    "behavior_stage_counts": "Batch B 维度3：行为阶段；立场中性≠无意向。unknown 允许保留。",
    "relevance_counts": "Batch C：相对研究问题的相关度四档（direct/edge/unrelated/pending_review）。",
    "innovation_counts": "Batch C：创新主张（须相关度=direct|edge，且同时有措辞线索+实质证据）。",
    "demand_subtype_counts": "兼容字段：仅当 research_topic 为 memorial/living_blessing 时映射。",
    "topic_counts": "兼容字段：镜像 research_topic。",
}


def _price_bucket(value: float) -> str:
    if value < 50:
        return "<50"
    if value < 100:
        return "50-99"
    if value < 150:
        return "100-149"
    if value < 200:
        return "150-199"
    return "200+"


def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def compute_trend_metrics(
    conn: sqlite3.Connection,
    *,
    window_days: int = 30,
    as_of: datetime | None = None,
    persist: bool = False,
    document_ids: Iterable[str] | None = None,
    project_id: str | None = None,
    ignore_time_window: bool = False,
) -> TrendReport:
    as_of = as_of or _utc_now()
    window_start = as_of - timedelta(days=window_days)
    prior_start = window_start - timedelta(days=window_days)
    id_filter = set(document_ids) if document_ids is not None else None
    # When caller scopes to explicit document_ids (e.g. public upload batch),
    # do not drop docs for missing timestamps / outside window.
    if document_ids is not None:
        ignore_time_window = True

    docs = conn.execute(
        """
        SELECT document_id, source_id, source_name, original_url,
               published_at, collected_at, is_duplicate
        FROM documents
        """
    ).fetchall()

    in_window: list[sqlite3.Row] = []
    prior_unique_rows: list[sqlite3.Row] = []
    for doc in docs:
        if id_filter is not None and doc["document_id"] not in id_filter:
            continue
        ts = _parse_iso(doc["published_at"]) or _parse_iso(doc["collected_at"])
        if ignore_time_window:
            in_window.append(doc)
            continue
        if ts is None:
            continue
        if window_start <= ts <= as_of:
            in_window.append(doc)
        elif prior_start <= ts < window_start and doc["is_duplicate"] == 0:
            prior_unique_rows.append(doc)

    unique_docs = [d for d in in_window if d["is_duplicate"] == 0]
    dup_docs = [d for d in in_window if d["is_duplicate"] == 1]
    sources = {d["source_name"] or d["source_id"] for d in unique_docs}
    prior_sources = {d["source_name"] or d["source_id"] for d in prior_unique_rows}
    prior_unique = len(prior_unique_rows)

    daily: dict[str, int] = {}
    weekly: dict[str, int] = {}
    monthly: dict[str, int] = {}
    for d in unique_docs:
        ts = _parse_iso(d["published_at"]) or _parse_iso(d["collected_at"])
        if ts is None:
            continue
        daily[ts.date().isoformat()] = daily.get(ts.date().isoformat(), 0) + 1
        wk = _iso_week_key(ts)
        weekly[wk] = weekly.get(wk, 0) + 1
        mk = f"{ts.year:04d}-{ts.month:02d}"
        monthly[mk] = monthly.get(mk, 0) + 1

    claim_rows = conn.execute(
        """
        SELECT c.claim_type, c.claim_value, c.polarity, c.document_id, d.published_at, d.collected_at,
               d.is_duplicate
        FROM claims c
        JOIN documents d ON d.document_id = c.document_id
        WHERE d.is_duplicate = 0
        """
    ).fetchall()

    topic_counts: dict[str, int] = {}
    content_kind_counts: dict[str, int] = {}
    research_topic_counts: dict[str, int] = {}
    relevance_counts: dict[str, int] = {}
    innovation_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {}
    behavior_counts: dict[str, int] = {}
    subtype_counts: dict[str, int] = {}
    stance_counts: dict[str, int] = {}
    prices: list[float] = []
    price_pending: list[dict[str, Any]] = []
    docs_with_claims: set[str] = set()
    unique_ids = {d["document_id"] for d in unique_docs}
    per_doc_kind: dict[str, str] = {}
    per_doc_topic: dict[str, str] = {}
    per_doc_stage: dict[str, str] = {}

    for row in claim_rows:
        if row["document_id"] not in unique_ids:
            continue
        if not ignore_time_window:
            ts = _parse_iso(row["published_at"]) or _parse_iso(row["collected_at"])
            if ts is None or not (window_start <= ts <= as_of):
                continue
        docs_with_claims.add(row["document_id"])
        did = row["document_id"]
        if row["claim_type"] == "topic":
            topic_counts[row["claim_value"]] = topic_counts.get(row["claim_value"], 0) + 1
        elif row["claim_type"] == "content_kind":
            content_kind_counts[row["claim_value"]] = (
                content_kind_counts.get(row["claim_value"], 0) + 1
            )
            per_doc_kind[did] = row["claim_value"]
        elif row["claim_type"] == "research_topic":
            research_topic_counts[row["claim_value"]] = (
                research_topic_counts.get(row["claim_value"], 0) + 1
            )
            per_doc_topic[did] = row["claim_value"]
        elif row["claim_type"] == "relevance":
            relevance_counts[row["claim_value"]] = (
                relevance_counts.get(row["claim_value"], 0) + 1
            )
        elif row["claim_type"] == "innovation":
            innovation_counts[row["claim_value"]] = (
                innovation_counts.get(row["claim_value"], 0) + 1
            )
        elif row["claim_type"] == "intent":
            intent_counts[row["claim_value"]] = intent_counts.get(row["claim_value"], 0) + 1
        elif row["claim_type"] == "behavior_stage":
            behavior_counts[row["claim_value"]] = behavior_counts.get(row["claim_value"], 0) + 1
            per_doc_stage[did] = row["claim_value"]
        elif row["claim_type"] == "demand_subtype":
            subtype_counts[row["claim_value"]] = subtype_counts.get(row["claim_value"], 0) + 1
        elif row["claim_type"] == "stance":
            key = row["polarity"] or row["claim_value"]
            stance_counts[key] = stance_counts.get(key, 0) + 1
        elif row["claim_type"] == "price":
            parsed = parse_price_claim_value(row["claim_value"])
            if not parsed:
                continue
            item = {
                "amount": parsed.get("amount"),
                "currency": parsed.get("currency"),
                "raw_expression": parsed.get("raw_expression"),
                "context": parsed.get("context"),
                "price_type": parsed.get("price_type"),
                "is_confirmed_price": bool(parsed.get("is_confirmed_price")),
                "source_id": parsed.get("source_id") or row["document_id"],
                "document_id": row["document_id"],
            }
            if item["is_confirmed_price"]:
                try:
                    prices.append(float(item["amount"]))
                except (TypeError, ValueError):
                    continue
            else:
                price_pending.append(item)

    conflict_counter: Counter[str] = Counter()
    for did in unique_ids:
        for note in detect_taxonomy_conflicts(
            content_kind=per_doc_kind.get(did, "unknown"),
            research_topic=per_doc_topic.get(did, "unknown"),
            behavior_stage=per_doc_stage.get(did, "unknown"),
        ):
            conflict_counter[note] += 1
    # Prefer research_topic_counts for topic_counts when available
    if research_topic_counts and not topic_counts:
        topic_counts = dict(research_topic_counts)

    # Events tied to filtered docs when possible
    event_rows = conn.execute(
        """
        SELECT e.event_id, e.event_key, e.event_time, e.created_at, c.document_id
        FROM events e
        LEFT JOIN claims c ON c.event_id = e.event_id
        """
    ).fetchall()
    independent_events = 0
    seen_keys: set[str] = set()
    for ev in event_rows:
        if id_filter is not None and ev["document_id"] and ev["document_id"] not in id_filter:
            continue
        if id_filter is not None and not ev["document_id"]:
            continue
        ts = _parse_iso(ev["event_time"]) or _parse_iso(ev["created_at"])
        if ts is None or not (window_start <= ts <= as_of):
            continue
        key = ev["event_key"] or ev["event_id"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        independent_events += 1

    price_buckets: dict[str, int] = {}
    for p in prices:
        b = _price_bucket(p)
        price_buckets[b] = price_buckets.get(b, 0) + 1

    unique_count = len(unique_docs)
    raw_count = len(in_window)
    dup_count = len(dup_docs)
    retention = (unique_count / raw_count) if raw_count else None
    deletion = (dup_count / raw_count) if raw_count else None

    platform_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()
    for d in unique_docs:
        platform_counter[str(d["source_name"] or d["source_id"] or "(unknown)")] += 1
        url = d["original_url"] or ""
        try:
            host = urlparse(url).netloc.lower() if url else ""
        except Exception:  # noqa: BLE001
            host = ""
        domain_counter[host or "(no-url)"] += 1

    growth = (unique_count - prior_unique) / prior_unique if prior_unique > 0 else None
    source_growth = (
        (len(sources) - len(prior_sources)) / len(prior_sources) if prior_sources else None
    )

    rules = load_rules()
    trend_cfg = rules.get("trends") or {}
    min_docs = int(trend_cfg.get("min_unique_docs", 5))
    max_share = float(trend_cfg.get("max_source_share", 0.7))

    warnings: list[str] = []
    top_share = None
    if unique_count < min_docs:
        warnings.append(
            f"低样本量：窗口内去重文档仅 {unique_count} 条（阈值 {min_docs}），不得表述为已确认市场趋势。"
        )
    if unique_count:
        counts = Counter((d["source_name"] or d["source_id"]) for d in unique_docs)
        top_source, top_n = counts.most_common(1)[0]
        top_share = top_n / unique_count
        if top_share >= max_share:
            warnings.append(
                f"来源高度集中：来源「{top_source}」占比 {top_share:.0%}（阈值 {max_share:.0%}）。"
            )
    if not docs_with_claims and unique_count:
        warnings.append("窗口内尚无结构化主张；请先运行分析。")
    if window_days not in {7, 30, 90}:
        warnings.append(f"非标准窗口 {window_days} 日；建议使用 7/30/90。")
    warnings.append("当前仅提供描述性统计；预警含义为「值得进一步研究」，非市场爆发断言。")

    composition = {
        "score_note": "不输出黑盒 AI 趋势分；以下为可加总组成部分与绝对数量。",
        "components": {
            "raw_documents": raw_count,
            "unique_documents": unique_count,
            "duplicate_documents": dup_count,
            "retention_rate": retention,
            "dedup_deletion_rate": deletion,
            "independent_events": independent_events,
            "independent_sources": len(sources),
            "platform_count": len(platform_counter),
            "domain_count": len(domain_counter),
            "growth_rate_vs_prior_window": growth,
            "source_growth_rate": source_growth,
            "topic_counts": topic_counts,
            "content_kind_counts": content_kind_counts,
            "research_topic_counts": research_topic_counts,
            "relevance_counts": relevance_counts,
            "innovation_counts": innovation_counts,
            "intent_counts": intent_counts,
            "behavior_stage_counts": behavior_counts,
            "demand_subtype_counts": subtype_counts,
            "stance_counts": stance_counts,
            "taxonomy_conflict_notes": dict(conflict_counter),
            "price_confirmed_sample_size": len(prices),
            "price_pending_review_count": len(price_pending),
        },
    }

    report = TrendReport(
        window_days=window_days,
        as_of=as_of.isoformat().replace("+00:00", "Z"),
        raw_documents=raw_count,
        unique_documents=unique_count,
        duplicate_documents=dup_count,
        retention_rate=retention,
        dedup_deletion_rate=deletion,
        independent_events=independent_events,
        independent_sources=len(sources),
        platform_count=len(platform_counter),
        domain_count=len(domain_counter),
        platform_counts=dict(platform_counter.most_common(40)),
        domain_counts=dict(domain_counter.most_common(40)),
        topic_counts=topic_counts or dict(research_topic_counts),
        content_kind_counts=content_kind_counts,
        research_topic_counts=research_topic_counts,
        relevance_counts=relevance_counts,
        innovation_counts=innovation_counts,
        intent_counts=intent_counts,
        behavior_stage_counts=behavior_counts,
        demand_subtype_counts=subtype_counts,
        stance_counts=stance_counts,
        taxonomy_conflict_notes=[f"{k}×{v}" for k, v in conflict_counter.most_common(20)],
        price_values=sorted(prices),
        price_buckets=price_buckets,
        price_pending_review=price_pending[:80],
        daily_unique_docs=dict(sorted(daily.items())),
        weekly_unique_docs=dict(sorted(weekly.items())),
        monthly_unique_docs=dict(sorted(monthly.items())),
        prior_window_unique_docs=prior_unique,
        prior_window_sources=len(prior_sources),
        growth_rate=growth,
        source_growth_rate=source_growth,
        top_source_share=top_share,
        definitions=METRIC_DEFINITIONS,
        composition=composition,
        warnings=warnings,
        confirmed_market_trend=False,
        document_ids=sorted(unique_ids),
        project_id=project_id,
    )

    if persist:
        conn.execute(
            """
            INSERT INTO trend_snapshots (
              snapshot_id, window_days, as_of, metrics_json, warnings_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                window_days,
                report.as_of,
                json.dumps(report.to_dict(), ensure_ascii=False),
                json.dumps(report.warnings, ensure_ascii=False),
                report.as_of,
            ),
        )
        conn.commit()

    return report
