from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class AgentType(StrEnum):
    codex = "codex"
    opencode = "opencode"
    claude_code = "claude-code"
    gemini_cli = "gemini-cli"
    custom = "custom"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    project_id: int
    project_path: str
    issue_iid: int
    issue_title: str
    issue_description: str
    trigger_type: str
    trigger_label: str
    agent: str
    workflow_id: str
    workflow_task_id: str | None
    status: str
    repo_http_url: str
    default_branch: str
    branch: str | None
    merge_request_iid: int | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    log_path: str | None
    sandbox_id: int | None = None
    workspace_path: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> "Job":
        return cls(**dict(row))
