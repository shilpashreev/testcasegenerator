"""Test Case Generator package.

Generates requirement-based QA test cases from Jira JSON using a pluggable
LLM backend (Anthropic Claude, Ollama, or any OpenAI-compatible server) and
exports per-ticket Excel files with incremental update logic.
"""

from .config import ProviderConfig, ProviderType, MODEL_SUGGESTIONS, DEFAULT_BASE_URLS
from .domain import TestCase, Requirements, GenerationResult, GenerationStats
from .service import GeneratorService

__all__ = [
    "ProviderConfig",
    "ProviderType",
    "MODEL_SUGGESTIONS",
    "DEFAULT_BASE_URLS",
    "TestCase",
    "Requirements",
    "GenerationResult",
    "GenerationStats",
    "GeneratorService",
]
