"""Registry of collectors for the public product."""

from __future__ import annotations

from insight_engine.collectors.base import BaseCollector
from insight_engine.collectors.news_search_rss import KeywordNewsRSSCollector
from insight_engine.collectors.open_apis import OPEN_API_COLLECTORS
from insight_engine.collectors.platform_stubs import PLATFORM_STUBS
from insight_engine.collectors.rss_collector import RSSCollector


def all_collectors() -> list[BaseCollector]:
    # Stubs stay registered for future official API wiring, but UI must not list them.
    return [
        KeywordNewsRSSCollector(),
        RSSCollector(),
        *OPEN_API_COLLECTORS,
        *PLATFORM_STUBS,
    ]


def get_collector(collector_id: str) -> BaseCollector | None:
    for c in all_collectors():
        if c.collector_id == collector_id:
            return c
    return None


def list_collector_cards(*, available_only: bool = True) -> list[dict]:
    cards = []
    for c in all_collectors():
        if c.source_kind == "stub_platform":
            continue
        ok = c.available()
        if available_only and not ok:
            continue
        cards.append(
            {
                "id": c.collector_id,
                "name": c.display_name,
                "kind": c.source_kind,
                "available": ok,
                "enabled_by_default": c.enabled_by_default,
            }
        )
    return cards
