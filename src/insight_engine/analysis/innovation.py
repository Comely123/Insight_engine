"""Batch C: three-step innovation detection with substance evidence."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from insight_engine.analysis.rules import _find_excerpt
from insight_engine.config import REPO_ROOT
from insight_engine.models.analysis import EvidenceRef, ExtractedClaim

DEFAULT_PATH = REPO_ROOT / "config" / "relevance_innovation.yaml"

# Relevance tiers that may emit innovation claims
INNOVATION_ALLOWED = frozenset({"direct", "edge"})


@lru_cache(maxsize=4)
def load_innovation_config(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_PATH
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("innovation config root must be a mapping")
    return data


def reset_innovation_cache() -> None:
    load_innovation_config.cache_clear()


def noise_terms() -> list[str]:
    cfg = load_innovation_config()
    return list(cfg.get("noise_terms") or [])


def _hit(text: str, keywords: list[str]) -> tuple[str | None, Any]:
    for kw in keywords:
        if not kw:
            continue
        ok = kw.lower() in text.lower() if kw.isascii() else kw in text
        if ok:
            return kw, _find_excerpt(text, kw)
    return None, None


def detect_innovation(
    text: str,
    *,
    relevance_tier: str,
) -> tuple[ExtractedClaim | None, str]:
    """
    Three steps:
      1) relevance gate (direct/edge only)
      2) cue keyword
      3) substance keyword (different excerpt preferred)
    Returns (claim_or_none, reason).
    """
    if relevance_tier not in INNOVATION_ALLOWED:
        return None, f"gated_by_relevance:{relevance_tier}"

    text = (text or "").strip()
    if not text:
        return None, "empty_text"

    cfg = load_innovation_config().get("innovation") or {}
    cues = list(cfg.get("cue_keywords") or [])
    substances = list(cfg.get("substance_keywords") or [])
    min_len = int(cfg.get("min_substance_excerpt_chars") or 12)
    require_distinct = bool(cfg.get("require_distinct_excerpts", True))

    cue_kw, cue_ev = _hit(text, cues)
    if not cue_kw or cue_ev is None:
        return None, "no_cue"

    sub_kw, sub_ev = _hit(text, substances)
    if not sub_kw or sub_ev is None:
        return None, f"cue_without_substance:{cue_kw}"

    if len((sub_ev.excerpt or "").strip()) < min_len:
        return None, "substance_excerpt_too_short"

    if require_distinct:
        # Prefer non-overlapping windows; if same window, still accept if both keywords present
        same = (
            cue_ev.char_start == sub_ev.char_start
            and cue_ev.char_end == sub_ev.char_end
        )
        if same and cue_kw == sub_kw:
            return None, "cue_equals_substance"

    evidence = [
        EvidenceRef(
            document_id="",  # filled by caller
            excerpt=f"[cue] {cue_ev.excerpt}",
            char_start=cue_ev.char_start,
            char_end=cue_ev.char_end,
        ),
        EvidenceRef(
            document_id="",
            excerpt=f"[substance] {sub_ev.excerpt}",
            char_start=sub_ev.char_start,
            char_end=sub_ev.char_end,
        ),
    ]
    claim = ExtractedClaim(
        claim_type="innovation",
        claim_value=f"{cue_kw}|{sub_kw}",
        confidence=0.65,
        is_inference=False,
        evidence=evidence,
    )
    return claim, f"ok:{cue_kw}+{sub_kw}"


def build_innovation_claim(
    *,
    document_id: str,
    title: str | None,
    content: str | None,
    relevance_tier: str,
) -> tuple[ExtractedClaim | None, str]:
    text = " ".join(x for x in [title or "", content or ""] if x).strip()
    claim, reason = detect_innovation(text, relevance_tier=relevance_tier)
    if claim is None:
        return None, reason
    for ev in claim.evidence:
        ev.document_id = document_id
    return claim, reason
