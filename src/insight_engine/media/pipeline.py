"""On-demand media processing pipeline (metadata → subtitles → ASR? → keyframes → OCR?)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from insight_engine.config import Settings, get_settings
from insight_engine.db.media_repository import MediaRepository
from insight_engine.db.repository import DocumentRepository
from insight_engine.dedup.hasher import content_hash
from insight_engine.media.asr.base import ASRProvider
from insight_engine.media.asr.factory import get_asr_provider
from insight_engine.media.dedup_link import link_overlapping_modalities, segment_content_hash
from insight_engine.media.ffprobe import extract_audio
from insight_engine.media.keyframes import extract_interval_keyframes
from insight_engine.media.ocr.base import OCRProvider
from insight_engine.media.ocr.factory import get_ocr_provider
from insight_engine.media.subtitles import load_subtitle_file
from insight_engine.models.documents import DocumentCreate, PermissionStatus
from insight_engine.models.media import (
    EvidenceStatus,
    MediaSegmentCreate,
    MediaSegmentModality,
    MediaProcessingStatus,
)
from insight_engine.ops.logging_util import get_logger
from insight_engine.ops.task_guard import should_skip_media_reprocess

_log = get_logger("insight_engine.media")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MediaPipeline:
    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings | None = None,
        asr: ASRProvider | None = None,
        ocr: OCRProvider | None = None,
    ) -> None:
        self.conn = conn
        self.settings = settings or get_settings()
        self.repo = MediaRepository(conn)
        self.doc_repo = DocumentRepository(conn)
        self.asr = asr if asr is not None else get_asr_provider()
        self.ocr = ocr if ocr is not None else get_ocr_provider()

    def process_media(
        self,
        media_id: str,
        *,
        run_asr: bool = False,
        run_ocr: bool = False,
        run_keyframes: bool = True,
        subtitle_path: Path | str | None = None,
        force: bool = False,
        allow_reprocess: bool = False,
    ) -> dict[str, Any]:
        asset = self.repo.get_asset(media_id)
        if asset is None:
            raise ValueError(f"media not found: {media_id}")

        skip, skip_reason = should_skip_media_reprocess(
            self.conn, media_id, force=force or allow_reprocess
        )
        if skip:
            _log.info("skip media reprocess media_id=%s reason=%s", media_id, skip_reason)
            return {
                "media_id": media_id,
                "status": "skipped",
                "error": skip_reason,
                "steps": [{"step": "guard", "status": "skipped", "reason": skip_reason}],
            }

        permission = asset["permission_status"]
        if permission in {"unclear", "denied"} and not force:
            self.repo.update_asset_metadata(
                media_id,
                processing_status=MediaProcessingStatus.BLOCKED.value,
                error_message="permission unclear/denied; processing blocked without force",
            )
            self.conn.commit()
            return {
                "media_id": media_id,
                "status": "blocked",
                "error": "permission blocked",
                "steps": [],
            }

        allowed = json.loads(asset.get("allowed_processing") or "[]")
        media_path = Path(asset["local_path"])
        if not media_path.exists():
            self.repo.update_asset_metadata(
                media_id,
                processing_status=MediaProcessingStatus.FAILED.value,
                error_message=f"file missing: {media_path}",
            )
            self.conn.commit()
            return {"media_id": media_id, "status": "failed", "error": "file missing", "steps": []}

        # resolve subtitle from provenance if not provided
        if subtitle_path is None:
            prov = json.loads(asset.get("provenance_metadata") or "{}")
            if prov.get("subtitle_path"):
                subtitle_path = Path(prov["subtitle_path"])

        started = time.perf_counter()
        run_id = self.repo.create_processing_run(
            media_id=media_id,
            params={
                "run_asr": run_asr,
                "run_ocr": run_ocr,
                "run_keyframes": run_keyframes,
                "subtitle_path": str(subtitle_path) if subtitle_path else None,
            },
            model_name=None,
        )
        self.repo.update_asset_metadata(
            media_id, processing_status=MediaProcessingStatus.PROCESSING.value, error_message=""
        )
        self.conn.commit()

        steps: list[dict[str, Any]] = []
        errors: list[str] = []
        model_name = None
        model_version = None
        has_subtitles = False

        # 1) Subtitles preferred
        if subtitle_path and Path(subtitle_path).exists():
            try:
                cues = load_subtitle_file(Path(subtitle_path))
                texts: list[str] = []
                for cue in cues:
                    if asset.get("duration_seconds") is not None:
                        if cue.start_time > float(asset["duration_seconds"]) + 0.5:
                            continue
                    seg = MediaSegmentCreate(
                        segment_id=str(uuid.uuid4()),
                        media_id=media_id,
                        modality=MediaSegmentModality.SUBTITLE,
                        start_time=cue.start_time,
                        end_time=cue.end_time,
                        subtitle_text=cue.text,
                        analysis_model="subtitle_file",
                        confidence=1.0,
                        evidence_status=EvidenceStatus.UNREVIEWED,
                        source_reference=str(subtitle_path),
                        processing_run_id=run_id,
                        content_hash=segment_content_hash(cue.text),
                    )
                    self.repo.insert_segment(seg)
                    texts.append(cue.text)
                has_subtitles = bool(texts)
                doc_id = self._upsert_text_document(
                    asset=asset,
                    title=f"subtitle:{asset.get('original_filename')}",
                    content="\n".join(texts),
                    content_type="subtitle",
                )
                self.repo.update_asset_metadata(media_id, document_id=doc_id)
                steps.append({"step": "subtitles", "status": "ok", "count": len(texts)})
            except Exception as exc:  # noqa: BLE001
                errors.append(f"subtitles: {exc}")
                steps.append({"step": "subtitles", "status": "error", "error": str(exc)})

        # 2) ASR only if requested and no subtitles (prefer subtitles)
        prefer_subs = bool(
            (self.settings.media_config.get("processing") or {}).get(
                "prefer_subtitles_over_asr", True
            )
        )
        should_asr = run_asr and "asr" in allowed and not (prefer_subs and has_subtitles)
        if should_asr:
            if not self.asr.available():
                steps.append({"step": "asr", "status": "skipped", "reason": "asr_unavailable"})
            else:
                try:
                    wav = self.settings.media_dir / media_id / "audio_16k.wav"
                    extract_audio(media_path, wav)
                    asr_segs = self.asr.transcribe(wav, language=self.settings.asr_language)
                    texts = []
                    for item in asr_segs:
                        status = EvidenceStatus.UNREVIEWED
                        if item.confidence is not None and item.confidence < 0.45:
                            status = EvidenceStatus.LOW_CONFIDENCE
                        seg = MediaSegmentCreate(
                            segment_id=str(uuid.uuid4()),
                            media_id=media_id,
                            modality=MediaSegmentModality.ASR,
                            start_time=item.start_time,
                            end_time=item.end_time,
                            transcript_text=item.text,
                            analysis_model=self.asr.name,
                            confidence=item.confidence,
                            evidence_status=status,
                            source_reference=str(wav),
                            processing_run_id=run_id,
                            content_hash=segment_content_hash(item.text),
                        )
                        self.repo.insert_segment(seg)
                        texts.append(item.text)
                    if texts:
                        doc_id = self._upsert_text_document(
                            asset=asset,
                            title=f"transcript:{asset.get('original_filename')}",
                            content="\n".join(texts),
                            content_type="transcript",
                        )
                        self.repo.update_asset_metadata(media_id, document_id=doc_id)
                    model_name = self.asr.name
                    model_version = getattr(self.asr, "model_size", None)
                    steps.append({"step": "asr", "status": "ok", "count": len(texts)})
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"asr: {exc}")
                    steps.append({"step": "asr", "status": "error", "error": str(exc)})
        elif run_asr and prefer_subs and has_subtitles:
            steps.append({"step": "asr", "status": "skipped", "reason": "subtitles_preferred"})

        # 3) Keyframes
        keyframe_refs = []
        if run_keyframes and "keyframes" in allowed:
            duration = float(asset.get("duration_seconds") or 0)
            if duration <= 0:
                steps.append({"step": "keyframes", "status": "skipped", "reason": "no_duration"})
            else:
                try:
                    out_dir = (
                        self.settings.media_dir
                        / media_id
                        / self.settings.keyframes_subdir
                    )
                    keyframe_refs = extract_interval_keyframes(
                        media_path,
                        out_dir,
                        duration_seconds=duration,
                        interval=self.settings.keyframe_interval_seconds,
                        max_frames=self.settings.max_keyframes,
                    )
                    for kf in keyframe_refs:
                        seg = MediaSegmentCreate(
                            segment_id=str(uuid.uuid4()),
                            media_id=media_id,
                            modality=MediaSegmentModality.KEYFRAME,
                            start_time=kf.timestamp_seconds,
                            end_time=kf.timestamp_seconds,
                            keyframe_path=str(kf.path),
                            analysis_model="ffmpeg_interval",
                            confidence=1.0,
                            evidence_status=EvidenceStatus.UNREVIEWED,
                            processing_run_id=run_id,
                        )
                        self.repo.insert_segment(seg)
                    steps.append(
                        {"step": "keyframes", "status": "ok", "count": len(keyframe_refs)}
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"keyframes: {exc}")
                    steps.append({"step": "keyframes", "status": "error", "error": str(exc)})

        # 4) OCR on keyframes
        if run_ocr and "ocr" in allowed:
            if not self.ocr.available():
                steps.append({"step": "ocr", "status": "skipped", "reason": "ocr_unavailable"})
            elif not keyframe_refs:
                steps.append({"step": "ocr", "status": "skipped", "reason": "no_keyframes"})
            else:
                ocr_count = 0
                try:
                    for kf in keyframe_refs:
                        result = self.ocr.recognize(kf.path)
                        if not result.text.strip():
                            continue
                        seg = MediaSegmentCreate(
                            segment_id=str(uuid.uuid4()),
                            media_id=media_id,
                            modality=MediaSegmentModality.OCR,
                            start_time=kf.timestamp_seconds,
                            end_time=kf.timestamp_seconds,
                            ocr_text=result.text,
                            keyframe_path=str(kf.path),
                            analysis_model=self.ocr.name,
                            confidence=result.confidence,
                            evidence_status=EvidenceStatus.UNREVIEWED,
                            processing_run_id=run_id,
                            content_hash=segment_content_hash(result.text),
                        )
                        self.repo.insert_segment(seg)
                        ocr_count += 1
                    steps.append({"step": "ocr", "status": "ok", "count": ocr_count})
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"ocr: {exc}")
                    steps.append({"step": "ocr", "status": "error", "error": str(exc)})

        # 5) Cross-modal soft links
        try:
            link_ids = link_overlapping_modalities(self.conn, media_id)
            steps.append({"step": "cross_modal_links", "status": "ok", "count": len(link_ids)})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"links: {exc}")
            steps.append({"step": "cross_modal_links", "status": "error", "error": str(exc)})

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if errors and not any(s.get("status") == "ok" for s in steps):
            status = "failed"
            asset_status = MediaProcessingStatus.FAILED.value
        elif errors:
            status = "partial"
            asset_status = MediaProcessingStatus.PARTIAL.value
        else:
            status = "succeeded"
            asset_status = MediaProcessingStatus.SUCCEEDED.value

        self.repo.finalize_processing_run(
            run_id,
            status=status,
            steps=steps,
            error_summary="; ".join(errors[:5]) if errors else None,
            duration_ms=elapsed_ms,
            model_name=model_name,
            model_version=str(model_version) if model_version else None,
        )
        self.repo.update_asset_metadata(
            media_id,
            processing_status=asset_status,
            error_message="; ".join(errors[:3]) if errors else "",
        )
        self.conn.commit()
        return {
            "media_id": media_id,
            "processing_run_id": run_id,
            "status": status,
            "steps": steps,
            "errors": errors,
            "duration_ms": elapsed_ms,
        }

    def _upsert_text_document(
        self,
        *,
        asset: dict[str, Any],
        title: str,
        content: str,
        content_type: str,
    ) -> str:
        document_id = str(uuid.uuid4())
        now = _utc_now()
        digest = content_hash(content)
        self.doc_repo.insert_document(
            DocumentCreate(
                document_id=document_id,
                source_id=asset["source_id"],
                source_type="local_media",
                source_name=asset.get("original_filename"),
                title=title,
                published_at=None,
                collected_at=now,
                content_type=content_type,
                raw_content=content,
                normalized_content=content,
                content_hash=digest,
                permission_status=PermissionStatus(asset["permission_status"]),
                processing_status="normalized",
                provenance_metadata={
                    "media_id": asset["media_id"],
                    "from_media": True,
                },
            )
        )
        return document_id
