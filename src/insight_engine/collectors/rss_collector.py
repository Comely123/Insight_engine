"""RSS collector for allowlisted public feeds (compliant)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from insight_engine.collectors.base import BaseCollector, CollectedItem, CollectResult

# Curated China-relevant public RSS examples (replaceable via config later)
DEFAULT_FEEDS = [
    ("人民网科技RSS", "http://www.people.com.cn/rss/finance.xml"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


class RSSCollector(BaseCollector):
    collector_id = "rss_public"
    display_name = "公开 RSS 资讯"
    source_kind = "rss"
    enabled_by_default = True

    def __init__(self, feeds: list[tuple[str, str]] | None = None) -> None:
        self.feeds = feeds or DEFAULT_FEEDS

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        items: list[CollectedItem] = []
        errors: list[str] = []
        kws = [k.strip() for k in keywords if k.strip()]
        for feed_name, url in self.feeds:
            try:
                req = Request(url, headers={"User-Agent": "InsightEngine/1.0 (+research; compliant-rss)"})
                with urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                root = ET.fromstring(raw)
                entries = []
                for node in root.iter():
                    if _local(node.tag) in {"item", "entry"}:
                        entries.append(node)
                for entry in entries:
                    title = ""
                    link = None
                    summary = ""
                    published = None
                    for child in list(entry):
                        name = _local(child.tag)
                        if name == "title" and child.text:
                            title = child.text.strip()
                        elif name in {"link", "id"}:
                            link = (child.get("href") or child.text or link or "").strip() or link
                        elif name in {"description", "summary", "content"}:
                            summary = _strip_html(child.text or "")
                        elif name in {"pubDate", "published", "updated"} and child.text:
                            published = child.text.strip()
                            try:
                                published = parsedate_to_datetime(published).isoformat()
                            except (TypeError, ValueError, IndexError):
                                pass
                    body = f"{title}\n{summary}".strip()
                    if kws and not any(k in body for k in kws):
                        continue
                    if not body:
                        continue
                    items.append(
                        CollectedItem(
                            title=title or None,
                            content=body,
                            original_url=link,
                            published_at=published,
                            source_name=feed_name,
                            content_type="rss",
                        )
                    )
                    if len(items) >= limit:
                        break
            except (HTTPError, URLError, ET.ParseError, TimeoutError, OSError) as exc:
                errors.append(f"{feed_name}: {exc}")
            if len(items) >= limit:
                break

        status = "succeeded"
        if errors and items:
            status = "partial"
        elif errors and not items:
            status = "failed"
        elif not items:
            status = "partial"
            errors.append("RSS 未匹配到关键词相关条目（源可用但无命中）")
        return CollectResult(
            collector_id=self.collector_id,
            status=status,
            items=items[:limit],
            errors=errors,
            notes="仅拉取公开 RSS；不做登录绕过。",
        )
