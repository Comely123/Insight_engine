"""Batch sample breakdown + profile-adaptive CSV export."""

from __future__ import annotations

import csv
import re
import sqlite3
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any

from insight_engine.analysis.innovation import build_innovation_claim, noise_terms
from insight_engine.analysis.relevance import classify_relevance
from insight_engine.analysis.taxonomy import classify_content_kind, classify_research_topic
from insight_engine.product.sample_fields import (
    mine_document_fields,
    project_rows_for_export,
)

# Lightweight CJK / EN token pattern
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9\-]{2,}")

_STOP = {
    "我们",
    "本文",
    "研究",
    "进行",
    "以及",
    "一个",
    "可以",
    "通过",
    "对于",
    "没有",
    "如果",
    "因为",
    "但是",
    "或者",
    "这个",
    "那个",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "have",
    "has",
    "been",
}


def _stop_set() -> set[str]:
    out = set(_STOP)
    for t in noise_terms():
        if t:
            out.add(t.lower() if t.isascii() else t)
    return out


def _tokens(text: str, *, limit: int = 80) -> list[str]:
    stop = _stop_set()
    found = []
    for m in _TOKEN_RE.findall(text or ""):
        t = m.strip().lower() if m.isascii() else m.strip()
        if len(t) < 2 or t in stop:
            continue
        found.append(t)
        if len(found) >= 4000:
            break
    counts = Counter(found)
    return [w for w, _ in counts.most_common(limit)]


def _excerpt(text: str, n: int = 180) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:n] + ("…" if len(t) > n else "")


