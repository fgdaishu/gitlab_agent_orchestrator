from __future__ import annotations

from ...handoff import handoff_path
from ..base import WorkflowContext, WorkflowPreflightContext, WorkflowPreflightResult, WorkflowValidationContext, WorkflowValidationResult
from ..labels import AGENT_STATUS_LABELS, STRICT_STATUS_LABELS
from .validation import preflight_strict_task, validate_strict_task


class StrictDevelopmentWorkflow:
    id = "strict_development"
    prompt_workflow_name = "strict_development"
    prompt_intro = "Execute this Strict Development task now."
    rules_heading = "Strict Development rules"
    label_prefix = "strict"
    comment_name = "Strict Development"

    def build_prompt(self, context: WorkflowContext) -> str:
        job = context.job
        task_id = job.workflow_task_id or _task_id_from_title(job.issue_title)
        if not task_id:
            raise RuntimeError(f"{self.id} workflow requires `Task-ID: <id>` in issue metadata or `[<id>]` in the issue title.")

        task_card_path = f"task-cards/{task_id}.yaml"
        context_pack_path = f"context-packs/{task_id}.md"
        task_card = context.read_repo_file(task_card_path)
        context_pack = context.read_repo_file(context_pack_path)
        if not task_card.strip():
            raise RuntimeError(f"{self.id} task card not found or empty: `{task_card_path}`.")
        if not context_pack.strip():
            raise RuntimeError(f"{self.id} context pack not found or empty: `{context_pack_path}`.")

        comments = ""
        if context.comments:
            comments = "\nIssue comments, oldest to newest:\n" + "\n\n".join(f"- {comment}" for comment in context.comments[-20:]) + "\n"
        rules = f"\nProject rules from repository:\n{context.project_rules}\n" if context.project_rules else ""
        handoffs = f"\nDependency handoff context:\n{context.handoff_context}\n" if context.handoff_context else ""
        mode = (
            "This issue already has an agent branch. Continue from the current branch state and implement only the new or still-missing requested changes."
            if context.is_incremental
            else "This is the first agent pass for this issue."
        )

        return f"""{self.prompt_intro} Modify repository files directly in the current working directory.

Task source:
- Project: {job.project_path}
- Issue: #{job.issue_iid}
- Workflow: {self.prompt_workflow_name}
- Task ID: {task_id}
- Title: {job.issue_title}

Issue description:
{job.issue_description}
{comments}
{handoffs}
{rules}
Execution mode:
{mode}

Task card from `{task_card_path}`:
```yaml
{task_card.strip()}
```

Context pack from `{context_pack_path}`:
```markdown
{context_pack.strip()}
```

{self.rules_heading}:
- Execute only the task described by the task card.
- Treat the task card, context pack, contracts, and security invariants as authoritative.
- Do not expand compatibility scope beyond the task card.
- Modify only files allowed by the task card.
- Do not modify forbidden files if the task card lists any.
- Do not introduce unsafe code unless the task card explicitly allows it.
- Do not weaken validation, resource limits, or malformed-input handling to pass tests.
- Run the validation commands listed in the task card when practical, and fix failures caused by your changes.
- Do not run git commit.
- Do not run git push.
- Leave all file changes unstaged or staged for the orchestrator to commit and push.
- Maintain a structured handoff document at `{handoff_path(job.issue_iid)}`.
- The handoff must include: Summary, Changed Files, Decisions, Interfaces / Contracts, Follow-up Needed, Test Notes, and Context For Next Issues.

Expected output:
- Implement the requested strict development task.
- Add or update task-specific tests when appropriate.
- Add or update `{handoff_path(job.issue_iid)}`.
- Provide a concise summary of changes and validation performed.
"""

    def validate(self, context: WorkflowValidationContext) -> WorkflowValidationResult:
        return validate_strict_task(context)

    def preflight(self, context: WorkflowPreflightContext) -> WorkflowPreflightResult:
        return preflight_strict_task(context)

    def running_labels(self, labels: list[str], trigger_label: str) -> list[str]:
        remove = {trigger_label, *AGENT_STATUS_LABELS, *STRICT_STATUS_LABELS}
        kept = [label for label in labels if label not in remove]
        kept.append(f"{self.label_prefix}:running")
        return kept

    def success_labels(self, labels: list[str]) -> list[str]:
        kept = [label for label in labels if label not in STRICT_STATUS_LABELS and label not in AGENT_STATUS_LABELS and not label.startswith("agent:")]
        kept.append(f"{self.label_prefix}:review")
        return kept

    def failure_labels(self, labels: list[str]) -> list[str]:
        kept = [label for label in labels if label not in STRICT_STATUS_LABELS and label not in AGENT_STATUS_LABELS and not label.startswith("agent:")]
        kept.append(f"{self.label_prefix}:validation-failed")
        return kept

    def cancelled_labels(self, labels: list[str]) -> list[str]:
        return [label for label in labels if label not in {"strict:running", "agent:running"}]

    def start_comment(self, job) -> str:
        task_id = job.workflow_task_id or _task_id_from_title(job.issue_title) or "unknown"
        return f"{self.comment_name} job `{job.id}` started with `{job.agent}`.\n\n- Task ID: `{task_id}`\n- Workflow: `{self.id}`"

    def completion_comment(self, job, *, branch: str, merge_request_iid: int | None, validation_summary: str) -> str:
        task_id = job.workflow_task_id or _task_id_from_title(job.issue_title) or "unknown"
        return (
            f"{self.comment_name} job `{job.id}` completed.\n\n"
            f"- Task ID: `{task_id}`\n"
            f"- Branch: `{branch}`\n"
            f"- MR: !{merge_request_iid}\n"
            f"- Handoff: `{handoff_path(job.issue_iid)}`\n"
            f"- Task card: `task-cards/{task_id}.yaml`\n"
            f"- Context pack: `context-packs/{task_id}.md`\n"
            f"- Validation report: `reports/{task_id}-validation.md`\n"
            f"- Validation: {validation_summary.splitlines()[0]}"
        )

    def failure_comment(self, job, *, error_type: str, error: str) -> str:
        task_id = job.workflow_task_id or _task_id_from_title(job.issue_title) or "unknown"
        return (
            f"{self.comment_name} job `{job.id}` failed validation or execution.\n\n"
            f"- Task ID: `{task_id}`\n"
            f"- Stage summary: `{error_type}`\n\n"
            f"Error:\n```text\n{error[-3000:]}\n```"
        )


def _task_id_from_title(title: str) -> str | None:
    stripped = (title or "").strip()
    if not stripped.startswith("[") or "]" not in stripped:
        return None
    candidate = stripped[1 : stripped.index("]")].strip()
    return candidate or None
