"""Pydantic models for Phase 1 ingest and documents."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PermissionStatus(str, Enum):
    ALLOWED = "allowed"
    UNCLEAR = "unclear"
    DENIED = "denied"
    USER_OWNED = "user_owned"


class SourceCreate(BaseModel):
    source_id: str
    source_name: str
    source_type: str = "file_upload"
    original_url: str | None = None
    acquisition_method: str = "user_upload"
    permission_status: PermissionStatus = PermissionStatus.USER_OWNED
    license_note: str | None = None
    allow_local_store: bool = True
    allow_model_process: bool = False
    allow_report_export: bool = True
    retention_policy: str | None = "user_controlled"


class DocumentCreate(BaseModel):
    document_id: str
    source_id: str
    batch_id: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    original_url: str | None = None
    title: str | None = None
    published_at: str | None = None
    collected_at: str
    content_type: str = "text"
    raw_content: str | None = None
    normalized_content: str | None = None
    content_hash: str
    url_normalized: str | None = None
    permission_status: PermissionStatus = PermissionStatus.USER_OWNED
    processing_status: str = "imported"
    provenance_metadata: dict[str, Any] = Field(default_factory=dict)
    is_duplicate: bool = False
    duplicate_of: str | None = None


class ImportErrorRecord(BaseModel):
    error_id: str
    batch_id: str
    row_number: int | None = None
    field_name: str | None = None
    message: str
    raw_snippet: str | None = None
    created_at: str


class ImportBatchResult(BaseModel):
    batch_id: str
    source_id: str
    filename: str | None = None
    content_type: str | None = None
    status: str
    row_count_input: int = 0
    row_count_imported: int = 0
    row_count_dupes: int = 0
    errors: list[ImportErrorRecord] = Field(default_factory=list)
    started_at: str
    finished_at: str | None = None

    @property
    def error_summary(self) -> str | None:
        if not self.errors:
            return None
        return f"{len(self.errors)} error(s); first: {self.errors[0].message}"
