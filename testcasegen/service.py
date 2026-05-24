"""Application service that orchestrates the whole generation flow.

Acts as a Facade over extraction, hashing, the LLM provider, and the Excel
repository. The incremental logic lives here:

    no existing file        -> generate from scratch
    hash unchanged          -> return existing untouched (no model call)
    hash changed            -> ask the model to revise the suite
"""

from __future__ import annotations

from typing import Callable

from .domain import (
    ACTION_ERROR,
    ACTION_GENERATED,
    ACTION_UNCHANGED,
    ACTION_UPDATED,
    GenerationResult,
    GenerationStats,
    Requirements,
    TestCase,
    TokenUsage,
)
from .extraction import RequirementExtractor
from .json_utils import parse_json_object
from .prompts import build_generate_user, build_update_user, system_prompt
from .providers.base import LLMError, LLMProvider
from .storage import ExcelRepository

ProgressCallback = Callable[[str], None]


class GeneratorService:
    def __init__(self, provider: LLMProvider, repository: ExcelRepository):
        self._provider = provider
        self._repo = repository
        self._extractor = RequirementExtractor()

    def process(
        self,
        jira_id: str,
        jira_data: dict,
        progress_cb: ProgressCallback | None = None,
    ) -> GenerationResult:
        def log(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)

        requirements = self._extractor.extract(jira_data)
        requirements.jira_id = jira_id

        if requirements.is_empty():
            return GenerationResult(
                message="No usable content found (summary/description/acceptance_criteria/attachments all empty).",
                action=ACTION_ERROR,
            )

        current_hash = requirements.content_hash()

        log("Checking for existing test cases...")
        existing, stored_hash = self._repo.load(jira_id)

        if existing and current_hash == stored_hash:
            return GenerationResult(
                message=f"Requirements unchanged - {len(existing)} existing test cases retained.",
                test_cases=existing,
                action=ACTION_UNCHANGED,
                stats=GenerationStats(total=len(existing), kept=len(existing)),
            )

        try:
            if existing:
                log(f"Requirements changed. Revising {len(existing)} existing test cases...")
                result = self._update(requirements, existing, log)
            else:
                log("Generating test cases from requirements...")
                result = self._generate(requirements, log)
        except LLMError as exc:
            return GenerationResult(message=str(exc), action=ACTION_ERROR)

        log("Saving to Excel...")
        self._repo.save(jira_id, result.test_cases, current_hash)
        return result

    # ------------------------------------------------------------------
    # Generation modes
    # ------------------------------------------------------------------

    def _generate(self, requirements: Requirements, log: ProgressCallback) -> GenerationResult:
        response = self._provider.complete(
            system=system_prompt(update=False),
            user=build_generate_user(requirements),
        )
        tests = self._parse_tests(response.text, requirements.jira_id, start=1)
        log(f"Model returned {len(tests)} test cases.")
        return GenerationResult(
            message=f"Generated {len(tests)} new test cases.",
            test_cases=tests,
            action=ACTION_GENERATED,
            stats=GenerationStats(total=len(tests), new=len(tests)),
            usage=response.usage,
        )

    def _update(
        self, requirements: Requirements, existing: list[TestCase], log: ProgressCallback
    ) -> GenerationResult:
        response = self._provider.complete(
            system=system_prompt(update=True),
            user=build_update_user(requirements, existing),
        )
        data = parse_json_object(response.text)

        if not data or "test_cases" not in data:
            log("Model returned no valid update. Keeping existing tests unchanged.")
            return GenerationResult(
                message="Could not parse model update - existing tests kept unchanged.",
                test_cases=existing,
                action=ACTION_UPDATED,
                stats=GenerationStats(total=len(existing), kept=len(existing)),
                usage=response.usage,
            )

        tests = self._coerce_tests(data.get("test_cases", []), requirements.jira_id, renumber=False)
        summary = data.get("change_summary", {}) or {}
        stats = GenerationStats(
            total=len(tests),
            kept=int(summary.get("kept", 0) or 0),
            updated=int(summary.get("updated", 0) or 0),
            new=int(summary.get("new", 0) or 0),
            removed=int(summary.get("removed", 0) or 0),
        )
        log(f"Done - kept {stats.kept}, updated {stats.updated}, new {stats.new}, removed {stats.removed}.")
        return GenerationResult(
            message=(
                f"Requirements changed - {stats.kept} kept, {stats.updated} updated, "
                f"{stats.new} new. Total: {len(tests)} test cases."
            ),
            test_cases=tests,
            action=ACTION_UPDATED,
            stats=stats,
            usage=response.usage,
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_tests(self, raw: str, jira_id: str, start: int) -> list[TestCase]:
        data = parse_json_object(raw)
        if not data:
            raise LLMError("Model did not return parseable JSON.")
        return self._coerce_tests(data.get("test_cases", []), jira_id, renumber=True, start=start)

    @staticmethod
    def _coerce_tests(
        raw_tests: list, jira_id: str, *, renumber: bool, start: int = 1
    ) -> list[TestCase]:
        tests: list[TestCase] = []
        for i, raw in enumerate(raw_tests, start):
            if not isinstance(raw, dict):
                continue
            tc = TestCase.from_dict(raw)
            tc.jira_id = jira_id
            if renumber or not tc.test_id:
                tc.test_id = f"TC-{jira_id}-{i:03d}"
            tests.append(tc)
        return tests
