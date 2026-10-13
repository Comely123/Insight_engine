from __future__ import annotations

from pathlib import Path

from insight_engine.media.ocr.base import OCRProvider
from insight_engine.models.media import OCRResult


class NullOCRProvider(OCRProvider):
    name = "null"

    def available(self) -> bool:
        return False

    def recognize(self, image_path: Path) -> OCRResult:
        raise RuntimeError("OCR is not configured (NullOCRProvider)")
