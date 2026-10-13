from __future__ import annotations

import os

from insight_engine.media.ocr.base import OCRProvider
from insight_engine.media.ocr.null_provider import NullOCRProvider
from insight_engine.media.ocr.tesseract_provider import TesseractOCRProvider


def get_ocr_provider(*, force_enable: bool | None = None, lang: str = "chi_sim+eng") -> OCRProvider:
    env_flag = os.environ.get("INSIGHT_OCR_ENABLED", "").strip().lower()
    # Default: try tesseract if installed; env can force off with 0/false
    if env_flag in {"0", "false", "no", "off"}:
        return NullOCRProvider()
    enabled = True if force_enable is None else force_enable
    provider = TesseractOCRProvider(lang=lang)
    if enabled and provider.available():
        return provider
    return NullOCRProvider()
