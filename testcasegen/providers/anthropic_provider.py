"""Anthropic Claude provider.

Token optimizations applied here:
  * The static system prompt is sent as a cacheable block (``cache_control``),
    so repeated calls only pay for it once within the 5-minute cache window.
  * The assistant turn is prefilled with ``{`` to force a JSON object and avoid
    spending output tokens on prose preamble.
"""

from __future__ import annotations

from ..config import ProviderConfig
from ..domain import TokenUsage
from .base import LLMProvider, LLMResponse, LLMError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, config: ProviderConfig):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("anthropic package not installed. Run: pip install anthropic") from exc

        if not config.api_key:
            raise LLMError("Anthropic API key is required.")

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=config.api_key)
        self._config = config

    def complete(self, system: str, user: str) -> LLMResponse:
        try:
            resp = self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": "{"},  # prefill -> forces JSON
                ],
            )
        except self._anthropic.AuthenticationError as exc:
            raise LLMError("Invalid Anthropic API key.") from exc
        except self._anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        # Re-attach the prefilled opening brace stripped by the assistant turn.
        text = "{" + resp.content[0].text
        usage = TokenUsage(
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
            cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        )
        return LLMResponse(text=text, usage=usage)

    def list_models(self) -> list[str]:
        from ..config import MODEL_SUGGESTIONS, ProviderType

        return MODEL_SUGGESTIONS[ProviderType.ANTHROPIC]

    def health(self) -> tuple[bool, str]:
        return (bool(self._config.api_key), "API key set" if self._config.api_key else "missing key")
