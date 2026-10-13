"""Import authorized local media files into media_assets."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import uuid
from pathlib import Path

from insight_engine.config import Settings, get_settings
from insight_engine.db.media_repository import MediaRepository
from insight_engine.db.repository import DocumentRepository
from insight_engine.media.ffprobe import FFmpegNotFoundError, probe_media
from insight_engine.models.documents import PermissionStatus, SourceCreate
from insight_engine.models.media import MediaAssetCreate, MediaProcessingStatus


def file_sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class MediaIngestService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings | None = None) -> None:
        self.conn = conn
        self.settings = settings or get_settings()
        self.repo = MediaRepository(conn)
        self.doc_repo = DocumentRepository(conn)

    def import_media(
        self,
        path: Path | str,
        *,
        permission_status: PermissionStatus = PermissionStatus.USER_OWNED,
        source_name: str | None = None,
        license_note: str | None = "User-authorized local media",
        copy_into_media_dir: bool = False,
        subtitle_path: Path | str | None = None,
        allow_asr: bool = True,
        allow_ocr: bool = True,
        allow_keyframes: bool = True,
    ) -> dict:
        path = Path(path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")

        allowed_ext = set(
            (self.settings.media_config.get("allowed_extensions") or [])
            or [".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".aac"]
        )
        if path.suffix.lower() not in {e.lower() for e in allowed_ext}:
            raise ValueError(f"Unsupported media extension: {path.suffix}")

        size = path.stat().st_size
        max_bytes = int(self.settings.media_max_file_mb * 1024 * 1024)
        if size > max_bytes:
            raise ValueError(f"File exceeds max size {self.settings.media_max_file_mb} MB")

        self.settings.ensure_directories()
        digest = file_sha256(path)
        existing = self.repo.find_by_hash(digest)

        source_id = str(uuid.uuid4())
        media_id = str(uuid.uuid4())
        self.doc_repo.upsert_source(
            SourceCreate(
                source_id=source_id,
                source_name=source_name or path.stem,
                source_type="local_media",
                acquisition_method="user_upload",
                permission_status=permission_status,
                license_note=license_note,
                allow_local_store=True,
                allow_model_process=permission_status
                in {PermissionStatus.USER_OWNED, PermissionStatus.ALLOWED},
                allow_report_export=True,
            )
        )

        if copy_into_media_dir:
            dest = self.settings.media_dir / f"{media_id}_{path.name}"
            shutil.copy2(path, dest)
            local_path = dest
        else:
            local_path = path.resolve()

        allowed = []
        if allow_keyframes:
            allowed.append("keyframes")
        if allow_asr:
            allowed.append("asr")
        if allow_ocr:
            allowed.append("ocr")
        if subtitle_path:
            allowed.append("subtitles")

        is_dup = existing is not None
        asset = MediaAssetCreate(
            media_id=media_id,
            source_id=source_id,
            file_type=path.suffix.lower().lstrip(".") or "unknown",
            original_filename=path.name,
            local_path=str(local_path),
            file_hash=digest,
            file_size_bytes=size,
            permission_status=permission_status.value,
            allowed_processing=allowed,
            processing_status=MediaProcessingStatus.IMPORTED,
            is_duplicate=is_dup,
            duplicate_of=existing["media_id"] if existing else None,
            provenance_metadata={
                "subtitle_path": str(subtitle_path) if subtitle_path else None,
                "copy_into_media_dir": copy_into_media_dir,
            },
        )
        self.repo.insert_asset(asset)

        meta_error = None
        try:
            meta = probe_media(local_path)
            duration = meta.get("duration_seconds")
            if duration and duration > self.settings.media_max_duration_seconds:
                self.repo.update_asset_metadata(
                    media_id,
                    duration_seconds=duration,
                    width=meta.get("width"),
                    height=meta.get("height"),
                    processing_status=MediaProcessingStatus.BLOCKED.value,
                    error_message=(
                        f"duration {duration:.1f}s exceeds max "
                        f"{self.settings.media_max_duration_seconds}s"
                    ),
                )
            else:
                self.repo.update_asset_metadata(
                    media_id,
                    duration_seconds=duration,
                    width=meta.get("width"),
                    height=meta.get("height"),
                    processing_status=MediaProcessingStatus.METADATA_READY.value,
                )
        except (FFmpegNotFoundError, RuntimeError) as exc:
            meta_error = str(exc)
            self.repo.update_asset_metadata(
                media_id,
                processing_status=MediaProcessingStatus.FAILED.value,
                error_message=meta_error,
            )

        self.conn.commit()
        out = self.repo.get_asset(media_id)
        assert out is not None
        out["import_note"] = (
            "duplicate_file_hash" if is_dup else ("metadata_error" if meta_error else "ok")
        )
        return out
