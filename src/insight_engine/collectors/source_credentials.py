"""Catalog of free / self-serve API credentials for collectors (like LLM presets)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceCredentialSpec:
    id: str
    label: str
    env_var: str
    optional: bool
    note: str
    # If True, collector stays usable without a key (key only raises quota/rate limits).
    works_without_key: bool = True


# Contact email is shared (NCBI / Crossref / OpenAlex / Unpaywall polite pool).
CONTACT_EMAIL_PREF = "source.contact_email"
CONTACT_EMAIL_ENV = "INSIGHT_CONTACT_EMAIL"

SOURCE_CREDENTIALS: tuple[SourceCredentialSpec, ...] = (
    SourceCredentialSpec(
        id="openalex",
        label="OpenAlex",
        env_var="INSIGHT_OPENALEX_API_KEY",
        optional=True,
        works_without_key=True,
        note="免费学术图谱。可不填 Key；建议填联系邮箱。https://openalex.org/",
    ),
    SourceCredentialSpec(
        id="semantic_scholar",
        label="Semantic Scholar",
        env_var="INSIGHT_S2_API_KEY",
        optional=True,
        works_without_key=True,
        note="免费学术检索。无 Key 有公共限流。https://www.semanticscholar.org/product/api",
    ),
    SourceCredentialSpec(
        id="pubmed",
        label="PubMed / NCBI",
        env_var="INSIGHT_NCBI_API_KEY",
        optional=True,
        works_without_key=True,
        note="生医文献。无 Key 可用；有 Key 提高限流。请同时填写联系邮箱。",
    ),
    SourceCredentialSpec(
        id="core",
        label="CORE",
        env_var="INSIGHT_CORE_API_KEY",
        optional=False,
        works_without_key=False,
        note="开放获取论文聚合。需免费申请 Key：https://core.ac.uk/services/api",
    ),
    SourceCredentialSpec(
        id="youtube",
        label="YouTube Data API",
        env_var="INSIGHT_YOUTUBE_API_KEY",
        optional=False,
        works_without_key=False,
        note="官方视频搜索（标题/描述）。Google Cloud 申请 API Key（有免费配额）。",
    ),
)


def secret_key_for(source_id: str) -> str:
    return f"source.api_key.{source_id}"


def credential_by_id(source_id: str) -> SourceCredentialSpec | None:
    for s in SOURCE_CREDENTIALS:
        if s.id == source_id:
            return s
    return None
