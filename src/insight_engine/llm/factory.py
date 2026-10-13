"""Resolve the active LLM provider from environment."""

from __future__ import annotations

import os

from insight_engine.llm.base import LLMProvider
from insight_engine.llm.null_provider import NullLLMProvider
from insight_engine.llm.openai_compat import OpenAICompatibleProvider


def get_llm_provider() -> LLMProvider:
    if os.environ.get("INSIGHT_LLM_API_KEY"):
        provider = OpenAICompatibleProvider()
        if provider.available():
            return provider
    return NullLLMProvider()
