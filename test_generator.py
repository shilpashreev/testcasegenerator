import re
import json
import hashlib
from pathlib import Path
import anthropic
from excel_manager import ExcelManager


class TestCaseGenerator:
    def __init__(self, api_key: str, output_dir: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process_jira(self, jira_id: str, jira_data: dict, progress_cb=None) -> dict:
        """
        Main entry. Returns:
          message, test_cases, action, stats
        action: "generated" | "updated" | "unchanged"
        """
        def log(msg):
            if progress_cb:
                progress_cb(msg)

        excel = ExcelManager(self.output_dir)
        requirements = self._extract_requirements(jira_data)
        requirements["jira_id"] = jira_id

        # Validate there is something to work with
        context = self._build_context(requirements)
        if context.strip() == "No content provided.":
            return {
                "message": "No usable content found in the JSON (summary/description/acceptance_criteria/attachments all empty).",
                "test_cases": [],
                "action": "error",
                "stats": {},
            }

        current_hash = self._compute_hash(requirements)

        log("Checking for existing test cases…")
        existing_data = excel.load_existing(jira_id)
        existing_tests = existing_data.get("test_cases", [])
        stored_hash = existing_data.get("requirements_hash", "")

        # ── No change: return as-is ──────────────────────────────────
        if existing_tests and current_hash == stored_hash:
            return {
                "message": f"Requirements unchanged — {len(existing_tests)} existing test cases retained.",
                "test_cases": existing_tests,
                "action": "unchanged",
                "stats": {"total": len(existing_tests), "new": 0, "updated": 0, "kept": len(existing_tests)},
            }

        # ── Update: requirements changed ─────────────────────────────
        if existing_tests:
            log(f"Requirements changed. Reviewing {len(existing_tests)} existing test cases…")
            merged, stats = self._update_test_cases(requirements, existing_tests, jira_id, log)
            action = "updated"
            message = (
                f"Requirements changed — {stats['kept']} kept, "
                f"{stats['updated']} updated, {stats['new']} new. "
                f"Total: {len(merged)} test cases."
            )

        # ── Fresh generate ────────────────────────────────────────────
        else:
            log("Generating test cases from requirements…")
            merged = self._generate_from_scratch(requirements, jira_id, log)
            stats = {"total": len(merged), "new": len(merged), "updated": 0, "kept": 0}
            action = "generated"
            message = f"Generated {len(merged)} new test cases."

        log("Saving to Excel…")
        excel.save(jira_id, merged, current_hash)

        return {
            "message": message,
            "test_cases": merged,
            "action": action,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # Requirements extraction
    # ------------------------------------------------------------------

    def _extract_requirements(self, jira_data: dict) -> dict:
        # Support flat format AND Jira REST API format (fields nested)
        fields = jira_data.get("fields", jira_data)

        def get(*keys):
            for k in keys:
                v = fields.get(k) or jira_data.get(k)
                if v:
                    return v
            return ""

        def get_list(*keys):
            for k in keys:
                v = fields.get(k) or jira_data.get(k)
                if v:
                    return v if isinstance(v, list) else [v]
            return []

        issue_type = get("issuetype", "type")
        if isinstance(issue_type, dict):
            issue_type = issue_type.get("name", "Story")

        status = get("status")
        if isinstance(status, dict):
            status = status.get("name", "")

        attachments = get_list("attachment", "attachments")
        norm_attachments = []
        for att in attachments:
            if isinstance(att, dict):
                norm_attachments.append({
                    "filename": att.get("filename", att.get("name", "attachment")),
                    "content": att.get("content", att.get("body", "")),
                })

        return {
            "jira_id": jira_data.get("id", jira_data.get("key", "")),
            "summary": get("summary"),
            "description": get("description"),
            "acceptance_criteria": get_list("acceptance_criteria", "acceptanceCriteria"),
            "type": issue_type,
            "status": status,
            "updated": get("updated"),
            "attachments": norm_attachments,
        }

    def _compute_hash(self, requirements: dict) -> str:
        content = json.dumps(
            {
                "summary": requirements.get("summary", ""),
                "description": requirements.get("description", ""),
                "acceptance_criteria": requirements.get("acceptance_criteria", []),
                "attachments": [a.get("content", "") for a in requirements.get("attachments", [])],
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    def _build_context(self, requirements: dict) -> str:
        parts = []
        if requirements.get("summary"):
            parts.append(f"SUMMARY:\n{requirements['summary']}")
        if requirements.get("description"):
            parts.append(f"DESCRIPTION:\n{requirements['description']}")
        ac = requirements.get("acceptance_criteria", [])
        if ac:
            parts.append("ACCEPTANCE CRITERIA:\n" + "\n".join(f"  - {c}" for c in ac))
        for att in requirements.get("attachments", []):
            if att.get("content"):
                parts.append(f"ATTACHED DOCUMENT [{att.get('filename', 'doc')}]:\n{att['content']}")
        return "\n\n".join(parts) if parts else "No content provided."

    # ------------------------------------------------------------------
    # Claude API call (with retry on bad JSON)
    # ------------------------------------------------------------------

    def _call_claude(self, prompt: str, retries: int = 2) -> dict:
        """Call Claude and return parsed dict. Retries on JSON parse failure."""
        for attempt in range(retries + 1):
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Try fenced JSON block first
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                candidate = m.group(1)
            else:
                # Fall back to first {...} block
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                candidate = m.group() if m else raw

            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                if attempt == retries:
                    return {}
                # Ask Claude to fix its own output
                prompt = (
                    "The following text is supposed to be valid JSON but has parse errors. "
                    "Return ONLY the corrected JSON, nothing else:\n\n" + raw
                )
        return {}

    # ------------------------------------------------------------------
    # Generate from scratch
    # ------------------------------------------------------------------

    def _generate_from_scratch(self, requirements: dict, jira_id: str, log=None) -> list:
        context = self._build_context(requirements)
        prompt = f"""You are a senior QA engineer generating a complete test suite.

STRICT RULES (must follow exactly):
1. Generate test cases ONLY from the requirements below — nothing else.
2. Do NOT invent, assume, or add any feature, URL, credential, or system detail not explicitly stated.
3. When a value is unspecified, use "As per requirements" — never guess a value.
4. Cover: happy path, error/negative cases, boundary values, and edge cases explicitly mentioned in requirements.
5. Every test must be traceable to a line or section of the requirements.

JIRA REQUIREMENTS ({jira_id}):
{context}

Return ONLY valid JSON (no extra text):
```json
{{
  "test_cases": [
    {{
      "test_id": "TC-{jira_id}-001",
      "jira_id": "{jira_id}",
      "test_title": "Short, action-oriented title",
      "description": "One sentence: what this test verifies",
      "steps": "1. Step one\\n2. Step two\\n3. Step three",
      "data": "Exact test data values, or N/A",
      "expected_result": "Outcome derived directly from requirements"
    }}
  ]
}}
```"""

        result = self._call_claude(prompt)
        tests = result.get("test_cases", [])

        # Assign sequential IDs and ensure jira_id
        for i, tc in enumerate(tests, 1):
            tc["test_id"] = f"TC-{jira_id}-{i:03d}"
            tc["jira_id"] = jira_id

        if log:
            log(f"Claude returned {len(tests)} test cases.")
        return tests

    # ------------------------------------------------------------------
    # Update existing test cases
    # ------------------------------------------------------------------

    def _update_test_cases(
        self, requirements: dict, existing_tests: list, jira_id: str, log=None
    ) -> tuple:
        context = self._build_context(requirements)

        # Determine next available test number
        max_num = 0
        for tc in existing_tests:
            parts = str(tc.get("test_id", "")).split("-")
            try:
                max_num = max(max_num, int(parts[-1]))
            except (ValueError, IndexError):
                pass

        next_id = f"TC-{jira_id}-{max_num + 1:03d}"
        existing_json = json.dumps(existing_tests, indent=2)

        prompt = f"""You are a senior QA engineer reviewing and updating a test suite after requirement changes.

STRICT RULES:
1. Base every decision ONLY on the updated requirements below — nothing else.
2. Do NOT invent, assume, or hallucinate any behavior not stated in the requirements.
3. For each existing test, choose:
   - KEEP  — requirement still valid, no changes needed (preserve test_id exactly)
   - UPDATE — requirement changed; modify only the affected fields (preserve test_id exactly)
   - REMOVE — test covers a removed/obsolete requirement (omit from output)
4. ADD new tests only for requirements that no existing test covers.
5. New test IDs start at {next_id} and increment sequentially.
6. Return ALL tests that should exist after the update (kept + updated + new).

UPDATED REQUIREMENTS ({jira_id}):
{context}

EXISTING TEST CASES:
{existing_json}

Return ONLY valid JSON:
```json
{{
  "test_cases": [
    {{
      "test_id": "TC-{jira_id}-NNN",
      "jira_id": "{jira_id}",
      "test_title": "...",
      "description": "...",
      "steps": "1. ...\\n2. ...",
      "data": "... or N/A",
      "expected_result": "..."
    }}
  ],
  "change_summary": {{
    "kept": 0,
    "updated": 0,
    "removed": 0,
    "new": 0
  }}
}}
```"""

        result = self._call_claude(prompt)

        if not result:
            # Fallback: return existing unchanged
            if log:
                log("Claude returned invalid JSON. Keeping existing tests unchanged.")
            return existing_tests, {
                "total": len(existing_tests), "kept": len(existing_tests),
                "updated": 0, "new": 0,
            }

        merged = result.get("test_cases", existing_tests)
        summary = result.get("change_summary", {})

        for tc in merged:
            tc["jira_id"] = jira_id

        if log:
            log(
                f"Done — kept {summary.get('kept', 0)}, "
                f"updated {summary.get('updated', 0)}, "
                f"new {summary.get('new', 0)}, "
                f"removed {summary.get('removed', 0)}."
            )

        stats = {
            "total": len(merged),
            "kept": summary.get("kept", 0),
            "updated": summary.get("updated", 0),
            "new": summary.get("new", 0),
        }
        return merged, stats
