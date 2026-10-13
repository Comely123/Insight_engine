from __future__ import annotations

from insight_engine.analysis.price_extract import extract_structured_prices, parse_price_claim_value
from insight_engine.analysis.rules import analyze_document_rules, reset_rules_cache


def test_confirmed_cny_price_enters_prices_list():
    reset_rules_cache()
    result = analyze_document_rules(
        document_id="p1",
        title="报价",
        content="活动报名费收费 69 元，现场另付。",
    )
    assert 69.0 in result.prices
    price_claims = [c for c in result.claims if c.claim_type == "price"]
    assert price_claims
    parsed = parse_price_claim_value(price_claims[0].claim_value)
    assert parsed is not None
    assert parsed["is_confirmed_price"] is True
    assert parsed["currency"] == "CNY"
    assert "69" in parsed["raw_expression"]


def test_year_and_orders_not_confirmed():
    hits = extract_structured_prices(
        "Li Wenyu (1840-1911) wrote many works. Conductivity is 2-3 orders higher.",
        source_id="d1",
        patterns=[
            r"(?P<amount>\d+(?:\.\d+)?)\s*元",
            r"[¥￥]\s*(?P<amount>\d+(?:\.\d+)?)",
            r"(?P<low>\d+(?:\.\d+)?)\s*[-~到至]\s*(?P<high>\d+(?:\.\d+)?)\s*元",
        ],
    )
    # No 元 / ¥ in text → no confirmed hits from tightened patterns
    assert all(not h.is_confirmed_price for h in hits)


def test_ambiguous_range_without_yuan_ignored_by_pattern():
    hits = extract_structured_prices(
        "pages 37-1 June 2024 50 (50)",
        source_id="d2",
    )
    assert hits == [] or all(not h.is_confirmed_price for h in hits)
