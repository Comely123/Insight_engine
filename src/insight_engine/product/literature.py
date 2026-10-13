"""Batch literature breakdown: commonality, differences, innovation signals + CSV."""

from __future__ import annotations

import csv
import re
import sqlite3
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any

# Lightweight CJK / EN token pattern
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9\-]{2,}")

_INNOVATION_HINTS = (
    "创新",
    "首次",
    "提出",
    "新颖",
    "突破",
    "原创",
    "发明",
    "专利",
    "新方法",
    "新框架",
    "改进",
    "优于",
    "novel",
    "propose",
    "proposed",
    "first",
    "breakthrough",
    "innovative",
    "contribution",
)

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


def _tokens(text: str, *, limit: int = 80) -> list[str]:
    found = []
    for m in _TOKEN_RE.findall(text or ""):
        t = m.strip().lower() if m.isascii() else m.strip()
        if len(t) < 2 or t in _STOP:
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
) -> dict[str, Any]:
    if not document_ids:
        return {
            "rows": [],
            "common_terms": [],
            "unique_terms_by_doc": {},
            "innovation_notes": [],
            "commonality": [],
            "differences": [],
            "innovations": [],
        }

    ph = ",".join("?" for _ in document_ids)
    docs = conn.execute(
        f"""
        SELECT document_id, title, source_name, content_type,
               COALESCE(raw_content, normalized_content, '') AS body,
               is_duplicate
        FROM documents
        WHERE document_id IN ({ph})
        ORDER BY collected_at ASC
        """,
        document_ids,
    ).fetchall()

    # Prefer non-duplicates; if all dupes (edge), still analyze them
    active = [d for d in docs if int(d["is_duplicate"] or 0) == 0] or list(docs)

    per_doc_terms: dict[str, set[str]] = {}
    rows: list[dict[str, Any]] = []
    innovation_notes: list[str] = []

    for d in active:
        body = d["body"] or ""
        if body.strip() == "[ephemeral:cleared]":
            body = ""
        terms = _tokens(body)
        term_set = set(terms)
        per_doc_terms[d["document_id"]] = term_set
        innov_hits = [h for h in _INNOVATION_HINTS if h.lower() in body.lower()]
        title = d["title"] or d["document_id"][:8]
        if innov_hits:
            innovation_notes.append(
                f"[{title}] 含创新表述线索：" + "、".join(innov_hits[:6])
            )
        rows.append(
            {
                "document_id": d["document_id"],
                "title": title,
                "source_name": d["source_name"] or "",
                "content_type": d["content_type"] or "",
                "char_count": len(body),
                "top_terms": "；".join(terms[:15]),
                "innovation_hints": "；".join(innov_hits[:8]),
                "excerpt": _excerpt(body),
            }
        )

    # Term document frequency
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
        "未检出明显「创新/首次/提出」等表述；可开启大模型汇总以补充创新点解读。"
    ]

    return {
        "rows": rows,
        "common_terms": common_terms,
        "unique_terms_by_doc": unique_by_doc,
        "innovation_notes": innovation_notes,
        "commonality": commonality,
        "differences": differences,
        "innovations": innovations,
    }


def literature_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = StringIO()
    fields = [
        "document_id",
        "title",
        "source_name",
        "content_type",
        "char_count",
        "top_terms",
        "innovation_hints",
        "excerpt",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def write_literature_csv(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(literature_rows_to_csv(rows), encoding="utf-8-sig")
    return path
