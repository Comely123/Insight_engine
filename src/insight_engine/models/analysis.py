"""Pydantic models for Phase 2 structured analysis outputs."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class IntentLabel(str, Enum):
    INTEREST = "interest"
    INQUIRY = "inquiry"
    PURCHASE_INTENT = "purchase_intent"
    PAYMENT = "payment"
    FULFILLMENT = "fulfillment"
    UNKNOWN = "unknown"


class StancePolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class EvidenceRef(BaseModel):
    document_id: str
    excerpt: str = Field(min_length=1)
    char_start: int | None = None
    char_end: int | None = None
    segment_id: str | None = None

    @field_validator("excerpt")
    @classmethod
    def excerpt_not_blank(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("excerpt must not be empty")
        return text


class ExtractedClaim(BaseModel):
    claim_type: Literal[
        "topic",  # legacy alias; prefer research_topic
        "intent",  # legacy commerce intent
        "price",
        "stance",
        "behavior_stage",
        "demand_subtype",  # legacy; mapped from research_topic when applicable
        "content_kind",
        "research_topic",
        "relevance",
        "innovation",
        "custom",
    ]
    claim_value: str
    polarity: StancePolarity | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    is_inference: bool = False
    evidence: list[EvidenceRef] = Field(min_length=1)


class DocumentAnalysisResult(BaseModel):
    """Validated structured output for one document. Must cite existing document_id."""

    document_id: str
    topic: str = "other"
    topic_label: str | None = None
    intent: IntentLabel = IntentLabel.UNKNOWN
    stance: StancePolarity = StancePolarity.NEUTRAL
    prices: list[float] = Field(default_factory=list)
    event_title: str | None = None
    event_summary: str | None = None
    claims: list[ExtractedClaim] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    analyzer: str = "rules"
    model_name: str | None = None
    prompt_version: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

    @field_validator("claims")
    @classmethod
    def claims_must_reference_same_document(
        cls, claims: list[ExtractedClaim], info: ValidationInfo
    ) -> list[ExtractedClaim]:
        doc_id = (info.data or {}).get("document_id")
        if not doc_id:
            return claims
        for claim in claims:
            for ev in claim.evidence:
                if ev.document_id != doc_id:
                    raise ValueError(
                        f"evidence.document_id {ev.document_id!r} != document_id {doc_id!r}"
                    )
        return claims


class AnalysisRunSummary(BaseModel):
    run_id: str
    status: str
    analyzer_type: str
    document_count: int = 0
    claims_created: int = 0
    events_created: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: str
    finished_at: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
