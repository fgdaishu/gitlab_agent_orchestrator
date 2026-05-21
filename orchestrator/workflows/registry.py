from __future__ import annotations

import re
from dataclasses import dataclass

from .base import WorkflowPlugin
from .default_coding.plugin import DefaultCodingWorkflow
from .strict_development.plugin import StrictDevelopmentWorkflow


DEFAULT_WORKFLOW_ID = "default_coding"
STRICT_WORKFLOW_ID = "strict_development"


@dataclass(frozen=True)
class WorkflowMetadata:
    workflow_id: str
    workflow_task_id: str | None = None


_WORKFLOWS: dict[str, WorkflowPlugin] = {
    DEFAULT_WORKFLOW_ID: DefaultCodingWorkflow(),
    STRICT_WORKFLOW_ID: StrictDevelopmentWorkflow(),
}

_ALIASES = {
    "default": DEFAULT_WORKFLOW_ID,
    "default_coding": DEFAULT_WORKFLOW_ID,
    "strict": STRICT_WORKFLOW_ID,
    "strict_development": STRICT_WORKFLOW_ID,
    "strict_developer": STRICT_WORKFLOW_ID,
}


def get_workflow(workflow_id: str | None) -> WorkflowPlugin:
    normalized = normalize_workflow_id(workflow_id)
    return _WORKFLOWS.get(normalized, _WORKFLOWS[DEFAULT_WORKFLOW_ID])


def normalize_workflow_id(workflow_id: str | None) -> str:
    if not workflow_id:
        return DEFAULT_WORKFLOW_ID
    value = workflow_id.strip().lower().replace("-", "_")
    return _ALIASES.get(value, value if value in _WORKFLOWS else DEFAULT_WORKFLOW_ID)


def extract_workflow_metadata(description: str) -> WorkflowMetadata:
    workflow = _parse_metadata_field(description, "Workflow") or DEFAULT_WORKFLOW_ID
    task_id = _parse_metadata_field(description, "Task-ID") or _parse_metadata_field(description, "Task-Id")
    return WorkflowMetadata(workflow_id=normalize_workflow_id(workflow), workflow_task_id=task_id)


def _parse_metadata_field(description: str, field: str) -> str | None:
    pattern = re.compile(rf"(?im)^\s*{re.escape(field)}\s*:\s*(.+?)\s*$")
    match = pattern.search(description or "")
    if not match:
        return None
    value = match.group(1).strip()
    return value or None
