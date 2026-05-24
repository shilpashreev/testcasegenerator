"""Best-effort JSON extraction from model output.

Providers request JSON natively (Anthropic prefill, Ollama ``format=json``,
OpenAI ``response_format``), so the happy path is a clean parse. This adds a
local fallback that strips code fences or grabs the outermost object — without
spending another model call to "repair" output.
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_object(raw: str) -> dict:
    """Parse a JSON object from model text. Returns ``{}`` if unrecoverable."""
    if not raw:
        return {}
    raw = raw.strip()

    for candidate in (raw, _extract_fenced(raw), _extract_object(raw)):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return {}


def _extract_fenced(raw: str) -> str:
    m = _FENCE.search(raw)
    return m.group(1) if m else ""


def _extract_object(raw: str) -> str:
    m = _OBJECT.search(raw)
    return m.group(0) if m else ""
