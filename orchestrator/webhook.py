from __future__ import annotations

from typing import Any

from .workflows import extract_workflow_metadata

AGENT_LABEL_PREFIX = "agent:"
LABEL_TO_AGENT = {
    "agent:codex": "codex",
    "agent:opencode": "opencode",
    "agent:claude": "claude-code",
    "agent:gemini": "gemini-cli",
}


def _label_name(label: Any) -> str:
    if isinstance(label, str):
        return label
    if isinstance(label, dict):
        return str(label.get("title") or label.get("name") or "")
    return ""


def _label_set(labels: Any) -> set[str]:
    if not isinstance(labels, list):
        return set()
    return {name for item in labels if (name := _label_name(item))}


def newly_added_agent_label(payload: dict[str, Any], configured_label: str) -> tuple[str, str] | None:
    if payload.get("object_kind") != "issue":
        return None

    candidate_labels = set(LABEL_TO_AGENT)
    candidate_labels.add(configured_label)

    labels_change = payload.get("changes", {}).get("labels")
    if isinstance(labels_change, dict):
        previous = _label_set(labels_change.get("previous"))
        current = _label_set(labels_change.get("current"))
        added = current - previous
    else:
        # GitLab issue creation webhooks may include labels on object_attributes
        # without a changes.labels block. Treat that as a trigger candidate; the
        # job store still dedupes pending/running jobs for the same issue.
        issue = payload.get("object_attributes") or {}
        added = _label_set(issue.get("labels"))

    for label in sorted(added):
        if label in candidate_labels:
            return label, LABEL_TO_AGENT.get(label, label.removeprefix(AGENT_LABEL_PREFIX))
    return None


def extract_issue_job(payload: dict[str, Any], trigger_label: str, agent: str) -> dict[str, Any]:
    project = payload.get("project") or {}
    issue = payload.get("object_attributes") or {}
    project_id = int(project.get("id") or issue.get("project_id"))
    description = issue.get("description") or ""
    workflow = extract_workflow_metadata(str(description))
    return {
        "project_id": project_id,
        "project_path": project.get("path_with_namespace") or project.get("web_url") or str(project_id),
        "issue_iid": int(issue["iid"]),
        "issue_title": issue.get("title") or "",
        "issue_description": description,
        "trigger_label": trigger_label,
        "agent": agent,
        "workflow_id": workflow.workflow_id,
        "workflow_task_id": workflow.workflow_task_id,
        "repo_http_url": project.get("git_http_url") or project.get("http_url") or "",
        "default_branch": project.get("default_branch") or "main",
    }
