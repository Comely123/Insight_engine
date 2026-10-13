"""Rule-based topic / intent / price / stance extraction with evidence excerpts."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from insight_engine.config import REPO_ROOT
from insight_engine.models.analysis import (
    DocumentAnalysisResult,
    EvidenceRef,
    ExtractedClaim,
    IntentLabel,
    StancePolarity,
)

DEFAULT_RULES_PATH = REPO_ROOT / "config" / "analysis_rules.yaml"


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> dict[str, Any]:
    rules_path = Path(path) if path else DEFAULT_RULES_PATH
    with rules_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"analysis rules root must be a mapping: {rules_path}")
    return data


def reset_rules_cache() -> None:
    load_rules.cache_clear()


def _find_excerpt(text: str, keyword: str) -> EvidenceRef | None:
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        # also try original case for CJK
        idx = text.find(keyword)
    if idx < 0:
        return None
    start = max(0, idx - 40)
    end = min(len(text), idx + len(keyword) + 40)
    excerpt = text[start:end].strip()
    return EvidenceRef(
        document_id="",  # filled by caller
        excerpt=excerpt or keyword,
        char_start=start,
        char_end=end,
    )


def _classify_topic(text: str, rules: dict[str, Any]) -> tuple[str, str, EvidenceRef | None]:
    topics = rules.get("topics") or {}
    best_id = "other"
    best_label = str((topics.get("other") or {}).get("label", "其他"))
    best_hit: EvidenceRef | None = None
    best_score = 0
    for topic_id, meta in topics.items():
        if topic_id == "other":
            continue
        keywords = meta.get("keywords") or []
        hits = 0
        first_ev = None
        for kw in keywords:
            if kw and kw in text:
                hits += 1
                if first_ev is None:
                    first_ev = _find_excerpt(text, kw)
        if hits > best_score:
            best_score = hits
            best_id = topic_id
            best_label = str(meta.get("label") or topic_id)
            best_hit = first_ev
    return best_id, best_label, best_hit


def _classify_intent(text: str, rules: dict[str, Any]) -> tuple[IntentLabel, EvidenceRef | None]:
    for item in rules.get("intents") or []:
        intent_id = str(item.get("id", "unknown"))
        if intent_id == "unknown":
            continue
        for kw in item.get("keywords") or []:
            if kw and kw in text:
                try:
                    label = IntentLabel(intent_id)
                except ValueError:
                    label = IntentLabel.UNKNOWN
                return label, _find_excerpt(text, kw)
    return IntentLabel.UNKNOWN, None


def _classify_stance(text: str, rules: dict[str, Any]) -> tuple[StancePolarity, EvidenceRef | None]:
    stance = rules.get("stance") or {}
    for kw in (stance.get("negative") or {}).get("keywords") or []:
        if kw and kw in text:
            return StancePolarity.NEGATIVE, _find_excerpt(text, kw)
    for kw in (stance.get("positive") or {}).get("keywords") or []:
        if kw and kw in text:
            return StancePolarity.POSITIVE, _find_excerpt(text, kw)
    return StancePolarity.NEUTRAL, None


def _extract_prices(text: str, rules: dict[str, Any], *, source_id: str = ""):
    from insight_engine.analysis.price_extract import extract_structured_prices

    patterns = (rules.get("price") or {}).get("patterns") or []
    return extract_structured_prices(text, source_id=source_id, patterns=patterns)


def analyze_document_rules(
    *,
    document_id: str,
    title: str | None,
    content: str | None,
    rules_path: str | None = None,
    content_type: str | None = None,
    research_keywords: list[str] | None = None,
    research_brief: str | None = None,
) -> DocumentAnalysisResult:
    from insight_engine.analysis.innovation import build_innovation_claim
    from insight_engine.analysis.relevance import build_relevance_claim
    from insight_engine.analysis.taxonomy import build_taxonomy_claims, load_taxonomy

    rules = load_rules(rules_path)
    tax = load_taxonomy()
    text = " ".join(x for x in [title or "", content or ""] if x).strip()
    if not text:
        return DocumentAnalysisResult(
            document_id=document_id,
            topic="unknown",
            intent=IntentLabel.UNKNOWN,
            stance=StancePolarity.UNKNOWN,
            analyzer="rules",
            prompt_version=str(tax.get("prompt_version", "taxonomy-v2")),
            confidence=0.0,
            unknowns=["empty document content"],
        )

    # Batch B primary dimensions (independent)
    tax_claims, tax_meta = build_taxonomy_claims(
        document_id=document_id,
        title=title,
        content=content,
        ingest_content_type=content_type,
    )
    research_topic = str(tax_meta.get("research_topic") or "unknown")
    content_kind = str(tax_meta.get("content_kind") or "unknown")
    behavior_stage = str(tax_meta.get("behavior_stage") or "unknown")

    topic_labels = {
        str(t.get("id")): str(t.get("label") or t.get("id"))
        for t in (tax.get("research_topics") or [])
        if isinstance(t, dict)
    }
    topic_label = topic_labels.get(research_topic, research_topic)

    # Legacy intent kept for compatibility — not used as research_topic.
    intent, intent_ev = _classify_intent(text, rules)
    stance, stance_ev = _classify_stance(text, rules)
    price_hits = _extract_prices(text, rules, source_id=document_id)

    claims: list[ExtractedClaim] = list(tax_claims)
    facts: list[str] = [
        f"content_kind={content_kind}",
        f"research_topic={research_topic}",
        f"behavior_stage={behavior_stage}",
    ]
    for n in tax_meta.get("notes") or []:
        facts.append(f"taxonomy_note={n}")
    for c in tax_meta.get("conflicts") or []:
        facts.append(f"taxonomy_conflict={c}")

    # Batch C: relevance (4 tiers) then gated innovation (cue + substance)
    rel_claim, rel_tier, rel_reason = build_relevance_claim(
        document_id=document_id,
        title=title,
        content=content,
        research_topic=research_topic,
        research_keywords=research_keywords,
        research_brief=research_brief,
    )
    claims.append(rel_claim)
    facts.append(f"relevance={rel_tier}")
    facts.append(f"relevance_reason={rel_reason}")

    innov_claim, innov_reason = build_innovation_claim(
        document_id=document_id,
        title=title,
        content=content,
        relevance_tier=rel_tier,
    )
    if innov_claim is not None:
        claims.append(innov_claim)
        facts.append(f"innovation={innov_claim.claim_value}")
    else:
        facts.append(f"innovation_skip={innov_reason}")

    def bind(ev: EvidenceRef | None, fallback: str) -> EvidenceRef:
        if ev is None:
            excerpt = text[:120]
            return EvidenceRef(document_id=document_id, excerpt=excerpt or fallback)
        return EvidenceRef(
            document_id=document_id,
            excerpt=ev.excerpt,
            char_start=ev.char_start,
            char_end=ev.char_end,
            segment_id=ev.segment_id,
        )

    # Legacy topic claim mirrors research_topic (not old memorial_craft bag)
    claims.append(
        ExtractedClaim(
            claim_type="topic",
            claim_value=research_topic,
            confidence=0.7 if research_topic not in {"unknown", "unrelated"} else 0.3,
            is_inference=research_topic == "unknown",
            evidence=[bind(None, research_topic)],
        )
    )

    # demand_subtype: only when topic is one of the two demand-like research topics
    if research_topic in {"memorial", "living_blessing"}:
        demand_val = research_topic
    else:
        demand_val = "unknown"
    claims.append(
        ExtractedClaim(
            claim_type="demand_subtype",
            claim_value=demand_val,
            confidence=0.65 if demand_val != "unknown" else 0.2,
            is_inference=demand_val == "unknown",
            evidence=[bind(None, demand_val)],
        )
    )
    facts.append(f"demand_subtype={demand_val}")

    claims.append(
        ExtractedClaim(
            claim_type="intent",
            claim_value=intent.value,
            confidence=0.75 if intent != IntentLabel.UNKNOWN else 0.2,
            is_inference=intent == IntentLabel.UNKNOWN,
            evidence=[bind(intent_ev, intent.value)],
        )
    )
    facts.append(f"intent={intent.value}")

    claims.append(
        ExtractedClaim(
            claim_type="stance",
            claim_value=stance.value,
            polarity=stance,
            confidence=0.7 if stance != StancePolarity.NEUTRAL else 0.4,
            is_inference=False,
            evidence=[bind(stance_ev, stance.value)],
        )
    )

    prices: list[float] = []
    for hit in price_hits:
        ev = EvidenceRef(
            document_id="",
            excerpt=hit.context or hit.raw_expression,
            char_start=hit.char_start,
            char_end=hit.char_end,
        )
        claims.append(
            ExtractedClaim(
                claim_type="price",
                claim_value=hit.to_claim_value(),
                confidence=0.85 if hit.is_confirmed_price else 0.35,
                is_inference=not hit.is_confirmed_price,
                evidence=[bind(ev, hit.raw_expression)],
            )
        )
        if hit.is_confirmed_price:
            prices.append(hit.amount)
            facts.append(f"price_confirmed={hit.amount}")
        else:
            facts.append(f"price_pending={hit.amount}:{hit.price_type}")

    event_title = (title or text[:40]).strip()
    summary_parts = [
        f"文体:{content_kind}",
        f"主题:{topic_label}",
        f"相关:{rel_tier}",
        f"行为:{behavior_stage}",
        f"立场:{stance.value}",
    ]
    if innov_claim is not None:
        summary_parts.append(f"创新:{innov_claim.claim_value}")
    if prices:
        summary_parts.append(f"价格:{','.join(str(p) for p in prices)}")

    unknowns: list[str] = []
    if content_kind == "unknown":
        unknowns.append("content_kind unknown")
    if research_topic == "unknown":
        unknowns.append("research_topic unknown")
    if behavior_stage == "unknown":
        unknowns.append("behavior_stage unknown")
    if rel_tier == "pending_review":
        unknowns.append("relevance pending_review")

    inferences = list(tax_meta.get("conflicts") or [])
    if research_topic == "unrelated":
        inferences.append("research_topic=unrelated（与研究域锚点无关，非强制需求标签）")
    if rel_tier == "unrelated":
        inferences.append("relevance=unrelated（创新主张已门控，不计入创新）")
    elif innov_claim is None and innov_reason.startswith("gated_by_relevance"):
        inferences.append(f"innovation_gated:{innov_reason}")

    return DocumentAnalysisResult(
        document_id=document_id,
        topic=research_topic,
        topic_label=topic_label,
        intent=intent,
        stance=stance,
        prices=prices,
        event_title=event_title,
        event_summary="; ".join(summary_parts),
        claims=claims,
        facts=facts,
        inferences=inferences,
        unknowns=unknowns,
        analyzer="rules",
        prompt_version=str(tax.get("prompt_version", "taxonomy-v2")),
        confidence=0.65 if research_topic not in {"unknown", "unrelated"} and rel_tier in {"direct", "edge"} else 0.35,
    )
