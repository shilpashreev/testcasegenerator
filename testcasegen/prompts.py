"""Prompt construction, kept deliberately compact to minimize tokens.

Design:
  * ``SYSTEM_PROMPT`` holds all the static rules and the output schema. It never
    varies between requests, so the Anthropic provider marks it cacheable and
    every backend pays for it only as fixed overhead.
  * User prompts carry only the per-request payload (requirements, and existing
    tests on update) in compact JSON — no pretty-printing, no repeated rules.
"""

from __future__ import annotations

import json

from .domain import Requirements, TestCase


SYSTEM_PROMPT = (
    "You are a senior QA engineer. Generate or revise software test cases from "
    "Jira requirements.\n"
    "Rules:\n"
    "1. Derive every test ONLY from the given requirements; never invent features, "
    "URLs, credentials, or values.\n"
    "2. If a value is unspecified, use \"As per requirements\".\n"
    "3. Cover happy path, negative/error, boundary, and edge cases that the "
    "requirements imply.\n"
    "4. Each test must be traceable to a requirement.\n"
    'Output ONLY a JSON object: {"test_cases":[{"test_title","description",'
    '"steps","data","expected_result"}]}. '
    "Use \\n to separate numbered steps. No prose outside the JSON."
)

# Extra rules appended (still static per-mode) for the update flow.
_UPDATE_SYSTEM_SUFFIX = (
    "\nUpdate mode: you receive EXISTING test cases. Keep tests whose requirement "
    "is unchanged (preserve their test_id), modify tests whose requirement changed "
    "(preserve test_id), drop tests for removed requirements, and add tests for "
    'newly uncovered requirements. Also return "change_summary":'
    '{"kept","updated","removed","new"}.'
)


def system_prompt(update: bool = False) -> str:
    return SYSTEM_PROMPT + (_UPDATE_SYSTEM_SUFFIX if update else "")


def build_generate_user(requirements: Requirements) -> str:
    return f"JIRA {requirements.jira_id} REQUIREMENTS:\n{requirements.to_context()}"


def build_update_user(requirements: Requirements, existing: list[TestCase]) -> str:
    # Compact JSON (no indentation / spaces) to save tokens on the existing set.
    existing_json = json.dumps(
        [tc.to_dict() for tc in existing], separators=(",", ":")
    )
    return (
        f"UPDATED JIRA {requirements.jira_id} REQUIREMENTS:\n"
        f"{requirements.to_context()}\n\n"
        f"EXISTING TEST CASES:\n{existing_json}"
    )
