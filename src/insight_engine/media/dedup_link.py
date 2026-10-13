"""Cross-modal linking and soft dedup for media segments (non-destructive)."""

from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from insight_engine.db.media_repository import MediaRepository
from insight_engine.dedup.hasher import content_hash


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", "", text).lower()


def text_similarity(a: str | None, b: str | None) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def link_overlapping_modalities(
    conn: sqlite3.Connection,
    media_id: str,
    *,
    threshold: float = 0.72,
) -> list[str]:
    """
    Create soft links between similar subtitle/ASR/OCR segments.
    Does not delete anything; does not treat modalities as independent demand evidence.
    """
    repo = MediaRepository(conn)
    segments = repo.list_segments(media_id)
    by_mod: dict[str, list[dict]] = {}
    for seg in segments:
        by_mod.setdefault(seg["modality"], []).append(seg)

    created: list[str] = []
    pairs = [
        ("subtitle", "asr", "subtitle_asr_near_duplicate"),
        ("subtitle", "ocr", "subtitle_ocr_near_duplicate"),
        ("asr", "ocr", "asr_ocr_near_duplicate"),
    ]
    for left_mod, right_mod, link_type in pairs:
        for left in by_mod.get(left_mod, []):
            left_text = left.get("subtitle_text") or left.get("transcript_text") or left.get("ocr_text")
            for right in by_mod.get(right_mod, []):
                right_text = (
                    right.get("subtitle_text") or right.get("transcript_text") or right.get("ocr_text")
                )
                score = text_similarity(left_text, right_text)
                if score < threshold:
                    continue
                # optional temporal overlap when both timed
                if left.get("start_time") is not None and right.get("start_time") is not None:
                    ls, le = float(left["start_time"]), float(left["end_time"] or left["start_time"])
                    rs, re_ = float(right["start_time"]), float(right["end_time"] or right["start_time"])
                    overlap = max(0.0, min(le, re_) - max(ls, rs))
                    if overlap <= 0 and abs(ls - rs) > 2.0:
                        continue
                link_id = repo.insert_link(
                    media_id=media_id,
                    from_segment_id=left["segment_id"],
                    to_segment_id=right["segment_id"],
                    link_type=link_type,
                    reason=f"similarity={score:.2f}; same media multimodal manifestations",
                    score=score,
                    created_by="rules",
                    review_status="auto",
                )
                created.append(link_id)
    return created


def segment_content_hash(text: str | None) -> str:
    return content_hash(text or "")
