"""Domain value objects.

These dataclasses are the vocabulary the rest of the app speaks in. Behaviour
that belongs to the data lives here (e.g. ``Requirements`` knows how to hash
and render itself) so services stay thin.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict


# Canonical column order used everywhere (UI, Excel, prompts).
TEST_CASE_FIELDS = [
    "test_id",
    "jira_id",
    "test_title",
    "description",
    "steps",
    "data",
    "expected_result",
]


@dataclass(slots=True)
class TestCase:
    test_id: str = ""
    jira_id: str = ""
    test_title: str = ""
    description: str = ""
    steps: str = ""
    data: str = ""
    expected_result: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in TEST_CASE_FIELDS}

    @classmethod
    def from_dict(cls, raw: dict) -> "TestCase":
        clean = {k: str(raw.get(k, "") or "").strip() for k in TEST_CASE_FIELDS}
        return cls(**clean)


@dataclass(slots=True)
class Attachment:
    filename: str = "attachment"
    content: str = ""


@dataclass(slots=True)
class Requirements:
    """Normalized requirements extracted from a Jira ticket."""

    jira_id: str = ""
    summary: str = ""
    description: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    type: str = "Story"
    status: str = ""
    updated: str = ""
    attachments: list[Attachment] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            [self.summary, self.description, self.acceptance_criteria, self.attachments]
        )

    def content_hash(self) -> str:
        """Stable hash over the *meaningful* requirement content only.

        Excludes volatile fields (status, updated) so cosmetic Jira changes do
        not trigger needless regeneration.
        """
        payload = json.dumps(
            {
                "summary": self.summary,
                "description": self.description,
                "acceptance_criteria": self.acceptance_criteria,
                "attachments": [a.content for a in self.attachments],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_context(self) -> str:
        """Render requirements as compact prompt context (token-conscious)."""
        parts: list[str] = []
        if self.summary:
            parts.append(f"SUMMARY: {self.summary}")
        if self.description:
            parts.append(f"DESCRIPTION:\n{self.description}")
        if self.acceptance_criteria:
            joined = "\n".join(f"- {c}" for c in self.acceptance_criteria)
            parts.append(f"ACCEPTANCE CRITERIA:\n{joined}")
        for att in self.attachments:
            if att.content:
                parts.append(f"ATTACHMENT [{att.filename}]:\n{att.content}")
        return "\n\n".join(parts) if parts else "No content provided."


@dataclass(slots=True)
class GenerationStats:
    total: int = 0
    new: int = 0
    updated: int = 0
    kept: int = 0
    removed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
        )

    def to_dict(self) -> dict:
        return asdict(self)


# Result actions
ACTION_GENERATED = "generated"
ACTION_UPDATED = "updated"
ACTION_UNCHANGED = "unchanged"
ACTION_ERROR = "error"


@dataclass(slots=True)
class GenerationResult:
    message: str
    test_cases: list[TestCase] = field(default_factory=list)
    action: str = ACTION_GENERATED
    stats: GenerationStats = field(default_factory=GenerationStats)
    usage: TokenUsage = field(default_factory=TokenUsage)

    def test_case_dicts(self) -> list[dict]:
        return [tc.to_dict() for tc in self.test_cases]
