"""Keyword-driven public news RSS (Google News) — compliant, no login bypass."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from insight_engine.collectors.base import BaseCollector, CollectedItem, CollectResult


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _parse_feed(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    out: list[dict] = []
    for node in root.iter():
        if _local(node.tag) not in {"item", "entry"}:
            continue
        title = ""
        link = None
        summary = ""
        published = None
        for child in list(node):
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
        if body:
            out.append(
                {
                    "title": title or None,
                    "content": body,
                    "original_url": link,
                    "published_at": published,
                }
            )
    return out


class KeywordNewsRSSCollector(BaseCollector):
    """Search public news RSS by keywords (text). Not a social video scraper."""

    collector_id = "news_search_rss"
    display_name = "公开资讯检索（新闻 RSS）"
    source_kind = "rss"
    enabled_by_default = True

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        kws = [k.strip() for k in keywords if k.strip()]
        if not kws:
            return CollectResult(
                collector_id=self.collector_id,
                status="failed",
                errors=["请提供至少一个关键词"],
            )

        items: list[CollectedItem] = []
        errors: list[str] = []
        # Query variants: combined + each keyword (improve hit rate for niche topics)
        queries = [" ".join(kws)] + kws[:5]
        seen_urls: set[str] = set()

        for q in queries:
            if len(items) >= limit:
                break
            url = (
                "https://news.google.com/rss/search?"
                f"q={quote_plus(q)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            )
            try:
                req = Request(
                    url,
                    headers={"User-Agent": "InsightEngine/1.0 (+research; public-rss)"},
                )
                with urlopen(req, timeout=25) as resp:
                    raw = resp.read()
                for row in _parse_feed(raw):
                    key = row.get("original_url") or row.get("content") or ""
                    if key in seen_urls:
                        continue
                    seen_urls.add(key)
                    items.append(
                        CollectedItem(
                            title=row.get("title"),
                            content=row["content"],
                            original_url=row.get("original_url"),
                            published_at=row.get("published_at"),
                            source_name=f"公开资讯:{q}",
                            content_type="rss",
                        )
                    )
                    if len(items) >= limit:
                        break
            except (HTTPError, URLError, ET.ParseError, TimeoutError, OSError) as exc:
                errors.append(f"query={q}: {exc}")

        status = "succeeded"
        if errors and items:
            status = "partial"
        elif errors and not items:
            status = "failed"
        elif not items:
            status = "partial"
            errors.append("公开资讯 RSS 未返回条目（网络受限或关键词过窄）")

        return CollectResult(
            collector_id=self.collector_id,
            status=status,
            items=items[:limit],
            errors=errors,
            notes="仅拉取公开新闻 RSS 文本摘要；不含登录墙社交/短视频平台内容。",
        )
