"""Structured price extraction with confirmation gate (Batch A)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PriceRecord:
    amount: float
    currency: str
    raw_expression: str
    context: str
    price_type: str
    is_confirmed_price: bool
    source_id: str
    evidence_location: str
    char_start: int
    char_end: int

    def to_claim_value(self) -> str:
        payload = {
            "amount": self.amount,
            "currency": self.currency,
            "raw_expression": self.raw_expression,
            "context": self.context,
            "price_type": self.price_type,
            "is_confirmed_price": self.is_confirmed_price,
            "source_id": self.source_id,
            "evidence_location": self.evidence_location,
        }
        return json.dumps(payload, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_price_claim_value(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "amount" in data:
                return data
        except json.JSONDecodeError:
            return None
    try:
        amount = float(text)
    except ValueError:
        return None
    # Legacy bare number claims: treat as unconfirmed (do not enter distribution).
    return {
        "amount": amount,
        "currency": "UNKNOWN",
        "raw_expression": text,
        "context": "",
        "price_type": "legacy_untyped",
        "is_confirmed_price": False,
        "source_id": "",
        "evidence_location": "",
    }


_YEARISH = re.compile(r"\b(19|20)\d{2}\b")
_ORDERS = re.compile(r"\b\d+(?:\.\d+)?\s*[-~–—]\s*\d+(?:\.\d+)?\s+orders?\b", re.I)
_DATEISH = re.compile(
    r"(19|20)\d{2}\s*[-/.年]\s*\d{1,2}|\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*(19|20)\d{2}"
)


def _classify_and_confirm(
    *,
    amount: float,
    raw: str,
    context: str,
    pattern_kind: str,
) -> tuple[str, bool]:
    ctx = f"{context} {raw}"
    # Explicit currency / 元 → candidate confirmed
    has_cny_mark = bool(re.search(r"[元¥￥]", raw)) or bool(re.search(r"[元¥￥]", context[max(0, context.find(raw) - 2) :]))

    if _ORDERS.search(ctx):
        return "mentioned_number", False
    if _DATEISH.search(ctx) and not has_cny_mark:
        return "date_or_timestamp", False
    if 1900 <= amount <= 2100 and not has_cny_mark:
        return "year_or_era", False
    if amount in {1, 2, 3, 4, 5} and not has_cny_mark:
        return "mentioned_number", False
    if amount > 500_000:
        return "outlier_amount", False

    if pattern_kind == "cny_suffix" or pattern_kind == "currency_symbol":
        return "listed_or_quoted_price", True
    if pattern_kind == "range":
        # Range without 元 was historically too loose; require 元 in raw.
        if re.search(r"元", raw):
            return "price_range", True
        return "ambiguous_range", False
    return "unknown", False


def extract_structured_prices(
    text: str,
    *,
    source_id: str,
    patterns: list[str] | None = None,
) -> list[PriceRecord]:
    """
    Extract price candidates. Only is_confirmed_price=True should enter formal buckets.
    """
    patterns = patterns or [
        r"(?P<amount>\d+(?:\.\d+)?)\s*元",
        r"[¥￥]\s*(?P<amount>\d+(?:\.\d+)?)",
        r"(?P<low>\d+(?:\.\d+)?)\s*[-~到至]\s*(?P<high>\d+(?:\.\d+)?)\s*元",
    ]
    found: list[PriceRecord] = []
    seen: set[tuple[float, int, int]] = set()

    kind_by_idx = []
    for i, pattern in enumerate(patterns):
        if "元" in pattern and "low" not in pattern:
            kind_by_idx.append("cny_suffix")
        elif "[¥￥]" in pattern or "¥" in pattern:
            kind_by_idx.append("currency_symbol")
        elif "low" in pattern:
            kind_by_idx.append("range")
        else:
            kind_by_idx.append("unknown")

    for i, pattern in enumerate(patterns):
        try:
            regex = re.compile(pattern)
        except re.error:
            continue
        kind = kind_by_idx[i] if i < len(kind_by_idx) else "unknown"
        for match in regex.finditer(text):
            amounts: list[float] = []
            if match.groupdict().get("amount"):
                amounts.append(float(match.group("amount")))
            if match.groupdict().get("low") and match.groupdict().get("high"):
                amounts.extend(
                    [float(match.group("low")), float(match.group("high"))]
                )
            start, end = match.span()
            raw = match.group(0)
            ctx_start = max(0, start - 40)
            ctx_end = min(len(text), end + 40)
            context = text[ctx_start:ctx_end].strip()
            for amount in amounts:
                key = (amount, start, end)
                if key in seen:
                    continue
                seen.add(key)
                price_type, confirmed = _classify_and_confirm(
                    amount=amount, raw=raw, context=context, pattern_kind=kind
                )
                found.append(
                    PriceRecord(
                        amount=amount,
                        currency="CNY" if confirmed or re.search(r"[元¥￥]", raw) else "UNKNOWN",
                        raw_expression=raw,
                        context=context,
                        price_type=price_type,
                        is_confirmed_price=confirmed,
                        source_id=source_id,
                        evidence_location=f"chars:{start}-{end}",
                        char_start=start,
                        char_end=end,
                    )
                )
    return found
