"""Collector adapter interface. No login/CAPTCHA bypass — authorized/compliant sources only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CollectedItem:
    title: str | None
    content: str
    original_url: str | None = None
    published_at: str | None = None
    source_name: str | None = None
    content_type: str = "text"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectResult:
    collector_id: str
    status: str  # succeeded | partial | failed | not_configured
    items: list[CollectedItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: str | None = None


class BaseCollector(ABC):
    collector_id: str = "base"
    display_name: str = "Base"
    # upload | rss | official_api | public_web | stub_platform
    source_kind: str = "stub_platform"
    enabled_by_default: bool = False

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        ...
