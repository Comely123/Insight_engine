"""Text, URL, and datetime normalization helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dateutil import parser as date_parser

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "spm",
    "from",
}


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(
    text: str | None,
    *,
    lowercase: bool = True,
    collapse: bool = True,
) -> str:
    if text is None:
        return ""
    value = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if collapse:
        value = collapse_whitespace(value)
    else:
        value = value.strip()
    if lowercase:
        value = value.lower()
    return value


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def parse_datetime_to_iso(
    value: Any,
    *,
    default_tz_name: str = "Asia/Shanghai",
) -> tuple[str | None, str | None]:
    """
    Parse a date/datetime into ISO-8601 UTC string.

    Returns (iso_utc, error_message). On success error_message is None.
    Empty values return (None, None).
    """
    if value is None:
        return None, None
    if isinstance(value, float) and value != value:  # NaN
        return None, None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "nat"}:
        return None, None

    try:
        if isinstance(value, datetime):
            dt = value
        else:
            dt = date_parser.parse(text)
    except (ValueError, OverflowError, TypeError) as exc:
        return None, f"unparseable datetime: {text!r} ({exc})"

    if dt.tzinfo is None:
        # Attach fixed offset for China Standard Time without requiring zoneinfo data files.
        # Asia/Shanghai is UTC+8 with no DST in modern practice.
        if default_tz_name in {"Asia/Shanghai", "Asia/Beijing", "CST"}:
            from datetime import timedelta

            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        else:
            dt = dt.replace(tzinfo=timezone.utc)

    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.isoformat().replace("+00:00", "Z"), None
