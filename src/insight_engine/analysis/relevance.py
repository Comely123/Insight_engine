"""Batch C: research-question relevance in four tiers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from insight_engine.analysis.rules import _find_excerpt
from insight_engine.config import REPO_ROOT
from insight_engine.models.analysis import EvidenceRef, ExtractedClaim

RelevanceTier = Literal["direct", "edge", "unrelated", "pending_review"]

DEFAULT_PATH = REPO_ROOT / "config" / "relevance_innovation.yaml"


@lru_cache(maxsize=4)
def load_relevance_config(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_PATH
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("relevance config root must be a mapping")
    return data


def reset_relevance_cache() -> None:
    load_relevance_config.cache_clear()


def _count_hits(text: str, keywords: list[str]) -> tuple[int, str | None]:
    hits = 0
    first: str | None = None
    lower = text.lower()
    for kw in keywords:
        if not kw:
            continue
        ok = kw.lower() in lower if kw.isascii() else kw in text
        if ok:
            hits += 1
            if first is None:
                first = kw
    return hits, first


def classify_relevance(
    text: str,
    *,
    research_topic: str | None = None,
    research_keywords: list[str] | None = None,
    research_brief: str | None = None,
) -> tuple[RelevanceTier, EvidenceRef | None, str]:
    """
    Returns (tier, evidence, reason).
    Does not force a tier when evidence is thin — prefer pending_review.
    """
    cfg = (load_relevance_config().get("relevance") or {})
    text = (text or "").strip()
    topic = (research_topic or "unknown").strip()
    strong = list(cfg.get("strong_anchors") or [])
    weak = list(cfg.get("weak_anchors") or [])
    min_chars = int(cfg.get("min_chars_for_unrelated") or 80)
    direct_topics = set(cfg.get("direct_topics") or [])
    edge_topics = set(cfg.get("edge_topics") or [])
    unrelated_topics = set(cfg.get("unrelated_topics") or [])

    if not text:
        return "pending_review", None, "empty_text"

    # Extra anchors from user keywords / brief tokens (2+ CJK or 3+ ascii)
    extra: list[str] = []
    for kw in research_keywords or []:
        k = (kw or "").strip()
        if len(k) >= 2:
            extra.append(k)
    brief = (research_brief or "").strip()
    if brief:
        for part in brief.replace("，", " ").replace(",", " ").split():
            if len(part) >= 2:
                extra.append(part)

    strong_hits, strong_kw = _count_hits(text, strong)
    weak_hits, weak_kw = _count_hits(text, weak)
    extra_hits, extra_kw = _count_hits(text, extra)

    ev_kw = strong_kw or extra_kw or weak_kw
    ev = _find_excerpt(text, ev_kw) if ev_kw else None

    if topic in unrelated_topics and strong_hits == 0 and extra_hits == 0:
        if len(text) >= min_chars:
            return "unrelated", ev, "topic_unrelated_no_anchor"
        return "pending_review", ev, "short_or_ambiguous_unrelated_topic"

    if strong_hits >= 1 or (topic in direct_topics and weak_hits >= 1):
        return "direct", ev, f"strong={strong_hits};topic={topic}"

    if topic in edge_topics or (weak_hits >= 1 and strong_hits == 0) or extra_hits >= 1:
        # Keyword-only match without strong service cues → edge
        if strong_hits == 0 and topic not in direct_topics:
            return "edge", ev, f"weak={weak_hits};extra={extra_hits};topic={topic}"

    if topic in direct_topics and weak_hits == 0 and strong_hits == 0:
        return "pending_review", ev, "direct_topic_without_text_anchor"

    if strong_hits == 0 and weak_hits == 0 and extra_hits == 0:
        if len(text) >= min_chars:
            return "unrelated", None, "no_domain_or_query_anchor"
        return "pending_review", None, "too_short_to_judge"

    return "pending_review", ev, "ambiguous_signals"


def build_relevance_claim(
    *,
    document_id: str,
    title: str | None,
    content: str | None,
    research_topic: str | None = None,
    research_keywords: list[str] | None = None,
    research_brief: str | None = None,
) -> tuple[ExtractedClaim, RelevanceTier, str]:
    text = " ".join(x for x in [title or "", content or ""] if x).strip()
    tier, ev, reason = classify_relevance(
        text,
        research_topic=research_topic,
        research_keywords=research_keywords,
        research_brief=research_brief,
    )
    if ev is None:
        evidence = [
            EvidenceRef(
                document_id=document_id,
                excerpt=(text[:120] or reason or tier),
            )
        ]
    else:
        evidence = [
            EvidenceRef(
                document_id=document_id,
                excerpt=ev.excerpt,
                char_start=ev.char_start,
                char_end=ev.char_end,
            )
        ]
    claim = ExtractedClaim(
        claim_type="relevance",
        claim_value=tier,
        confidence={
            "direct": 0.8,
            "edge": 0.55,
            "unrelated": 0.7,
            "pending_review": 0.3,
        }.get(tier, 0.3),
        is_inference=tier == "pending_review",
        evidence=evidence,
    )
    return claim, tier, reason
