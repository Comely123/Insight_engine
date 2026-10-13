"""Local logging with secret redaction and simple size-based rotation."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from insight_engine.config import get_settings

_KEY_VALUE_SECRET = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token)\s*[:=]\s*\S+"
)
_SK_TOKEN = re.compile(r"(?i)sk-[A-Za-z0-9]{10,}")


def redact_secrets(text: str) -> str:
    out = _KEY_VALUE_SECRET.sub(r"\1=[REDACTED]", text)
    out = _SK_TOKEN.sub("[REDACTED]", out)
    return out


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_secrets(original)


def get_logger(name: str = "insight_engine") -> logging.Logger:
    settings = get_settings()
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_dir / "insight_engine.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    return logger
