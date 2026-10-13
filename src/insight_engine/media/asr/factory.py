"""Resolve ASR provider. Prefer project-local faster-whisper when installed."""

from __future__ import annotations

import os

from insight_engine.config import get_settings
from insight_engine.media.asr.base import ASRProvider
from insight_engine.media.asr.faster_whisper_provider import FasterWhisperASRProvider
from insight_engine.media.asr.null_provider import NullASRProvider


def get_asr_provider(*, force_enable: bool | None = None) -> ASRProvider:
    """
    Use faster-whisper from the project .venv when installed.
    Model weights download into data/models/faster-whisper.

    Disable explicitly with INSIGHT_ASR_ENABLED=0.
    """
    settings = get_settings()
    env_flag = os.environ.get("INSIGHT_ASR_ENABLED", "").strip().lower()
    if force_enable is False or env_flag in {"0", "false", "no", "off"}:
        return NullASRProvider()

    provider = FasterWhisperASRProvider(settings)
    if not provider.available():
        return NullASRProvider()

    # Installed → enabled (unless forced off above). force_enable=True also ok.
    if force_enable is True or env_flag in {"", "1", "true", "yes", "on"}:
        return provider
    return NullASRProvider()
