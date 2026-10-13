"""Behavior stage and demand subtype classification (config-driven)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from insight_engine.analysis.rules import _find_excerpt
from insight_engine.config import REPO_ROOT
from insight_engine.models.analysis import EvidenceRef, ExtractedClaim

DEFAULT_RESEARCH_RULES = REPO_ROOT / "config" / "research_rules.yaml"


@lru_cache(maxsize=4)
def load_research_rules(path: str | None = None) -> dict[str, Any]:
    rules_path = Path(path) if path else DEFAULT_RESEARCH_RULES
    with rules_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("research rules root must be a mapping")
    return data


def reset_research_rules_cache() -> None:
    load_research_rules.cache_clear()


def _classify_ordered(text: str, items: list[dict[str, Any]]) -> tuple[str, EvidenceRef | None]:
    for item in items:
        item_id = str(item.get("id", "unknown"))
        if item_id == "unknown":
            continue
        for kw in item.get("keywords") or []:
            if kw and kw in text:
                return item_id, _find_excerpt(text, kw)
    return "unknown", None


def classify_behavior_and_subtype(
    *,
    document_id: str,
    title: str | None,
    content: str | None,
) -> list[ExtractedClaim]:
    rules = load_research_rules()
    text = " ".join(x for x in [title or "", content or ""] if x).strip()
    claims: list[ExtractedClaim] = []
    if not text:
        claims.append(
            ExtractedClaim(
                claim_type="behavior_stage",
                claim_value="unknown",
                confidence=0.0,
                is_inference=True,
                evidence=[EvidenceRef(document_id=document_id, excerpt="(empty)")],
            )
        )
        claims.append(
            ExtractedClaim(
                claim_type="demand_subtype",
                claim_value="unknown",
                confidence=0.0,
                is_inference=True,
                evidence=[EvidenceRef(document_id=document_id, excerpt="(empty)")],
            )
        )
        return claims

    stage, stage_ev = _classify_ordered(text, list(rules.get("behavior_stages") or []))
    subtype, sub_ev = _classify_ordered(text, list(rules.get("demand_subtypes") or []))

    def bind(ev: EvidenceRef | None, fallback: str) -> EvidenceRef:
        if ev is None:
            return EvidenceRef(document_id=document_id, excerpt=text[:120] or fallback)
        return EvidenceRef(
            document_id=document_id,
            excerpt=ev.excerpt,
            char_start=ev.char_start,
            char_end=ev.char_end,
        )

    claims.append(
        ExtractedClaim(
            claim_type="behavior_stage",
            claim_value=stage,
            confidence=0.75 if stage != "unknown" else 0.2,
            is_inference=stage == "unknown",
            evidence=[bind(stage_ev, stage)],
        )
    )
    claims.append(
        ExtractedClaim(
            claim_type="demand_subtype",
            claim_value=subtype,
            confidence=0.7 if subtype != "unknown" else 0.2,
            is_inference=subtype == "unknown",
            evidence=[bind(sub_ev, subtype)],
        )
    )
    return claims
