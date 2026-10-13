"""ASR provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from insight_engine.models.media import ASRSegment


class ASRProvider(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def transcribe(self, audio_or_media_path: Path, *, language: str | None = None) -> list[ASRSegment]:
        ...
