"""No-op LLM provider used when no API key is configured."""

from __future__ import annotations

from typing import Any

from insight_engine.llm.base import LLMProvider


class NullLLMProvider(LLMProvider):
    name = "null"

    def available(self) -> bool:
        return False

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        raise RuntimeError("LLM is not configured (NullLLMProvider)")
