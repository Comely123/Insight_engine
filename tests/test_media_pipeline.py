from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from insight_engine.db.media_repository import MediaRepository
from insight_engine.media.asr.null_provider import NullASRProvider
from insight_engine.media.ingest import MediaIngestService
from insight_engine.media.ocr.null_provider import NullOCRProvider
from insight_engine.media.pipeline import MediaPipeline
from insight_engine.media.dedup_link import text_similarity
from insight_engine.models.documents import PermissionStatus

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "samples" / "media"


def _ensure_samples() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    target = SAMPLE_DIR / "sample_with_subs.mp4"
    srt = SAMPLE_DIR / "sample_with_subs.srt"
    if not target.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x240:d=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:duration=3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
    if not srt.exists():
        srt.write_text(
            """1
00:00:00,000 --> 00:00:01,500
宠物毛发祈福手绳 价格 128 元

2
00:00:01,500 --> 00:00:03,000
欢迎咨询定制
""",
            encoding="utf-8",
        )
    corrupt = SAMPLE_DIR / "corrupt.mp4"
    if not corrupt.exists():
        corrupt.write_bytes(b"NOT_A_VALID_MEDIA_FILE")


@pytest.fixture(scope="module", autouse=True)
def samples():
    _ensure_samples()


def test_import_metadata_and_subtitle_keyframes_without_asr_ocr(db_conn, tmp_settings):
    svc = MediaIngestService(db_conn, tmp_settings)
    asset = svc.import_media(
        SAMPLE_DIR / "sample_with_subs.mp4",
        permission_status=PermissionStatus.USER_OWNED,
        subtitle_path=SAMPLE_DIR / "sample_with_subs.srt",
        copy_into_media_dir=False,
    )
    assert asset["duration_seconds"] is not None
    assert asset["processing_status"] in {"metadata_ready", "imported", "succeeded"}

    pipeline = MediaPipeline(
        db_conn,
        tmp_settings,
        asr=NullASRProvider(),
        ocr=NullOCRProvider(),
    )
    result = pipeline.process_media(
        asset["media_id"],
        run_asr=True,  # should skip gracefully
        run_ocr=True,  # should skip gracefully
        run_keyframes=True,
    )
    assert result["status"] in {"succeeded", "partial"}
    steps = {s["step"]: s for s in result["steps"]}
    assert steps["subtitles"]["status"] == "ok"
    assert steps["asr"]["status"] == "skipped"
    assert steps["ocr"]["status"] == "skipped"
    assert steps["keyframes"]["status"] == "ok"

    repo = MediaRepository(db_conn)
    segs = repo.list_segments(asset["media_id"])
    mods = {s["modality"] for s in segs}
    assert "subtitle" in mods
    assert "keyframe" in mods
    for s in segs:
        if s["start_time"] is not None:
            assert s["start_time"] >= 0
            assert s["start_time"] <= float(asset["duration_seconds"]) + 0.6


def test_duplicate_file_hash(db_conn, tmp_settings):
    svc = MediaIngestService(db_conn, tmp_settings)
    a1 = svc.import_media(SAMPLE_DIR / "sample_with_subs.mp4")
    a2 = svc.import_media(SAMPLE_DIR / "sample_with_subs.mp4")
    assert a2["is_duplicate"] == 1
    assert a2["duplicate_of"] == a1["media_id"]


def test_corrupt_media_has_readable_error(db_conn, tmp_settings):
    svc = MediaIngestService(db_conn, tmp_settings)
    asset = svc.import_media(SAMPLE_DIR / "corrupt.mp4")
    assert asset["processing_status"] == "failed"
    assert asset.get("error_message")


def test_unclear_permission_blocks_processing(db_conn, tmp_settings):
    svc = MediaIngestService(db_conn, tmp_settings)
    asset = svc.import_media(
        SAMPLE_DIR / "sample_with_subs.mp4",
        permission_status=PermissionStatus.UNCLEAR,
        subtitle_path=SAMPLE_DIR / "sample_with_subs.srt",
    )
    result = MediaPipeline(
        db_conn, tmp_settings, asr=NullASRProvider(), ocr=NullOCRProvider()
    ).process_media(asset["media_id"], run_keyframes=True)
    assert result["status"] == "blocked"


def test_text_similarity_for_cross_modal():
    assert text_similarity("价格128元", "价格 128 元") > 0.7
