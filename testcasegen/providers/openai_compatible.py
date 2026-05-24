"""OpenAI-compatible provider.

Works with any server exposing the ``/v1/chat/completions`` schema: LM Studio,
vLLM, llama.cpp server, text-generation-webui, and Ollama's own ``/v1`` shim.
Requests a JSON object via ``response_format`` when the server honours it.
"""

from __future__ import annotations

import requests

from ..config import ProviderConfig
from ..domain import TokenUsage
from .base import LLMProvider, LLMResponse, LLMError


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, config: ProviderConfig):
        self._config = config
        self._base = config.resolved_base_url().rstrip("/")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    def complete(self, system: str, user: str) -> LLMResponse:
        payload = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(
                f"{self._base}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=600,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(f"OpenAI-compatible request failed ({self._base}): {exc}") from exc

        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        usage_raw = body.get("usage", {}) or {}
        usage = TokenUsage(
            input_tokens=usage_raw.get("prompt_tokens", 0) or 0,
            output_tokens=usage_raw.get("completion_tokens", 0) or 0,
        )
        return LLMResponse(text=text, usage=usage)

    def list_models(self) -> list[str]:
        try:
            resp = requests.get(f"{self._base}/models", headers=self._headers(), timeout=5)
            resp.raise_for_status()
            return sorted(m["id"] for m in resp.json().get("data", []))
        except requests.RequestException:
            return []

    def health(self) -> tuple[bool, str]:
        try:
            requests.get(f"{self._base}/models", headers=self._headers(), timeout=3).raise_for_status()
            return True, f"connected: {self._base}"
        except requests.RequestException as exc:
            return False, f"unreachable: {exc}"
