"""Strategy interface every LLM backend implements.

The service layer depends only on this abstraction, so swapping Claude for a
local Gemma/Llama model is a config change, not a code change (Strategy +
Dependency-Inversion).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain import TokenUsage


class LLMError(Exception):
    """Raised for any provider-side failure (auth, connection, bad response)."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    usage: TokenUsage


class LLMProvider(ABC):
    """A text-completion backend that returns JSON-shaped responses."""

    #: Human-readable name for logs/UI.
    name: str = "llm"

    @abstractmethod
    def complete(self, system: str, user: str) -> LLMResponse:
        """Run one completion. ``system`` carries the static instructions
        (cacheable), ``user`` the per-request content. Implementations should
        request JSON output where the backend supports it."""

    def list_models(self) -> list[str]:
        """Models available from this backend (best-effort; empty if unknown)."""
        return []

    def health(self) -> tuple[bool, str]:
        """Return (reachable, detail) so the UI can show connection status."""
        return True, "ok"
