"""LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Optional language-model adapter. Must not be required for core features."""

    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """True when this provider can make a model call."""

    @abstractmethod
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """
        Return parsed JSON object from the model.

        Implementations must not log API keys. On failure, raise a RuntimeError
        with a safe message (no secrets).
        """
