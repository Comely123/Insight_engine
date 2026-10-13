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


def _extract_prices(text: str, rules: dict[str, Any]) -> list[tuple[float, EvidenceRef]]:
    patterns = (rules.get("price") or {}).get("patterns") or []
    found: list[tuple[float, EvidenceRef]] = []
    seen: set[float] = set()
    for pattern in patterns:
        try:
            regex = re.compile(pattern)
        except re.error:
            continue
        for match in regex.finditer(text):
            amounts: list[float] = []
            if match.groupdict().get("amount"):
                amounts.append(float(match.group("amount")))
            if match.groupdict().get("low") and match.groupdict().get("high"):
                amounts.extend([float(match.group("low")), float(match.group("high"))])
            start, end = match.span()
            excerpt = text[max(0, start - 20) : min(len(text), end + 20)].strip()
            ev = EvidenceRef(
                document_id="",
                excerpt=excerpt or match.group(0),
                char_start=start,
                char_end=end,
            )
            for amount in amounts:
                if amount in seen:
                    continue
                seen.add(amount)
                found.append((amount, ev))
    return found


def analyze_document_rules(
    *,
    document_id: str,
    title: str | None,
    content: str | None,
    rules_path: str | None = None,
) -> DocumentAnalysisResult:
    rules = load_rules(rules_path)
    text = " ".join(x for x in [title or "", content or ""] if x).strip()
    if not text:
        return DocumentAnalysisResult(
            document_id=document_id,
            topic="other",
            intent=IntentLabel.UNKNOWN,
            stance=StancePolarity.UNKNOWN,
            analyzer="rules",
            prompt_version=str(rules.get("prompt_version", "rules-v1")),
            confidence=0.0,
            unknowns=["empty document content"],
        )

    topic_id, topic_label, topic_ev = _classify_topic(text, rules)
    intent, intent_ev = _classify_intent(text, rules)
    stance, stance_ev = _classify_stance(text, rules)
    price_hits = _extract_prices(text, rules)

    claims: list[ExtractedClaim] = []
    facts: list[str] = []

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

    claims.append(
        ExtractedClaim(
            claim_type="topic",
            claim_value=topic_id,
            confidence=0.7 if topic_id != "other" else 0.3,
            is_inference=topic_id == "other",
            evidence=[bind(topic_ev, topic_id)],
        )
    )
    facts.append(f"topic={topic_id}")

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
    for amount, ev in price_hits:
        prices.append(amount)
        claims.append(
            ExtractedClaim(
                claim_type="price",
                claim_value=str(amount),
                confidence=0.8,
                is_inference=False,
                evidence=[bind(ev, str(amount))],
            )
        )
        facts.append(f"price={amount}")

    # Phase 4: behavior_stage + demand_subtype (in addition to intent)
    from insight_engine.research.behavior import classify_behavior_and_subtype

    behavior_claims = classify_behavior_and_subtype(
        document_id=document_id, title=title, content=content
    )
    claims.extend(behavior_claims)
    for bc in behavior_claims:
        facts.append(f"{bc.claim_type}={bc.claim_value}")

    event_title = (title or text[:40]).strip()
    summary_parts = [f"主题:{topic_label}", f"意向:{intent.value}", f"立场:{stance.value}"]
    if prices:
        summary_parts.append(f"价格:{','.join(str(p) for p in prices)}")
    for bc in behavior_claims:
        summary_parts.append(f"{bc.claim_type}:{bc.claim_value}")

    return DocumentAnalysisResult(
        document_id=document_id,
        topic=topic_id,
        topic_label=topic_label,
        intent=intent,
        stance=stance,
        prices=prices,
        event_title=event_title,
        event_summary="; ".join(summary_parts),
        claims=claims,
        facts=facts,
        inferences=["topic=other 为兜底分类"] if topic_id == "other" else [],
        unknowns=["intent unknown"] if intent == IntentLabel.UNKNOWN else [],
        analyzer="rules",
        prompt_version=str(rules.get("prompt_version", "rules-v1")),
        confidence=0.65 if topic_id != "other" else 0.35,
    )