def analyze_literature_batch(
    conn: sqlite3.Connection,
    document_ids: list[str],
    *,
    research_keywords: list[str] | None = None,
    research_brief: str | None = None,
) -> dict[str, Any]:
    if not document_ids:
        return {
            "rows": [],
            "export_rows": [],
            "export_headers": [],
            "common_terms": [],
            "unique_terms_by_doc": {},
            "innovation_notes": [],
            "commonality": [],
            "differences": [],
            "innovations": [],
            "relevance_counts": {},
            "profile": "mixed",
        }

    ph = ",".join("?" for _ in document_ids)
    docs = conn.execute(
        f"""
        SELECT document_id, title, source_name, content_type, original_url, published_at,
               COALESCE(raw_content, normalized_content, '') AS body,
               is_duplicate
        FROM documents
        WHERE document_id IN ({ph})
        ORDER BY collected_at ASC
        """,
        document_ids,
    ).fetchall()

    active = [d for d in docs if int(d["is_duplicate"] or 0) == 0] or list(docs)

    per_doc_terms: dict[str, set[str]] = {}
    rows: list[dict[str, Any]] = []
    innovation_notes: list[str] = []
    relevance_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()

    for d in active:
        body = d["body"] or ""
        if body.strip() == "[ephemeral:cleared]":
            body = ""
        title = d["title"] or d["document_id"][:8]
        text = " ".join(x for x in [title, body] if x).strip()
        terms = _tokens(body)
        term_set = set(terms)
        per_doc_terms[d["document_id"]] = term_set

        topic, _, _ = classify_research_topic(text)
        kind, _, _ = classify_content_kind(
            text, ingest_content_type=d["content_type"] or ""
        )
        kind_counts[kind] += 1
        tier, _, rel_reason = classify_relevance(
            text,
            research_topic=topic,
            research_keywords=research_keywords,
            research_brief=research_brief,
        )
        relevance_counts[tier] += 1

        innov_claim, innov_reason = build_innovation_claim(
            document_id=d["document_id"],
            title=title,
            content=body,
            relevance_tier=tier,
        )
        # Soft pass: pending_review may still carry useful “新说法” for reports
        if innov_claim is None and tier == "pending_review":
            innov_claim, innov_reason = build_innovation_claim(
                document_id=d["document_id"],
                title=title,
                content=body,
                relevance_tier="edge",
            )

        innov_hints = ""
        innov_evidence = ""
        if innov_claim is not None:
            innov_hints = innov_claim.claim_value
            innov_evidence = " | ".join(ev.excerpt for ev in innov_claim.evidence)
            innovation_notes.append(
                f"[{title}] 相关度={tier}；创新={innov_hints}；证据：{innov_evidence[:160]}"
            )
        elif innov_reason.startswith("cue_without_substance"):
            innovation_notes.append(
                f"[{title}] 有创新措辞但缺少实质证据（{innov_reason}），已忽略。"
            )

        deep = mine_document_fields(
            title=title,
            body=body,
            source_name=d["source_name"] or "",
            content_type=d["content_type"] or "",
            published_at=d["published_at"],
            original_url=d["original_url"],
        )
        # Prefer gated innovation text; else keep empty
        if not innov_hints and innov_reason.startswith("gated_by_relevance"):
            innov_hints = ""

        rows.append(
            {
                "document_id": d["document_id"],
                "title": title,
                "source_name": d["source_name"] or "",
                "content_type": d["content_type"] or "",
                "content_kind": kind,
                "char_count": len(body),
                "relevance_tier": tier,
                "relevance_reason": rel_reason,
                "research_topic": topic,
                "top_terms": "；".join(terms[:15]),
                "innovation_hints": innov_hints,
                "innovation_evidence": innov_evidence,
                "innovation_skip": "" if innov_claim else innov_reason,
                "excerpt": _excerpt(body),
                **deep,
            }
        )

    df: Counter[str] = Counter()
    for s in per_doc_terms.values():
        df.update(s)
    n = max(len(per_doc_terms), 1)
    common_terms = [t for t, c in df.most_common(40) if c >= 2 and c >= min(2, n)]
    unique_by_doc: dict[str, list[str]] = {}
    for doc_id, s in per_doc_terms.items():
        unique_by_doc[doc_id] = sorted(t for t in s if df[t] == 1)[:20]

    title_by_id = {r["document_id"]: r["title"] for r in rows}
    commonality = []
    if common_terms:
        commonality.append("多篇共现主题词：" + "、".join(common_terms[:20]))
    else:
        commonality.append("未检出稳定共现主题词（样本过短、抽字失败或主题分散）。")
    if relevance_counts:
        parts = [f"{k}×{v}" for k, v in relevance_counts.most_common()]
        commonality.append("研究相关度四档：" + "、".join(parts))

    differences = []
    for doc_id, uniq in unique_by_doc.items():
        if uniq:
            differences.append(
                f"[{title_by_id.get(doc_id, doc_id)}] 相对独特用语："
                + "、".join(uniq[:12])
            )
    if not differences:
        differences.append("各篇用词高度重叠，差异信号较弱。")

    innovations = innovation_notes or [
        "未检出稳定创新主张；仍可在 CSV 中查看现状/趋势/可发展方向等深度字段。"
    ]

    return {
        "rows": rows,
        "common_terms": common_terms,
        "unique_terms_by_doc": unique_by_doc,
        "innovation_notes": innovation_notes,
        "commonality": commonality,
        "differences": differences,
        "innovations": innovations,
        "relevance_counts": dict(relevance_counts),
        "content_kind_counts": dict(kind_counts),
    }


def literature_rows_to_csv(
    rows: list[dict[str, Any]],
    *,
    profile: str | None = None,
) -> str:
    """CSV with Chinese headers that change by analysis profile."""
    from insight_engine.product.analysis_profile import detect_analysis_profile

    prof = profile or "mixed"
    if profile is None and rows:
        kinds: Counter[str] = Counter()
        types: list[str] = []
        for r in rows:
            if r.get("content_kind"):
                kinds[str(r["content_kind"])] += 1
            if r.get("content_type"):
                types.append(str(r["content_type"]))
        prof = detect_analysis_profile(
            mode="upload",
            content_kind_counts=dict(kinds),
            content_types=types,
            document_count=len(rows),
        )

    headers, projected = project_rows_for_export(rows, profile=prof)
    buf = StringIO()
    if not headers:
        return ""
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in projected:
        writer.writerow(r)
    return buf.getvalue()


def write_literature_csv(
    rows: list[dict[str, Any]],
    path: Path,
    *,
    profile: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        literature_rows_to_csv(rows, profile=profile),
        encoding="utf-8-sig",
    )
    return path


def build_export_table(
    rows: list[dict[str, Any]],
    *,
    profile: str,
) -> dict[str, Any]:
    headers, projected = project_rows_for_export(rows, profile=profile)
    return {
        "headers": headers,
        "rows": projected,
        "profile": profile,
    }
