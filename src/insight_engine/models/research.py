"""Pydantic models for Phase 4 research projects and alerts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchProjectCreate(BaseModel):
    project_id: str
    name: str
    research_question: str | None = None
    target_market: str | None = None
    geo_scope: str | None = None
    time_start: str | None = None
    time_end: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    source_filters: dict[str, Any] = Field(default_factory=dict)
    quality_requirements: str | None = None
    notes: str | None = None


class KeywordVersionCreate(BaseModel):
    version_id: str
    project_id: str
    version_number: int
    keywords: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    change_note: str | None = None


class TrendAlertRecord(BaseModel):
    alert_id: str
    project_id: str | None
    run_id: str | None
    alert_type: str
    severity: str
    title: str
    trigger_reason: str
    metric_values: dict[str, Any] = Field(default_factory=dict)
    compare_window_days: int | None = None
    sample_size: int | None = None
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    opposing_evidence: list[dict[str, Any]] = Field(default_factory=list)
    quality_notes: str | None = None
    review_suggestion: str | None = None
    review_status: str = "unreviewed"
