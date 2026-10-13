from __future__ import annotations

from insight_engine.normalize.pipeline import normalize_text, normalize_url, parse_datetime_to_iso


def test_normalize_text_collapse_and_lower():
    assert normalize_text("  Foo\n\tBAR  ") == "foo bar"


def test_normalize_url_strips_tracking_and_www():
    url = "https://www.Example.com/path/?utm_source=x&id=1"
    assert normalize_url(url) == "https://example.com/path?id=1"


def test_parse_datetime_naive_assumes_shanghai():
    iso, err = parse_datetime_to_iso("2025-11-02 14:20:00")
    assert err is None
    assert iso == "2025-11-02T06:20:00Z"


def test_parse_datetime_with_offset():
    iso, err = parse_datetime_to_iso("2025-11-08T18:30:00+08:00")
    assert err is None
    assert iso == "2025-11-08T10:30:00Z"


def test_parse_datetime_invalid():
    iso, err = parse_datetime_to_iso("not-a-date")
    assert iso is None
    assert err is not None
