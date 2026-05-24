"""Ollama provider for local open-source models (Gemma, Llama, Qwen, ...).

Talks to the native Ollama HTTP API at ``/api/chat`` with ``format="json"`` so
the model returns a JSON object directly.
"""

from __future__ import annotations

import requests

from ..config import ProviderConfig
from ..domain import TokenUsage
from .base import LLMProvider, LLMResponse, LLMError


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, config: ProviderConfig):
        self._config = config
        self._base = config.resolved_base_url().rstrip("/")

    def complete(self, system: str, user: str) -> LLMResponse:
        payload = {
            "model": self._config.model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self._config.temperature,
                "num_predict": self._config.max_tokens,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(f"{self._base}/api/chat", json=payload, timeout=600)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(f"Ollama request failed ({self._base}): {exc}") from exc

        body = resp.json()
        text = body.get("message", {}).get("content", "")
        usage = TokenUsage(
            input_tokens=body.get("prompt_eval_count", 0) or 0,
            output_tokens=body.get("eval_count", 0) or 0,
        )
        return LLMResponse(text=text, usage=usage)

    def list_models(self) -> list[str]:
        try:
            resp = requests.get(f"{self._base}/api/tags", timeout=5)
            resp.raise_for_status()
            return sorted(m["name"] for m in resp.json().get("models", []))
        except requests.RequestException:
            return []

    def health(self) -> tuple[bool, str]:
        try:
            requests.get(f"{self._base}/api/tags", timeout=3).raise_for_status()
            return True, f"connected: {self._base}"
        except requests.RequestException as exc:
            return False, f"unreachable: {exc}"
