"""faster-whisper ASR with project-local model cache under data/models/faster-whisper."""

from __future__ import annotations

from pathlib import Path

from insight_engine.config import Settings, get_settings
from insight_engine.media.asr.base import ASRProvider
from insight_engine.models.media import ASRSegment


class FasterWhisperASRProvider(ASRProvider):
    name = "faster_whisper"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = None
        self.model_size = self.settings.asr_model_size
        self.download_root = self.settings.asr_download_root
        self.device = self.settings.asr_device
        self.compute_type = self.settings.asr_compute_type
        self.default_language = self.settings.asr_language

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def _load_model(self):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel

        self.download_root.mkdir(parents=True, exist_ok=True)
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=str(self.download_root),
        )
        return self._model

    def transcribe(self, audio_or_media_path: Path, *, language: str | None = None) -> list[ASRSegment]:
        if not self.available():
            raise RuntimeError("faster-whisper is not installed in the project venv")
        model = self._load_model()
        lang = language if language is not None else self.default_language
        segments_iter, _info = model.transcribe(
            str(audio_or_media_path),
            language=lang,
            vad_filter=True,
        )
        results: list[ASRSegment] = []
        for seg in segments_iter:
            text = (seg.text or "").strip()
            if not text:
                continue
            conf = None
            if getattr(seg, "avg_logprob", None) is not None:
                # map logprob-ish to 0..1 softly; mark low confidence separately upstream
                conf = max(0.0, min(1.0, 1.0 + float(seg.avg_logprob) / 5.0))
            results.append(
                ASRSegment(
                    start_time=float(seg.start),
                    end_time=float(seg.end),
                    text=text,
                    confidence=conf,
                )
            )
        return results
