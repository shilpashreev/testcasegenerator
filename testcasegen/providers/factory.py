"""Factory that maps a ``ProviderConfig`` to a concrete provider strategy.

Adding a new backend means writing one ``LLMProvider`` subclass and registering
it here — no other module changes.
"""

from __future__ import annotations

from ..config import ProviderConfig, ProviderType
from .base import LLMProvider, LLMError
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


class ProviderFactory:
    _REGISTRY = {
        ProviderType.ANTHROPIC: AnthropicProvider,
        ProviderType.OLLAMA: OllamaProvider,
        ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
    }

    @classmethod
    def create(cls, config: ProviderConfig) -> LLMProvider:
        try:
            provider_cls = cls._REGISTRY[config.type]
        except KeyError as exc:
            raise LLMError(f"Unknown provider type: {config.type}") from exc
        return provider_cls(config)


def create_provider(config: ProviderConfig) -> LLMProvider:
    """Convenience wrapper around :meth:`ProviderFactory.create`."""
    return ProviderFactory.create(config)
