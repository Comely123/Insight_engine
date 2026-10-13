from insight_engine.collectors.registry import list_collector_cards


def test_ui_hides_unavailable_platform_stubs() -> None:
    cards = list_collector_cards(available_only=True)
    ids = {c["id"] for c in cards}
    assert "news_search_rss" in ids
    assert "weibo" not in ids
    assert "douyin" not in ids
    assert all(c["available"] for c in cards)
