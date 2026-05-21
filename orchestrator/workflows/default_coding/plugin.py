from __future__ import annotations

from ...handoff import handoff_path
from ..base import WorkflowContext, WorkflowPreflightContext, WorkflowPreflightResult, WorkflowValidationContext, WorkflowValidationResult
from ..labels import AGENT_STATUS_LABELS
from .prompt_builder import build_default_prompt


class DefaultCodingWorkflow:
    id = "default_coding"

    def build_prompt(self, context: WorkflowContext) -> str:
        return build_default_prompt(
            context.job,
            context.project_rules,
            comments=context.comments,
            is_incremental=context.is_incremental,
            handoff_context=context.handoff_context,
        )

    def preflight(self, context: WorkflowPreflightContext) -> WorkflowPreflightResult:
        return WorkflowPreflightResult(True, "default_coding preflight passed.")

    def validate(self, context: WorkflowValidationContext) -> WorkflowValidationResult:
        handoff = handoff_path(context.job.issue_iid)
        if not context.repo_file_exists(handoff):
            return WorkflowValidationResult(False, f"Agent completed but did not create `{handoff}`.")
        return WorkflowValidationResult(
            True,
            "Handoff present. Tests are not enforced by default_coding; the agent may run tests when the issue explicitly asks for them.",
        )

    def running_labels(self, labels: list[str], trigger_label: str) -> list[str]:
        remove = {trigger_label, *AGENT_STATUS_LABELS}
        kept = [label for label in labels if label not in remove]
        kept.append("agent:running")
        return kept

    def success_labels(self, labels: list[str]) -> list[str]:
        kept = [label for label in labels if label not in AGENT_STATUS_LABELS and not label.startswith("agent:")]
        kept.append("agent:review")
        return kept

    def failure_labels(self, labels: list[str]) -> list[str]:
        kept = [label for label in labels if label not in AGENT_STATUS_LABELS and not label.startswith("agent:")]
        kept.append("agent:failed")
        return kept

    def cancelled_labels(self, labels: list[str]) -> list[str]:
        return [label for label in labels if label != "agent:running"]

    def start_comment(self, job) -> str:
        return f"Agent job `{job.id}` started with `{job.agent}` using workflow `{job.workflow_id}`."

    def completion_comment(self, job, *, branch: str, merge_request_iid: int | None, validation_summary: str) -> str:
        return (
            f"Agent job `{job.id}` completed.\n\n"
            f"- Workflow: `{job.workflow_id}`\n"
            f"- Branch: `{branch}`\n"
            f"- MR: !{merge_request_iid}\n"
            f"- Handoff: `{handoff_path(job.issue_iid)}`\n"
            f"- Checks: {validation_summary.splitlines()[0]}"
        )

    def failure_comment(self, job, *, error_type: str, error: str) -> str:
        return (
            f"Agent job `{job.id}` failed.\n\n"
            f"Stage summary: `{error_type}`\n\n"
            f"Error:\n```text\n{error[-3000:]}\n```"
        )
