"""Registry of collectors for the public product."""

from __future__ import annotations

from insight_engine.collectors.base import BaseCollector
from insight_engine.collectors.platform_stubs import PLATFORM_STUBS
from insight_engine.collectors.rss_collector import RSSCollector


def all_collectors() -> list[BaseCollector]:
    return [RSSCollector(), *PLATFORM_STUBS]


def get_collector(collector_id: str) -> BaseCollector | None:
    for c in all_collectors():
        if c.collector_id == collector_id:
            return c
    return None


def list_collector_cards() -> list[dict]:
    cards = []
    for c in all_collectors():
        cards.append(
            {
                "id": c.collector_id,
                "name": c.display_name,
                "kind": c.source_kind,
                "available": c.available(),
                "enabled_by_default": c.enabled_by_default,
            }
        )
    return cards
