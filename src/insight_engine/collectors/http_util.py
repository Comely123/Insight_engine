"""Minimal HTTP helpers for compliant public APIs (stdlib only)."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_UA = "InsightEngine/1.0 (+research; compliant-api; https://github.com/Comely123/Insight_engine)"


def http_get_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> bytes:
    hdrs = {"User-Agent": DEFAULT_UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> Any:
    raw = http_get_bytes(url, headers=headers, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


def build_url(base: str, params: dict[str, Any]) -> str:
    cleaned = {k: v for k, v in params.items() if v is not None and v != ""}
    if not cleaned:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode(cleaned, doseq=True)}"


def polite_pause(seconds: float = 0.35) -> None:
    if seconds > 0:
        time.sleep(seconds)


def http_error_message(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        return f"HTTP {exc.code}: {body or exc.reason}"
    if isinstance(exc, URLError):
        return str(exc.reason or exc)
    return str(exc)
