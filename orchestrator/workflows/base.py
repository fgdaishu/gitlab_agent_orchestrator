from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from ..models import Job


RepoReader = Callable[[str], str]
RepoFileChecker = Callable[[str], bool]
RepoCommandRunner = Callable[[str], str]
RepoChangedFiles = Callable[[], list[str]]


@dataclass(frozen=True)
class WorkflowContext:
    job: Job
    project_rules: str
    comments: list[str]
    is_incremental: bool
    handoff_context: str
    read_repo_file: RepoReader


@dataclass(frozen=True)
class WorkflowValidationContext:
    job: Job
    read_repo_file: RepoReader
    repo_file_exists: RepoFileChecker
    run_repo_command: RepoCommandRunner
    changed_files: RepoChangedFiles


@dataclass(frozen=True)
class WorkflowPreflightContext:
    job: Job
    read_repo_file: RepoReader
    repo_file_exists: RepoFileChecker
    run_repo_command: RepoCommandRunner


@dataclass(frozen=True)
class WorkflowPreflightResult:
    passed: bool
    summary: str


@dataclass(frozen=True)
class WorkflowValidationResult:
    passed: bool
    summary: str
    report_path: str | None = None
    report_content: str | None = None


class WorkflowPlugin(Protocol):
    id: str

    def build_prompt(self, context: WorkflowContext) -> str:
        ...

    def preflight(self, context: WorkflowPreflightContext) -> WorkflowPreflightResult:
        ...

    def validate(self, context: WorkflowValidationContext) -> WorkflowValidationResult:
        ...

    def running_labels(self, labels: list[str], trigger_label: str) -> list[str]:
        ...

    def success_labels(self, labels: list[str]) -> list[str]:
        ...

    def failure_labels(self, labels: list[str]) -> list[str]:
        ...

    def cancelled_labels(self, labels: list[str]) -> list[str]:
        ...

    def start_comment(self, job: Job) -> str:
        ...

    def completion_comment(self, job: Job, *, branch: str, merge_request_iid: int | None, validation_summary: str) -> str:
        ...

    def failure_comment(self, job: Job, *, error_type: str, error: str) -> str:
        ...
