"""Encrypted local secret storage (API keys) + plaintext prefs in SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from insight_engine.config import Settings, get_settings
from insight_engine.db.connection import get_connection, initialize_database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fernet_key_path(settings: Settings) -> Path:
    return settings.data_dir / ".fernet_key"


def _get_fernet(settings: Settings | None = None):
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("缺少 cryptography，请执行 pip install cryptography") from exc

    settings = settings or get_settings()
    settings.ensure_directories()
    key_path = _fernet_key_path(settings)
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
    return Fernet(key_path.read_bytes())


class SecretsStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        initialize_database(self.settings)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.settings.db_path)

    def get_pref(self, key: str, default: str | None = None) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT pref_value FROM app_prefs WHERE pref_key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        return str(row["pref_value"])

    def set_pref(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO app_prefs (pref_key, pref_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(pref_key) DO UPDATE SET
                  pref_value = excluded.pref_value,
                  updated_at = excluded.updated_at
                """,
                (key, value, _utc_now()),
            )
            conn.commit()

    def get_secret(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT ciphertext FROM app_secrets WHERE secret_key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        f = _get_fernet(self.settings)
        try:
            return f.decrypt(bytes(row["ciphertext"])).decode("utf-8")
        except Exception:  # noqa: BLE001
            return None

    def set_secret(self, key: str, value: str) -> None:
        if not value:
            return
        token = _get_fernet(self.settings).encrypt(value.encode("utf-8"))
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO app_secrets (secret_key, ciphertext, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(secret_key) DO UPDATE SET
                  ciphertext = excluded.ciphertext,
                  updated_at = excluded.updated_at
                """,
                (key, token, _utc_now()),
            )
            conn.commit()

    def delete_secret(self, key: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM app_secrets WHERE secret_key = ?", (key,))
            conn.commit()

    def has_secret(self, key: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM app_secrets WHERE secret_key = ?", (key,)
            ).fetchone()
        return row is not None

    # --- LLM helpers ---
    def llm_secret_key(self, provider: str) -> str:
        return f"llm.api_key.{provider}"

    def save_llm_settings(
        self,
        *,
        provider: str,
        api_key: str | None,
        model: str | None,
        base_url: str | None,
        replace_key: bool = True,
    ) -> None:
        self.set_pref("llm.provider", provider)
        if model:
            self.set_pref(f"llm.model.{provider}", model)
        if base_url:
            self.set_pref(f"llm.base_url.{provider}", base_url)
        if replace_key and api_key and api_key.strip() and api_key.strip() != "********":
            self.set_secret(self.llm_secret_key(provider), api_key.strip())

    def load_llm_settings(self, provider: str) -> dict:
        return {
            "last_provider": self.get_pref("llm.provider", "rules"),
            "model": self.get_pref(f"llm.model.{provider}"),
            "base_url": self.get_pref(f"llm.base_url.{provider}"),
            "api_key": self.get_secret(self.llm_secret_key(provider)),
            "has_api_key": self.has_secret(self.llm_secret_key(provider)),
        }

    # --- Open data source helpers (literature / YouTube etc.) ---
    def source_secret_key(self, source_id: str) -> str:
        return f"source.api_key.{source_id}"

    def save_source_api_key(self, source_id: str, api_key: str | None) -> None:
        if api_key and api_key.strip() and api_key.strip() != "********":
            self.set_secret(self.source_secret_key(source_id), api_key.strip())

    def load_source_key_status(self, source_id: str) -> dict:
        return {
            "has_api_key": self.has_secret(self.source_secret_key(source_id)),
            "api_key": self.get_secret(self.source_secret_key(source_id)),
        }
