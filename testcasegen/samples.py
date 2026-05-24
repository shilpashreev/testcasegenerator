"""Bundled sample Jira tickets for the demo / Load Sample button."""

from __future__ import annotations

import json
from pathlib import Path

# sample_jira.json lives at the project root (one level above this package).
_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "sample_jira.json"

_FALLBACK = {
    "id": "PROJ-101",
    "summary": "User Login and Authentication",
    "type": "Story",
    "description": "As a user I want to log in with email and password.",
    "acceptance_criteria": [
        "Valid credentials grant access",
        "Invalid credentials show a generic error",
        "Account locks after 5 failed attempts",
    ],
    "attachments": [],
}


def load_sample_text() -> str:
    if _SAMPLE_PATH.exists():
        return _SAMPLE_PATH.read_text(encoding="utf-8")
    return json.dumps(_FALLBACK, indent=2)
