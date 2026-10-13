"""OpenAI-compatible Chat Completions adapter (optional)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from insight_engine.llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("INSIGHT_LLM_API_KEY") or ""
        self.base_url = (
            base_url
            or os.environ.get("INSIGHT_LLM_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("INSIGHT_LLM_MODEL") or "gpt-4o-mini"
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key.strip())

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("INSIGHT_LLM_API_KEY is not set")

        messages = [
            {
                "role": "system",
                "content": system_prompt
                + "\n请只输出一个 JSON 对象，不要 Markdown 代码块。",
            },
            {"role": "user", "content": user_prompt},
        ]
        # Some CN gateways reject response_format; try with it, then retry without.
        body = self._post_chat(messages, temperature=temperature, force_json=True)
        if body is None:
            body = self._post_chat(messages, temperature=temperature, force_json=False)
        if body is None:
            raise RuntimeError("LLM HTTP error")

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response missing choices/message/content") from exc

        content = (content or "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM returned non-JSON content") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM JSON root must be an object")
        return parsed

    def _post_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        force_json: bool,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
        }
        if force_json:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if force_json and exc.code in {400, 404, 422}:
                return None
            raise RuntimeError(f"LLM HTTP error: {exc.code}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM network error: {exc.reason}") from None
