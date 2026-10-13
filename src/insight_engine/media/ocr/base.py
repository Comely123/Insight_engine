from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from insight_engine.models.media import OCRResult


class OCRProvider(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def recognize(self, image_path: Path) -> OCRResult:
        ...
