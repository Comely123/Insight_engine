"""Batch B: three independent classification dimensions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from insight_engine.analysis.rules import _find_excerpt
from insight_engine.config import REPO_ROOT
from insight_engine.models.analysis import EvidenceRef, ExtractedClaim

DEFAULT_TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy_v2.yaml"


@lru_cache(maxsize=4)
def load_taxonomy(path: str | None = None) -> dict[str, Any]:
    rules_path = Path(path) if path else DEFAULT_TAXONOMY_PATH
    with rules_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("taxonomy root must be a mapping")
    return data


def reset_taxonomy_cache() -> None:
    load_taxonomy.cache_clear()


def _ordered_match(
    text: str, items: list[dict[str, Any]], *, default: str = "unknown"
) -> tuple[str, EvidenceRef | None]:
    for item in items:
        item_id = str(item.get("id", default))
        if item_id in {default, "unrelated"}:
            continue
        require_any = item.get("require_any") or []
        if require_any and not any(k and k in text for k in require_any):
            continue
        for kw in item.get("keywords") or []:
            if kw and kw in text:
                return item_id, _find_excerpt(text, kw)
    return default, None


def _has_domain_anchor(text: str, anchors: list[str]) -> bool:
    lower = text.lower()
    for a in anchors:
        if not a:
            continue
        if a.isascii():
            if a.lower() in lower:
                return True
        elif a in text:
            return True
    return False


def classify_content_kind(
    text: str,
    *,
    ingest_content_type: str | None,
    taxonomy: dict[str, Any] | None = None,
) -> tuple[str, EvidenceRef | None, str]:
    from insight_engine.product.doc_genre import (
        classify_document_genre,
        genre_to_content_kind,
    )

    tax = taxonomy or load_taxonomy()
    hint_map = tax.get("content_type_hints") or {}
    ingest = (ingest_content_type or "").lower()
    hint = hint_map.get(ingest)

    kind, ev = _ordered_match(text, list(tax.get("content_kinds") or []))
    note = ""
    if kind != "unknown":
        return kind, ev, note

    # Content-first genre (PDF/DOCX ≠ literature). Prefer over bare format hints.
    genre = classify_document_genre(text)
    genre_kind = genre_to_content_kind(genre)
    if genre_kind != "unknown":
        return genre_kind, None, f"content_kind_from_genre={genre}"

    if hint:
        # Weak prior from ingest type only when text has no stronger genre cue.
        # Never treat raw pdf/document as academic via missing hint.
        return str(hint), None, f"content_kind_from_ingest={hint}"
    return "unknown", None, ""


def classify_research_topic(
    text: str,
    *,
    taxonomy: dict[str, Any] | None = None,
) -> tuple[str, EvidenceRef | None, list[str]]:
    tax = taxonomy or load_taxonomy()
    topics = list(tax.get("research_topics") or [])
    anchors = list(tax.get("domain_anchor_keywords") or [])
    notes: list[str] = []

    topic, ev = _ordered_match(text, topics, default="unknown")
    # Souvenir keywords can also appear with memorial — memorial wins via order
    # if require_any satisfied; otherwise souvenir is fine.

    if topic == "unknown":
        if not _has_domain_anchor(text, anchors):
            # Academic/news without pet/blessing anchors → unrelated (explicit),
            # not forced living_blessing.
            if len(text.strip()) >= 80:
                return "unrelated", None, ["no_domain_anchor→unrelated"]
        return "unknown", None, notes

    if topic == "souvenir" and any(k in text for k in ["离世", "去世", "骨灰", "殡葬"]):
        notes.append("souvenir_with_loss_cues_kept_separate_from_memorial_unless_required")
    return topic, ev, notes


def classify_behavior_stage_v2(
    text: str,
    *,
    taxonomy: dict[str, Any] | None = None,
) -> tuple[str, EvidenceRef | None]:
    tax = taxonomy or load_taxonomy()
    return _ordered_match(text, list(tax.get("behavior_stages") or []))


def detect_taxonomy_conflicts(
    *,
    content_kind: str,
    research_topic: str,
    behavior_stage: str,
) -> list[str]:
    """Soft conflict notes — do not auto-correct labels."""
    notes: list[str] = []
    if research_topic == "memorial" and behavior_stage in {
        "payment",
        "signup",
        "purchase_intent",
        "price_inquiry",
    }:
        # Valid possible path; no conflict.
        pass
    if content_kind == "academic" and behavior_stage in {
        "payment",
        "signup",
        "fulfillment",
        "participation",
    }:
        notes.append("academic_text_with_transaction_stage—verify_not_false_positive")
    if research_topic == "unrelated" and behavior_stage not in {"unknown", "discussion"}:
        notes.append("unrelated_topic_with_behavior_label—likely_noise")
    if research_topic == "souvenir" and behavior_stage == "unknown":
        # Common for product blurbs; not a conflict.
        pass
    if content_kind == "news" and research_topic == "living_blessing":
        notes.append("news_genre_vs_living_blessing_topic—ok_if_reporting_activity")
    return notes


def build_taxonomy_claims(
    *,
    document_id: str,
    title: str | None,
    content: str | None,
    ingest_content_type: str | None = None,
) -> tuple[list[ExtractedClaim], dict[str, Any]]:
    tax = load_taxonomy()
    text = " ".join(x for x in [title or "", content or ""] if x).strip()
    meta: dict[str, Any] = {
        "content_kind": "unknown",
        "research_topic": "unknown",
        "behavior_stage": "unknown",
        "conflicts": [],
        "notes": [],
    }
    claims: list[ExtractedClaim] = []

    def bind(ev: EvidenceRef | None, fallback: str) -> EvidenceRef:
        if ev is None:
            return EvidenceRef(document_id=document_id, excerpt=(text[:120] or fallback))
        return EvidenceRef(
            document_id=document_id,
            excerpt=ev.excerpt,
            char_start=ev.char_start,
            char_end=ev.char_end,
        )

    if not text:
        empty_ev = [EvidenceRef(document_id=document_id, excerpt="(empty)")]
        claims.extend(
            [
                ExtractedClaim(
                    claim_type="content_kind",
                    claim_value="unknown",
                    confidence=0.0,
                    is_inference=True,
                    evidence=empty_ev,
                ),
                ExtractedClaim(
                    claim_type="research_topic",
                    claim_value="unknown",
                    confidence=0.0,
                    is_inference=True,
                    evidence=empty_ev,
                ),
                ExtractedClaim(
                    claim_type="behavior_stage",
                    claim_value="unknown",
                    confidence=0.0,
                    is_inference=True,
                    evidence=empty_ev,
                ),
            ]
        )
        return claims, meta

    kind, kind_ev, kind_note = classify_content_kind(
        text, ingest_content_type=ingest_content_type, taxonomy=tax
    )
    topic, topic_ev, topic_notes = classify_research_topic(text, taxonomy=tax)
    stage, stage_ev = classify_behavior_stage_v2(text, taxonomy=tax)
    conflicts = detect_taxonomy_conflicts(
        content_kind=kind, research_topic=topic, behavior_stage=stage
    )
    meta.update(
        {
            "content_kind": kind,
            "research_topic": topic,
            "behavior_stage": stage,
            "conflicts": conflicts,
            "notes": ([kind_note] if kind_note else []) + topic_notes,
        }
    )

    claims.append(
        ExtractedClaim(
            claim_type="content_kind",
            claim_value=kind,
            confidence=0.75 if kind != "unknown" else 0.25,
            is_inference=kind == "unknown",
            evidence=[bind(kind_ev, kind)],
        )
    )
    claims.append(
        ExtractedClaim(
            claim_type="research_topic",
            claim_value=topic,
            confidence=0.7 if topic not in {"unknown", "unrelated"} else 0.35,
            is_inference=topic == "unknown",
            evidence=[bind(topic_ev, topic)],
        )
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
    return claims, meta
