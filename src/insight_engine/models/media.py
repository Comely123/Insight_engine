"""Pydantic models for Phase 3 media evidence."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MediaProcessingStatus(str, Enum):
    IMPORTED = "imported"
    METADATA_READY = "metadata_ready"
    PROCESSING = "processing"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class MediaSegmentModality(str, Enum):
    SUBTITLE = "subtitle"
    ASR = "asr"
    OCR = "ocr"
    KEYFRAME = "keyframe"
    DESCRIPTION = "description"


class EvidenceStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    LOW_CONFIDENCE = "low_confidence"


class MediaAssetCreate(BaseModel):
    media_id: str
    source_id: str
    document_id: str | None = None
    file_type: str
    original_filename: str | None = None
    local_path: str
    file_hash: str
    file_size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    permission_status: str
    allowed_processing: list[str] = Field(default_factory=list)
    retention_policy: str | None = "path_reference_only"
    processing_status: MediaProcessingStatus = MediaProcessingStatus.IMPORTED
    is_duplicate: bool = False
    duplicate_of: str | None = None
    error_message: str | None = None
    provenance_metadata: dict[str, Any] = Field(default_factory=dict)


class MediaSegmentCreate(BaseModel):
    segment_id: str
    media_id: str
    modality: MediaSegmentModality
    start_time: float | None = None
    end_time: float | None = None
    transcript_text: str | None = None
    subtitle_text: str | None = None
    ocr_text: str | None = None
    keyframe_path: str | None = None
    analysis_model: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_status: EvidenceStatus = EvidenceStatus.UNREVIEWED
    source_reference: str | None = None
    processing_run_id: str | None = None
    content_hash: str | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def non_negative_time(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("timestamps must be >= 0 and must come from media timeline")
        return v


class ASRSegment(BaseModel):
    start_time: float
    end_time: float
    text: str
    confidence: float | None = None


class OCRResult(BaseModel):
    text: str
    confidence: float | None = None
    start_time: float | None = None
    keyframe_path: str | None = None
