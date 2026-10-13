#!/usr/bin/env python3
"""Print a short checklist of media-related dependencies."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> int:
    print("Media dependency check")
    print("-" * 40)

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    print(f"ffmpeg : {'OK  ' + ffmpeg if ffmpeg else 'MISSING (install FFmpeg)'}")
    print(f"ffprobe: {'OK  ' + ffprobe if ffprobe else 'MISSING (install FFmpeg)'}")

    tess = shutil.which("tesseract")
    print(f"tesseract: {'OK  ' + tess if tess else 'optional MISSING (OCR only)'}")

    try:
        import faster_whisper

        print(f"faster-whisper: OK  {faster_whisper.__version__}")
    except ImportError:
        print("faster-whisper: MISSING  -> .\\scripts\\setup_media.ps1")

    try:
        import pytesseract  # noqa: F401

        print("pytesseract: OK")
    except ImportError:
        print("pytesseract: optional MISSING")

    try:
        from pypdf import PdfReader  # noqa: F401

        print("pypdf: OK (PDF literature upload)")
    except ImportError:
        print("pypdf: MISSING  -> pip install -r requirements.txt")

    from insight_engine.media.asr.factory import get_asr_provider

    asr = get_asr_provider()
    print(f"ASR provider: {asr.name} available={asr.available()}")
    print("-" * 40)
    print("Setup: .\\scripts\\setup_media.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
