"""Configuration objects and provider registry.

A single ``ProviderConfig`` value object describes which LLM backend to use and
how to reach it. The UI builds one of these from user input and hands it to the
``ProviderFactory`` — nothing else in the codebase needs to know which backend
is active.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderType(str, Enum):
    """Supported LLM backends."""

    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"

    @property
    def label(self) -> str:
        return {
            ProviderType.ANTHROPIC: "Anthropic (Claude)",
            ProviderType.OLLAMA: "Ollama (local Gemma / Llama)",
            ProviderType.OPENAI_COMPATIBLE: "OpenAI-compatible (LM Studio / vLLM / llama.cpp)",
        }[self]


# Default endpoints for the self-hosted backends.
DEFAULT_BASE_URLS: dict[ProviderType, str] = {
    ProviderType.OLLAMA: "http://localhost:11434",
    ProviderType.OPENAI_COMPATIBLE: "http://localhost:1234/v1",
}

# Suggested models surfaced in the UI. For Ollama / OpenAI-compatible the live
# list is fetched from the server; these are fallbacks when none is reachable.
MODEL_SUGGESTIONS: dict[ProviderType, list[str]] = {
    ProviderType.ANTHROPIC: [
        "claude-sonnet-4-6",
        "claude-opus-4-7",
        "claude-haiku-4-5-20251001",
    ],
    ProviderType.OLLAMA: [
        "gemma2",
        "gemma2:9b",
        "llama3.1",
        "llama3.1:8b",
        "qwen2.5",
    ],
    ProviderType.OPENAI_COMPATIBLE: [
        "gemma-2-9b-it",
        "meta-llama-3.1-8b-instruct",
    ],
}


@dataclass(slots=True)
class ProviderConfig:
    """Everything needed to construct an LLM provider.

    Attributes:
        type: Which backend to use.
        model: Model identifier understood by that backend.
        api_key: Secret for hosted backends (Anthropic; optional for local).
        base_url: Endpoint for self-hosted backends; ignored for Anthropic.
        max_tokens: Upper bound on generated tokens per call.
        temperature: Sampling temperature (kept low for deterministic test cases).
    """

    type: ProviderType
    model: str
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.2

    def resolved_base_url(self) -> str:
        return self.base_url or DEFAULT_BASE_URLS.get(self.type, "")
