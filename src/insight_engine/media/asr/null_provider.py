from __future__ import annotations

from pathlib import Path

from insight_engine.media.asr.base import ASRProvider
from insight_engine.models.media import ASRSegment


class NullASRProvider(ASRProvider):
    name = "null"

    def available(self) -> bool:
        return False

    def transcribe(self, audio_or_media_path: Path, *, language: str | None = None) -> list[ASRSegment]:
        raise RuntimeError("ASR is not configured (NullASRProvider)")
