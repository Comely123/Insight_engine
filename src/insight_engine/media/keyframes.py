"""Keyframe extraction with configurable caps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insight_engine.media.ffprobe import extract_keyframe_at


@dataclass
class KeyframeRef:
    timestamp_seconds: float
    path: Path


def plan_interval_timestamps(
    duration_seconds: float,
    *,
    interval: float,
    max_frames: int,
) -> list[float]:
    if duration_seconds <= 0 or interval <= 0 or max_frames <= 0:
        return []
    times: list[float] = []
    t = 0.0
    # avoid exact end which can fail seeking
    end = max(0.0, duration_seconds - 0.05)
    while t <= end and len(times) < max_frames:
        times.append(round(t, 3))
        t += interval
    if not times:
        times = [0.0]
    return times


def extract_interval_keyframes(
    media_path: Path,
    out_dir: Path,
    *,
    duration_seconds: float,
    interval: float,
    max_frames: int,
) -> list[KeyframeRef]:
    out_dir.mkdir(parents=True, exist_ok=True)
    refs: list[KeyframeRef] = []
    for idx, ts in enumerate(
        plan_interval_timestamps(
            duration_seconds, interval=interval, max_frames=max_frames
        )
    ):
        # Keep a real image extension; do not replace dots in the whole filename.
        out = out_dir / f"kf_{idx:03d}_{int(ts * 1000):08d}ms.jpg"
        try:
            extract_keyframe_at(media_path, out, timestamp_seconds=ts)
            refs.append(KeyframeRef(timestamp_seconds=ts, path=out))
        except RuntimeError:
            continue
    return refs
