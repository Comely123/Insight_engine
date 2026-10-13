#!/usr/bin/env python3
"""Generate small local test media samples with ffmpeg (no external downloads)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "samples" / "media"


def run(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with_sub = OUT / "sample_with_subs.mp4"
    no_sub = OUT / "sample_speech_tone.mp4"
    corrupt = OUT / "corrupt.mp4"
    srt = OUT / "sample_with_subs.srt"

    # 3s color + sine tone
    run(
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
            str(with_sub),
        ]
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(no_sub),
        ]
    )

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
    corrupt.write_bytes(b"NOT_A_VALID_MEDIA_FILE")
    print(f"Samples written to {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
