"""
Free / self-serve official APIs for literature & public media search.

No login bypass. Keys (when needed) come from SecretsStore or env vars.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.error import HTTPError, URLError
from insight_engine.collectors.base import BaseCollector, CollectedItem, CollectResult
from insight_engine.collectors.http_util import (
    DEFAULT_UA,
    build_url,
    http_error_message,
    http_get_bytes,
    http_get_json,
    polite_pause,
)
from insight_engine.collectors.source_credentials import (
    CONTACT_EMAIL_ENV,
    CONTACT_EMAIL_PREF,
    secret_key_for,
)
from insight_engine.ops.secrets_store import SecretsStore


def _contact_email() -> str | None:
    store = SecretsStore()
    email = (store.get_pref(CONTACT_EMAIL_PREF) or "").strip()
    if email:
        return email
    return (os.environ.get(CONTACT_EMAIL_ENV) or "").strip() or None


def _api_key(source_id: str, env_var: str) -> str | None:
    store = SecretsStore()
    key = (store.get_secret(secret_key_for(source_id)) or "").strip()
    if key:
        return key
    return (os.environ.get(env_var) or "").strip() or None


def _join_keywords(keywords: list[str]) -> str:
    return " ".join(k.strip() for k in keywords if k.strip())


def _authors_str(authors: Any) -> str:
    if not authors:
        return ""
    names: list[str] = []
    if isinstance(authors, list):
        for a in authors[:12]:
            if isinstance(a, dict):
                names.append(str(a.get("display_name") or a.get("name") or a.get("author") or "").strip())
            else:
                names.append(str(a).strip())
    return ", ".join(n for n in names if n)


def _item_from_paper(
    *,
    title: str | None,
    abstract: str | None,
    url: str | None,
    year: Any = None,
    authors: str = "",
    source_name: str,
    extra: dict | None = None,
) -> CollectedItem | None:
    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not title and not abstract:
        return None
    bits = [title]
    if year:
        bits.append(f"Year: {year}")
    if authors:
        bits.append(f"Authors: {authors}")
    if abstract:
        bits.append(abstract)
    body = "\n".join(bits).strip()
    return CollectedItem(
        title=title or None,
        content=body,
        original_url=url,
        published_at=str(year) if year else None,
        source_name=source_name,
        content_type="literature",
        extra=extra or {},
    )


class OpenAlexCollector(BaseCollector):
    collector_id = "openalex"
    display_name = "OpenAlex（学术）"
    source_kind = "official_api"
    enabled_by_default = True

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        email = _contact_email()
        api_key = _api_key("openalex", "INSIGHT_OPENALEX_API_KEY")
        params: dict[str, Any] = {
            "search": q,
            "per-page": min(limit, 50),
        }
        if email:
            params["mailto"] = email
        if api_key:
            params["api_key"] = api_key
        url = build_url("https://api.openalex.org/works", params)
        try:
            data = http_get_json(url, timeout=35)
            polite_pause(0.2)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        items: list[CollectedItem] = []
        for row in data.get("results") or []:
            title = row.get("display_name") or row.get("title")
            year = row.get("publication_year")
            abs_inv = row.get("abstract_inverted_index") or {}
            abstract = _reconstruct_openalex_abstract(abs_inv) if abs_inv else ""
            loc = row.get("primary_location") or {}
            landing = (loc.get("landing_page_url") if isinstance(loc, dict) else None) or None
            doi = row.get("doi")
            link = landing or (f"https://doi.org/{doi.split('doi.org/')[-1]}" if doi else None)
            if not link and row.get("id"):
                link = str(row["id"])
            authors = _authors_str(
                [
                    (a.get("author") or {}).get("display_name")
                    for a in (row.get("authorships") or [])
                    if isinstance(a, dict)
                ]
            )
            it = _item_from_paper(
                title=title,
                abstract=abstract,
                url=link,
                year=year,
                authors=authors,
                source_name="OpenAlex",
                extra={"doi": doi},
            )
            if it:
                items.append(it)
            if len(items) >= limit:
                break
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["OpenAlex 无匹配结果"],
            notes="元数据/摘要；开放获取链接视条目而定。",
        )


def _reconstruct_openalex_abstract(inv: dict) -> str:
    """OpenAlex stores abstracts as inverted index {token: [positions]}."""
    try:
        positions: list[tuple[int, str]] = []
        for token, idxs in inv.items():
            for i in idxs:
                positions.append((int(i), str(token)))
        positions.sort(key=lambda x: x[0])
        return " ".join(t for _, t in positions)
    except Exception:  # noqa: BLE001
        return ""


class SemanticScholarCollector(BaseCollector):
    collector_id = "semantic_scholar"
    display_name = "Semantic Scholar（学术）"
    source_kind = "official_api"
    enabled_by_default = True

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        api_key = _api_key("semantic_scholar", "INSIGHT_S2_API_KEY")
        params = {
            "query": q,
            "limit": min(limit, 100),
            "fields": "title,abstract,url,year,authors,externalIds,openAccessPdf",
        }
        url = build_url("https://api.semanticscholar.org/graph/v1/paper/search", params)
        headers = {"User-Agent": DEFAULT_UA}
        if api_key:
            headers["x-api-key"] = api_key
        try:
            data = http_get_json(url, headers=headers, timeout=35)
            polite_pause(0.35)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        items: list[CollectedItem] = []
        for row in data.get("data") or []:
            oa = row.get("openAccessPdf") or {}
            link = (oa.get("url") if isinstance(oa, dict) else None) or row.get("url")
            authors = _authors_str(row.get("authors"))
            it = _item_from_paper(
                title=row.get("title"),
                abstract=row.get("abstract"),
                url=link,
                year=row.get("year"),
                authors=authors,
                source_name="Semantic Scholar",
                extra={"externalIds": row.get("externalIds")},
            )
            if it:
                items.append(it)
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["Semantic Scholar 无匹配结果"],
        )


class CrossrefCollector(BaseCollector):
    collector_id = "crossref"
    display_name = "Crossref（DOI/元数据）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        email = _contact_email()
        ua = DEFAULT_UA
        if email:
            ua = f"InsightEngine/1.0 (mailto:{email}; research)"
        url = build_url(
            "https://api.crossref.org/works",
            {"query": q, "rows": min(limit, 50)},
        )
        try:
            data = http_get_json(url, headers={"User-Agent": ua}, timeout=35)
            polite_pause(0.25)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        items: list[CollectedItem] = []
        for row in (data.get("message") or {}).get("items") or []:
            title_list = row.get("title") or []
            title = title_list[0] if title_list else None
            abstract = re.sub(r"<[^>]+>", " ", row.get("abstract") or "").strip()
            year = None
            issued = (row.get("issued") or {}).get("date-parts") or []
            if issued and issued[0]:
                year = issued[0][0]
            doi = row.get("DOI")
            link = f"https://doi.org/{doi}" if doi else None
            authors = _authors_str(
                [
                    " ".join(
                        x
                        for x in [a.get("given"), a.get("family")]
                        if x
                    )
                    for a in (row.get("author") or [])
                    if isinstance(a, dict)
                ]
            )
            it = _item_from_paper(
                title=title,
                abstract=abstract,
                url=link,
                year=year,
                authors=authors,
                source_name="Crossref",
                extra={"doi": doi},
            )
            if it:
                items.append(it)
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["Crossref 无匹配结果"],
        )


class ArxivCollector(BaseCollector):
    collector_id = "arxiv"
    display_name = "arXiv（预印本）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        terms = [k.strip() for k in keywords if k.strip()]
        search = " AND ".join(f'all:"{t}"' for t in terms) if terms else f'all:"{q}"'
        url = build_url(
            "https://export.arxiv.org/api/query",
            {"search_query": search, "start": 0, "max_results": min(limit, 50)},
        )
        try:
            raw = http_get_bytes(url, timeout=35)
            polite_pause(1.0)  # stay polite to arXiv rate guidance
            root = ET.fromstring(raw)
        except (HTTPError, URLError, TimeoutError, OSError, ET.ParseError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items: list[CollectedItem] = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
            published = entry.findtext("atom:published", default="", namespaces=ns)
            link = None
            for ln in entry.findall("atom:link", ns):
                if ln.get("type") == "text/html" or ln.get("rel") == "alternate":
                    link = ln.get("href")
                    break
            if not link:
                link = entry.findtext("atom:id", default="", namespaces=ns)
            authors = ", ".join(
                (a.findtext("atom:name", default="", namespaces=ns) or "").strip()
                for a in entry.findall("atom:author", ns)
            )
            it = _item_from_paper(
                title=re.sub(r"\s+", " ", title),
                abstract=re.sub(r"\s+", " ", summary),
                url=link,
                year=(published or "")[:4] or None,
                authors=authors,
                source_name="arXiv",
            )
            if it:
                items.append(it)
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["arXiv 无匹配结果"],
            notes="预印本；请求已限速以符合 arXiv 礼仪。",
        )


class EuropePmcCollector(BaseCollector):
    collector_id = "europe_pmc"
    display_name = "Europe PMC（生医/全文库）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        url = build_url(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            {
                "query": q,
                "format": "json",
                "pageSize": min(limit, 50),
                "resultType": "core",
            },
        )
        try:
            data = http_get_json(url, timeout=35)
            polite_pause(0.2)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        items: list[CollectedItem] = []
        for row in (data.get("resultList") or {}).get("result") or []:
            title = row.get("title")
            abstract = row.get("abstractText") or ""
            year = row.get("pubYear")
            pmid = row.get("pmid")
            doi = row.get("doi")
            link = None
            if doi:
                link = f"https://doi.org/{doi}"
            elif pmid:
                link = f"https://europepmc.org/article/MED/{pmid}"
            authors = row.get("authorString") or ""
            it = _item_from_paper(
                title=title,
                abstract=abstract,
                url=link,
                year=year,
                authors=authors,
                source_name="Europe PMC",
                extra={"pmid": pmid, "doi": doi},
            )
            if it:
                items.append(it)
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["Europe PMC 无匹配结果"],
        )


class PubMedCollector(BaseCollector):
    collector_id = "pubmed"
    display_name = "PubMed（NCBI）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        email = _contact_email() or "insight-engine@example.com"
        api_key = _api_key("pubmed", "INSIGHT_NCBI_API_KEY")
        search_params: dict[str, Any] = {
            "db": "pubmed",
            "term": q,
            "retmax": min(limit, 40),
            "retmode": "json",
            "tool": "InsightEngine",
            "email": email,
        }
        if api_key:
            search_params["api_key"] = api_key
        try:
            search = http_get_json(
                build_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", search_params),
                timeout=35,
            )
            polite_pause(0.35)
            ids = (search.get("esearchresult") or {}).get("idlist") or []
            if not ids:
                return CollectResult(
                    self.collector_id, "partial", errors=["PubMed 无匹配结果"]
                )
            sum_params: dict[str, Any] = {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
                "tool": "InsightEngine",
                "email": email,
            }
            if api_key:
                sum_params["api_key"] = api_key
            summary = http_get_json(
                build_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", sum_params),
                timeout=35,
            )
            polite_pause(0.35)
            # abstracts via efetch XML (plain)
            fetch_params = dict(sum_params)
            fetch_params["rettype"] = "abstract"
            fetch_params["retmode"] = "text"
            abs_text = http_get_bytes(
                build_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", fetch_params),
                timeout=40,
            ).decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        abs_by_id = _split_pubmed_abstracts(abs_text, ids)
        result_map = (summary.get("result") or {})
        items: list[CollectedItem] = []
        for pmid in ids:
            row = result_map.get(pmid) or {}
            title = row.get("title")
            year = None
            pub = row.get("pubdate") or ""
            if pub:
                year = pub[:4]
            authors = ", ".join(
                a.get("name", "") for a in (row.get("authors") or [])[:10] if isinstance(a, dict)
            )
            it = _item_from_paper(
                title=title,
                abstract=abs_by_id.get(pmid) or row.get("sorttitle") or "",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                year=year,
                authors=authors,
                source_name="PubMed",
                extra={"pmid": pmid},
            )
            if it:
                items.append(it)
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["PubMed 摘要解析为空"],
        )


def _split_pubmed_abstracts(text: str, ids: list[str]) -> dict[str, str]:
    """Best-effort split of efetch text abstracts."""
    out: dict[str, str] = {}
    if not text.strip():
        return out
    # Records often separated by blank lines; try PMID markers
    chunks = re.split(r"\n(?=PMID:\s*\d+)", text)
    if len(chunks) <= 1:
        chunks = re.split(r"\n{2,}", text)
    for chunk in chunks:
        m = re.search(r"PMID:\s*(\d+)", chunk)
        pmid = m.group(1) if m else None
        body = chunk.strip()
        if pmid:
            out[pmid] = body[:8000]
    # Fallback: assign whole text to first id if nothing parsed
    if not out and ids:
        out[ids[0]] = text.strip()[:8000]
    return out


class CoreCollector(BaseCollector):
    collector_id = "core"
    display_name = "CORE（开放获取）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return bool(_api_key("core", "INSIGHT_CORE_API_KEY"))

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        api_key = _api_key("core", "INSIGHT_CORE_API_KEY")
        if not api_key:
            return CollectResult(
                self.collector_id,
                "not_configured",
                errors=["请先申请并填写 CORE API Key"],
            )
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        url = build_url(
            "https://api.core.ac.uk/v3/search/works",
            {"q": q, "limit": min(limit, 50)},
        )
        try:
            data = http_get_json(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=40,
            )
            polite_pause(0.3)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        results = data if isinstance(data, list) else (data.get("results") or [])
        items: list[CollectedItem] = []
        for row in results:
            title = row.get("title")
            abstract = row.get("abstract") or row.get("description") or ""
            year = row.get("yearPublished") or row.get("year")
            link = row.get("downloadUrl") or row.get("sourceFulltextUrls")
            if isinstance(link, list):
                link = link[0] if link else None
            doi = row.get("doi")
            if not link and doi:
                link = f"https://doi.org/{doi}"
            authors = _authors_str(row.get("authors"))
            it = _item_from_paper(
                title=title,
                abstract=abstract,
                url=link,
                year=year,
                authors=authors,
                source_name="CORE",
                extra={"doi": doi},
            )
            if it:
                items.append(it)
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["CORE 无匹配结果"],
        )


class YoutubeSearchCollector(BaseCollector):
    collector_id = "youtube"
    display_name = "YouTube（官方搜索）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return bool(_api_key("youtube", "INSIGHT_YOUTUBE_API_KEY"))

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        api_key = _api_key("youtube", "INSIGHT_YOUTUBE_API_KEY")
        if not api_key:
            return CollectResult(
                self.collector_id,
                "not_configured",
                errors=["请先填写 YouTube Data API Key"],
            )
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        url = build_url(
            "https://www.googleapis.com/youtube/v3/search",
            {
                "part": "snippet",
                "q": q,
                "type": "video",
                "maxResults": min(limit, 50),
                "key": api_key,
            },
        )
        try:
            data = http_get_json(url, timeout=30)
            polite_pause(0.2)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        items: list[CollectedItem] = []
        for row in data.get("items") or []:
            sn = row.get("snippet") or {}
            vid = (row.get("id") or {}).get("videoId")
            title = sn.get("title")
            desc = sn.get("description") or ""
            link = f"https://www.youtube.com/watch?v={vid}" if vid else None
            body = f"{title or ''}\n{desc}".strip()
            if not body:
                continue
            items.append(
                CollectedItem(
                    title=title,
                    content=body,
                    original_url=link,
                    published_at=sn.get("publishedAt"),
                    source_name="YouTube",
                    content_type="video_meta",
                    extra={"channel": sn.get("channelTitle")},
                )
            )
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["YouTube 无匹配结果"],
            notes="仅官方搜索返回的标题/描述元数据，不下载音视频。",
        )


class OpenAireCollector(BaseCollector):
    collector_id = "openaire"
    display_name = "OpenAIRE（开放科研）"
    source_kind = "official_api"
    enabled_by_default = False

    def available(self) -> bool:
        return True

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        q = _join_keywords(keywords)
        if not q:
            return CollectResult(self.collector_id, "failed", errors=["缺少关键词"])
        url = build_url(
            "https://api.openaire.eu/search/publications",
            {"keywords": q, "format": "json", "size": min(limit, 50)},
        )
        try:
            data = http_get_json(url, timeout=40)
            polite_pause(0.3)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return CollectResult(
                self.collector_id, "failed", errors=[http_error_message(exc)]
            )

        # OpenAIRE JSON shape varies; tolerate nested results
        results = (
            ((data.get("response") or {}).get("results") or {}).get("result")
            or data.get("results")
            or []
        )
        if isinstance(results, dict):
            results = [results]
        items: list[CollectedItem] = []
        for row in results:
            meta = _openaire_metadata(row)
            it = _item_from_paper(
                title=meta.get("title"),
                abstract=meta.get("abstract"),
                url=meta.get("url"),
                year=meta.get("year"),
                authors=meta.get("authors") or "",
                source_name="OpenAIRE",
            )
            if it:
                items.append(it)
            if len(items) >= limit:
                break
        return CollectResult(
            self.collector_id,
            "succeeded" if items else "partial",
            items=items,
            errors=[] if items else ["OpenAIRE 无匹配结果或返回结构无法解析"],
        )


def _openaire_metadata(row: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(row, dict):
        return out
    # Newer Graph-ish / mixed shapes
    for key in ("title", "description", "abstract"):
        if key in row and isinstance(row[key], str):
            out["title" if key == "title" else "abstract"] = row[key]
    if row.get("url"):
        out["url"] = row["url"]
    # Classic nested: metadata.oaf:entity.oaf:result
    try:
        entity = (
            ((row.get("metadata") or {}).get("oaf:entity") or {}).get("oaf:result")
            or (row.get("metadata") or {}).get("result")
            or {}
        )
        title = entity.get("title")
        if isinstance(title, list) and title:
            t0 = title[0]
            out["title"] = t0.get("$") if isinstance(t0, dict) else str(t0)
        elif isinstance(title, dict):
            out["title"] = title.get("$") or title.get("content")
        elif isinstance(title, str):
            out["title"] = title
        desc = entity.get("description")
        if isinstance(desc, list) and desc:
            d0 = desc[0]
            out["abstract"] = d0.get("$") if isinstance(d0, dict) else str(d0)
        elif isinstance(desc, str):
            out["abstract"] = desc
        date = entity.get("dateofacceptance") or entity.get("date")
        if isinstance(date, dict):
            date = date.get("$")
        if date:
            out["year"] = str(date)[:4]
        pid = entity.get("pid")
        if isinstance(pid, list):
            for p in pid:
                if isinstance(p, dict) and (p.get("@classid") == "doi" or "doi" in str(p).lower()):
                    val = p.get("$") or p.get("#text")
                    if val:
                        out["url"] = f"https://doi.org/{val}"
                        break
    except Exception:  # noqa: BLE001
        pass
    return out


OPEN_API_COLLECTORS: list[BaseCollector] = [
    OpenAlexCollector(),
    SemanticScholarCollector(),
    CrossrefCollector(),
    ArxivCollector(),
    EuropePmcCollector(),
    PubMedCollector(),
    CoreCollector(),
    OpenAireCollector(),
    YoutubeSearchCollector(),
]
