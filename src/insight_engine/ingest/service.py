"""Unified import service for CSV / JSON / TXT."""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from insight_engine.config import Settings, get_settings
from insight_engine.db.repository import DocumentRepository
from insight_engine.dedup.hasher import content_hash, find_duplicate_id
from insight_engine.ingest.field_map import build_column_map, row_get
from insight_engine.ingest.readers import read_csv_rows, read_json_rows, read_txt_as_rows
from insight_engine.models.documents import (
    DocumentCreate,
    ImportBatchResult,
    ImportErrorRecord,
    PermissionStatus,
    SourceCreate,
)
from insight_engine.normalize.pipeline import normalize_text, normalize_url, parse_datetime_to_iso


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if suffix in {".txt", ".md", ".markdown", ".log", ".text"}:
        return "txt"
    raise ValueError(
        f"Unsupported file type: {suffix or '(none)'}. "
        "Use .csv, .json, .txt, .md, or audiovisual formats via the public upload pipeline."
    )


class ImportService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings | None = None,
    ) -> None:
        self.conn = conn
        self.settings = settings or get_settings()
        self.repo = DocumentRepository(conn)

    def import_file(
        self,
        path: Path | str,
        *,
        source_name: str | None = None,
        permission_status: PermissionStatus = PermissionStatus.USER_OWNED,
        license_note: str | None = "User-provided research sample",
        save_copy: bool = True,
        field_overrides: dict[str, str] | None = None,
    ) -> ImportBatchResult:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")

        content_type = detect_format(path)
        started_at = _utc_now()
        batch_id = str(uuid.uuid4())
        source_id = str(uuid.uuid4())
        resolved_source_name = source_name or path.stem

        if save_copy:
            self.settings.ensure_directories()
            dest = self.settings.imports_dir / f"{batch_id}_{path.name}"
            shutil.copy2(path, dest)
            stored_path = str(dest)
        else:
            stored_path = str(path.resolve())

        source = SourceCreate(
            source_id=source_id,
            source_name=resolved_source_name,
            source_type="file_upload",
            acquisition_method="user_upload",
            permission_status=permission_status,
            license_note=license_note,
            allow_local_store=True,
            allow_model_process=False,
            allow_report_export=True,
        )
        self.repo.upsert_source(source)
        self.repo.create_batch(
            batch_id=batch_id,
            source_id=source_id,
            filename=path.name,
            content_type=content_type,
            started_at=started_at,
        )
        self.conn.commit()

        result = ImportBatchResult(
            batch_id=batch_id,
            source_id=source_id,
            filename=path.name,
            content_type=content_type,
            status="running",
            started_at=started_at,
        )

        try:
            columns, rows = self._read_rows(path, content_type)
            result.row_count_input = len(rows)
            column_map = build_column_map(columns)
            if field_overrides:
                column_map.update(field_overrides)

            if "content" not in column_map and content_type != "txt":
                # Allow title-only failure per row; still require some content field ideally
                pass

            for index, row in enumerate(rows, start=1):
                self._ingest_row(
                    result=result,
                    row=row,
                    row_number=index,
                    column_map=column_map,
                    source=source,
                    batch_id=batch_id,
                    stored_path=stored_path,
                    default_content_type=content_type,
                )

            if result.errors and result.row_count_imported == 0:
                result.status = "failed"
            elif result.errors:
                result.status = "partial"
            else:
                result.status = "succeeded"
        except Exception as exc:  # noqa: BLE001 - surface as batch failure
            result.status = "failed"
            err = ImportErrorRecord(
                error_id=str(uuid.uuid4()),
                batch_id=batch_id,
                row_number=None,
                field_name=None,
                message=f"Import aborted: {exc}",
                raw_snippet=None,
                created_at=_utc_now(),
            )
            result.errors.append(err)
            self.repo.insert_error(err)

        result.finished_at = _utc_now()
        self.repo.finalize_batch(result)
        self.conn.commit()
        return result

    def _read_rows(self, path: Path, content_type: str) -> tuple[list[str], list[dict[str, Any]]]:
        if content_type == "csv":
            return read_csv_rows(path)
        if content_type == "json":
            return read_json_rows(path)
        if content_type == "txt":
            return read_txt_as_rows(path)
        raise ValueError(f"Unsupported content_type: {content_type}")

    def _ingest_row(
        self,
        *,
        result: ImportBatchResult,
        row: dict[str, Any],
        row_number: int,
        column_map: dict[str, str],
        source: SourceCreate,
        batch_id: str,
        stored_path: str,
        default_content_type: str,
    ) -> None:
        raw_content = row_get(row, column_map, "content")
        title = row_get(row, column_map, "title")
        if raw_content is None or str(raw_content).strip() == "":
            # Fallback: use whole row JSON-ish text if no content column
            if title and str(title).strip():
                raw_content = str(title)
            else:
                err = ImportErrorRecord(
                    error_id=str(uuid.uuid4()),
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="content",
                    message="Missing content/text field; row skipped",
                    raw_snippet=str(row)[:500],
                    created_at=_utc_now(),
                )
                result.errors.append(err)
                self.repo.insert_error(err)
                return

        published_raw = row_get(row, column_map, "published_at")
        published_at, date_err = parse_datetime_to_iso(
            published_raw,
            default_tz_name=self.settings.default_timezone,
        )
        if date_err:
            err = ImportErrorRecord(
                error_id=str(uuid.uuid4()),
                batch_id=batch_id,
                row_number=row_number,
                field_name="published_at",
                message=date_err,
                raw_snippet=str(published_raw)[:200] if published_raw is not None else None,
                created_at=_utc_now(),
            )
            result.errors.append(err)
            self.repo.insert_error(err)
            # Continue with null published_at

        original_url = row_get(row, column_map, "original_url")
        url_norm = normalize_url(str(original_url) if original_url else None)
        row_source_name = row_get(row, column_map, "source_name")
        content_type_val = row_get(row, column_map, "content_type") or default_content_type

        display_norm = normalize_text(
            str(raw_content),
            lowercase=False,
            collapse=self.settings.dedup_collapse_whitespace,
        )
        hash_value = content_hash(
            str(raw_content),
            lowercase=self.settings.dedup_lowercase,
            collapse_whitespace=self.settings.dedup_collapse_whitespace,
        )
        duplicate_of = find_duplicate_id(self.conn, hash_value)
        is_duplicate = duplicate_of is not None

        doc = DocumentCreate(
            document_id=str(uuid.uuid4()),
            source_id=source.source_id,
            batch_id=batch_id,
            source_type=source.source_type,
            source_name=str(row_source_name) if row_source_name else source.source_name,
            original_url=str(original_url).strip() if original_url else None,
            title=str(title).strip() if title else None,
            published_at=published_at,
            collected_at=_utc_now(),
            content_type=str(content_type_val),
            raw_content=str(raw_content),
            normalized_content=display_norm,
            content_hash=hash_value,
            url_normalized=url_norm,
            permission_status=source.permission_status,
            processing_status="normalized",
            provenance_metadata={
                "import_row_number": row_number,
                "stored_path": stored_path,
                "column_map": column_map,
            },
            is_duplicate=is_duplicate,
            duplicate_of=duplicate_of,
        )
        self.repo.insert_document(doc)
        result.row_count_imported += 1
        if is_duplicate:
            result.row_count_dupes += 1
