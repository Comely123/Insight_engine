"""Resolve LLM provider: default self-hosted OpenAI-compatible, optional user key."""

from __future__ import annotations

import os

from insight_engine.llm.base import LLMProvider
from insight_engine.llm.null_provider import NullLLMProvider
from insight_engine.llm.openai_compat import OpenAICompatibleProvider

# Default: local / self-hosted OpenAI-compatible endpoint (Ollama, vLLM, etc.)
DEFAULT_LOCAL_BASE_URL = os.environ.get(
    "INSIGHT_LLM_BASE_URL", "http://127.0.0.1:11434/v1"
)
DEFAULT_LOCAL_MODEL = os.environ.get("INSIGHT_LLM_MODEL", "qwen2.5:7b")


def get_llm_provider(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    prefer_local: bool = True,
) -> LLMProvider:
    """
    Priority:
    1) Explicit user api_key / base_url (session-only from UI)
    2) Env INSIGHT_LLM_API_KEY (+ optional base URL)
    3) Local self-hosted endpoint with placeholder key (many local servers ignore auth)
    4) Null
    """
    key = (api_key or os.environ.get("INSIGHT_LLM_API_KEY") or "").strip()
    url = (base_url or os.environ.get("INSIGHT_LLM_BASE_URL") or "").strip()
    mdl = (model or os.environ.get("INSIGHT_LLM_MODEL") or DEFAULT_LOCAL_MODEL).strip()

    if key:
        return OpenAICompatibleProvider(
            api_key=key,
            base_url=url or DEFAULT_LOCAL_BASE_URL,
            model=mdl,
        )

    if prefer_local:
        # Local deployments often accept any/non-empty key
        return OpenAICompatibleProvider(
            api_key=os.environ.get("INSIGHT_LLM_LOCAL_KEY", "local"),
            base_url=url or DEFAULT_LOCAL_BASE_URL,
            model=mdl,
        )

    return NullLLMProvider()
