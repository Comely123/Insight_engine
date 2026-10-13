"""Video / media evidence research page."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.config import get_settings
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.db.media_repository import MediaRepository
from insight_engine.media.asr.factory import get_asr_provider
from insight_engine.media.ingest import MediaIngestService
from insight_engine.media.ocr.factory import get_ocr_provider
from insight_engine.media.pipeline import MediaPipeline
from insight_engine.models.documents import PermissionStatus

st.set_page_config(page_title="视频证据 · Insight Engine", layout="wide")
initialize_database()
settings = get_settings()

st.title("视频证据")
st.caption(
    "仅处理用户授权的本地媒体。未核验的转写/OCR 不得当作人工确认原文。"
    "同一视频的字幕、口播、OCR 不视为多条独立需求证据。"
)

asr = get_asr_provider()
ocr = get_ocr_provider()
st.write(
    {
        "asr_provider": asr.name,
        "asr_available": asr.available(),
        "asr_model_dir": str(settings.asr_download_root),
        "ocr_provider": ocr.name,
        "ocr_available": ocr.available(),
        "ffmpeg_hint": "系统 PATH 需有 ffmpeg/ffprobe",
    }
)

st.subheader("导入本地媒体")
perm = st.selectbox(
    "授权状态",
    [
        PermissionStatus.USER_OWNED.value,
        PermissionStatus.ALLOWED.value,
        PermissionStatus.UNCLEAR.value,
        PermissionStatus.DENIED.value,
    ],
)
uploaded = st.file_uploader("视频/音频文件", type=["mp4", "mov", "mkv", "webm", "mp3", "wav", "m4a"])
sub_uploaded = st.file_uploader("可选字幕 SRT/VTT", type=["srt", "vtt"])
copy_flag = st.checkbox("复制到 data/media（默认仅记录本地路径）", value=False)
if st.button("导入媒体", type="primary"):
    settings.ensure_directories()
    target: Path | None = None
    sub_path: Path | None = None
    try:
        if uploaded is not None:
            target = settings.media_dir / f"_upload_{uploaded.name}"
            target.write_bytes(uploaded.getvalue())
        else:
            st.error("请上传视频/音频文件")
            st.stop()
        if sub_uploaded is not None:
            sub_path = settings.media_dir / f"_sub_{sub_uploaded.name}"
            sub_path.write_bytes(sub_uploaded.getvalue())

        with get_connection() as conn:
            asset = MediaIngestService(conn, settings).import_media(
                target,
                permission_status=PermissionStatus(perm),
                copy_into_media_dir=copy_flag,
                subtitle_path=sub_path,
            )
        st.success(f"已导入 media_id={asset['media_id']} status={asset['processing_status']}")
        st.json({k: asset[k] for k in asset if k != "provenance_metadata"})
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))

st.subheader("媒体列表")
with get_connection() as conn:
    assets = MediaRepository(conn).list_assets(100)
    stats = MediaRepository(conn).overview_stats()
st.write(stats)
st.dataframe(assets, width="stretch")

if assets:
    media_id = st.selectbox("选择媒体查看/处理", [a["media_id"] for a in assets])
    asset = next(a for a in assets if a["media_id"] == media_id)

    st.markdown(f"**状态**: `{asset['processing_status']}` | **错误**: {asset.get('error_message') or '—'}")
    if asset.get("is_duplicate"):
        st.warning(f"文件哈希重复，canonical media_id={asset.get('duplicate_of')}")

    c1, c2, c3 = st.columns(3)
    run_asr = c1.checkbox("运行 ASR（需 faster-whisper）", value=False)
    run_ocr = c2.checkbox("运行 OCR（需 Tesseract）", value=False)
    run_kf = c3.checkbox("抽取关键帧", value=True)
    force = st.checkbox("强制处理（unclear/denied 时仍处理，请谨慎）", value=False)

    if st.button("处理所选媒体", type="primary"):
        with get_connection() as conn:
            result = MediaPipeline(conn, settings).process_media(
                media_id,
                run_asr=run_asr,
                run_ocr=run_ocr,
                run_keyframes=run_kf,
                force=force,
            )
        st.json(result)

    with get_connection() as conn:
        repo = MediaRepository(conn)
        segments = repo.list_segments(media_id)
        links = repo.list_links(media_id)
        runs = repo.list_runs(media_id)

    st.subheader("处理运行")
    st.dataframe(runs, width="stretch")

    st.subheader("片段（字幕 / ASR / OCR / 关键帧）")
    for seg in segments:
        label = (
            f"{seg['modality']} | t={seg.get('start_time')}–{seg.get('end_time')} | "
            f"{seg['evidence_status']}"
        )
        with st.expander(label):
            text = seg.get("subtitle_text") or seg.get("transcript_text") or seg.get("ocr_text")
            if text:
                st.write(text)
            if seg.get("keyframe_path") and Path(seg["keyframe_path"]).exists():
                st.image(seg["keyframe_path"])
            st.caption(
                f"segment_id={seg['segment_id']} model={seg.get('analysis_model')} "
                f"conf={seg.get('confidence')}"
            )
            action = st.selectbox(
                "核验",
                ["confirm", "reject", "correct"],
                key=f"seg_act_{seg['segment_id']}",
            )
            new_text = st.text_area(
                "纠正文本",
                value=text or "",
                key=f"seg_txt_{seg['segment_id']}",
            )
            if st.button("提交片段核验", key=f"seg_btn_{seg['segment_id']}"):
                status = {
                    "confirm": "confirmed",
                    "reject": "rejected",
                    "correct": "corrected",
                }[action]
                with get_connection() as conn:
                    MediaRepository(conn).update_segment_status(
                        seg["segment_id"],
                        evidence_status=status,
                        corrected_text=new_text if action == "correct" else None,
                        modality=seg["modality"],
                    )
                    conn.commit()
                st.success("已更新")
                st.rerun()

    st.subheader("跨模态关联（可撤销）")
    for link in links:
        st.write(
            {
                "link_id": link["link_id"],
                "type": link["link_type"],
                "score": link["score"],
                "reason": link["reason"],
                "review_status": link["review_status"],
            }
        )
        b1, b2 = st.columns(2)
        if b1.button("确认关联", key=f"ok_{link['link_id']}"):
            with get_connection() as conn:
                MediaRepository(conn).confirm_link(link["link_id"])
                conn.commit()
            st.rerun()
        if b2.button("撤销关联", key=f"rv_{link['link_id']}"):
            with get_connection() as conn:
                MediaRepository(conn).revoke_link(link["link_id"])
                conn.commit()
            st.rerun()
