"""Configuration loading for Insight Engine."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Engine/ (repo root): .../src/insight_engine/config.py -> parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


class Settings:
    """Runtime settings resolved from YAML + environment variables."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        raw = _load_yaml(self.config_path)

        self.app_name: str = str(raw.get("app_name", "Insight Engine"))
        data_dir_name = os.environ.get("INSIGHT_DATA_DIR") or raw.get("data_dir", "data")
        self.data_dir: Path = (REPO_ROOT / data_dir_name).resolve()

        db_env = os.environ.get("INSIGHT_DB_PATH")
        if db_env:
            self.db_path: Path = Path(db_env).expanduser().resolve()
        else:
            db_filename = str(raw.get("db_filename", "insight.db"))
            self.db_path = self.data_dir / db_filename

        self.imports_dir: Path = self.data_dir / str(raw.get("imports_dirname", "imports"))
        self.samples_dir: Path = self.data_dir / str(raw.get("samples_dirname", "samples"))
        self.default_timezone: str = str(raw.get("default_timezone", "Asia/Shanghai"))

        dedup = raw.get("dedup") or {}
        self.dedup_lowercase: bool = bool(dedup.get("lowercase", True))
        self.dedup_collapse_whitespace: bool = bool(dedup.get("collapse_whitespace", True))

        search = raw.get("search") or {}
        self.search_default_limit: int = int(search.get("default_limit", 50))
        self.search_max_limit: int = int(search.get("max_limit", 500))

        media = raw.get("media") or {}
        self.media_dir: Path = self.data_dir / str(media.get("media_dirname", "media"))
        self.models_dir: Path = self.data_dir / str(media.get("models_dirname", "models"))
        self.keyframes_subdir: str = str(media.get("keyframes_subdir", "keyframes"))
        self.media_max_duration_seconds: float = float(media.get("max_duration_seconds", 1800))
        self.media_max_file_mb: float = float(media.get("max_file_mb", 500))
        self.keyframe_interval_seconds: float = float(media.get("keyframe_interval_seconds", 2.0))
        self.max_keyframes: int = int(media.get("max_keyframes", 30))
        self.asr_model_size: str = str(
            os.environ.get("INSIGHT_ASR_MODEL") or media.get("asr_model_size", "tiny")
        )
        self.asr_device: str = str(media.get("asr_device", "cpu"))
        self.asr_compute_type: str = str(media.get("asr_compute_type", "int8"))
        self.asr_language: str | None = media.get("asr_language", "zh")
        self.asr_download_root: Path = self.models_dir / "faster-whisper"

        media_cfg_path = REPO_ROOT / "config" / "media.yaml"
        self.media_config: dict[str, Any] = _load_yaml(media_cfg_path)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.asr_download_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
