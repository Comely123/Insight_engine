"""Optional Tesseract OCR via pytesseract."""

from __future__ import annotations

import shutil
from pathlib import Path

from insight_engine.media.ocr.base import OCRProvider
from insight_engine.models.media import OCRResult


class TesseractOCRProvider(OCRProvider):
    name = "tesseract"

    def __init__(self, *, lang: str = "chi_sim+eng") -> None:
        self.lang = lang

    def available(self) -> bool:
        if shutil.which("tesseract") is None:
            return False
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            return False
        return True

    def recognize(self, image_path: Path) -> OCRResult:
        if not self.available():
            raise RuntimeError("Tesseract/pytesseract/Pillow not available")
        import pytesseract
        from PIL import Image

        with Image.open(image_path) as img:
            text = pytesseract.image_to_string(img, lang=self.lang)
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return OCRResult(text=cleaned, confidence=None, keyframe_path=str(image_path))
