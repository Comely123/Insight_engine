"""FFmpeg / ffprobe helpers for authorized local media."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class FFmpegNotFoundError(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegNotFoundError("ffmpeg not found on PATH")
    return path


def require_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FFmpegNotFoundError("ffprobe not found on PATH")
    return path


def probe_media(path: Path) -> dict[str, Any]:
    ffprobe = require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"ffprobe failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe error: {proc.stderr.strip() or proc.returncode}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid JSON") from exc

    duration = None
    width = height = None
    fmt = data.get("format") or {}
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            if duration is None and stream.get("duration"):
                try:
                    duration = float(stream["duration"])
                except (TypeError, ValueError):
                    pass
            break
    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "raw": data,
    }


def extract_audio(path: Path, out_wav: Path, *, timeout: int = 300) -> Path:
    ffmpeg = require_ffmpeg()
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(out_wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"audio extract failed: {proc.stderr.strip()[:500]}")
    return out_wav


def extract_keyframe_at(
    path: Path,
    out_image: Path,
    *,
    timestamp_seconds: float,
    timeout: int = 120,
) -> Path:
    ffmpeg = require_ffmpeg()
    out_image.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{max(0.0, timestamp_seconds):.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_image),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not out_image.exists():
        raise RuntimeError(f"keyframe extract failed at {timestamp_seconds}: {proc.stderr.strip()[:400]}")
    return out_image
