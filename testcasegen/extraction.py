"""Turn raw Jira JSON (flat or REST-API nested) into a ``Requirements`` object.

Isolated from the service so the parsing quirks of different Jira payload
shapes live in one place.
"""

from __future__ import annotations

from .domain import Attachment, Requirements


class RequirementExtractor:
    """Normalizes both the flat sample format and the Jira REST ``fields`` shape."""

    def extract(self, jira_data: dict) -> Requirements:
        fields = jira_data.get("fields", jira_data)

        def get(*keys: str) -> str:
            for k in keys:
                v = fields.get(k) or jira_data.get(k)
                if v:
                    return v
            return ""

        def get_list(*keys: str) -> list:
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

        attachments: list[Attachment] = []
        for att in get_list("attachment", "attachments"):
            if isinstance(att, dict):
                attachments.append(
                    Attachment(
                        filename=att.get("filename", att.get("name", "attachment")),
                        content=att.get("content", att.get("body", "")),
                    )
                )

        return Requirements(
            jira_id=jira_data.get("id", jira_data.get("key", "")),
            summary=get("summary"),
            description=get("description"),
            acceptance_criteria=[str(c) for c in get_list("acceptance_criteria", "acceptanceCriteria")],
            type=issue_type or "Story",
            status=status,
            updated=get("updated"),
            attachments=attachments,
        )
