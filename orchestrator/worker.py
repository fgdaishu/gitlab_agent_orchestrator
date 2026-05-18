from __future__ import annotations

import time
from pathlib import Path

from .agent import adapter_for
from .config import settings
from .db import JobStore
from .git_ops import commit_all, current_head, has_changes, prepare_issue_branch, push_branch, redact_sensitive_text, slugify
from .gitlab_client import GitLabClient
from .models import Job
from .prompt import build_prompt, read_project_rules
from .sandbox import DockerProjectSandbox, issue_workspace


def _labels_without_agent_trigger(labels: list[str], trigger_label: str) -> list[str]:
    remove = {trigger_label, "agent:failed", "agent:review", "agent:done"}
    kept = [label for label in labels if label not in remove]
    if "agent:running" not in kept:
        kept.append("agent:running")
    return kept


def _finish_labels(labels: list[str], *, success: bool) -> list[str]:
    remove = {"agent:running", "agent:failed", "agent:review"}
    kept = [label for label in labels if label not in remove and not label.startswith("agent:")]
    kept.append("agent:review" if success else "agent:failed")
    return kept


def _current_labels(client: GitLabClient, job: Job) -> list[str]:
    issue = client.get_issue(job.project_id, job.issue_iid)
    labels = issue.get("labels") or []
    return [str(label) for label in labels]


def _repo_dir_for_job(job: Job) -> Path:
    if settings.agent_execution_backend == "docker_project":
        return settings.workspace_root / f"project-{job.project_id}" / "repo"
    return settings.workspace_root / f"project-{job.project_id}" / f"issue-{job.issue_iid}" / "repo"


def process_job(job: Job, store: JobStore, client: GitLabClient) -> None:
    workspace = issue_workspace(settings, job.project_id, job.issue_iid)
    repo_dir = _repo_dir_for_job(job)
    log_path = workspace / "logs" / f"{job.id}.log"
    cancel_file = workspace / f"{job.id}.cancel"
    pid_file = workspace / f"{job.id}.pid"
    branch = f"agent/issue-{job.issue_iid}-{slugify(job.issue_title)}"
    workspace.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    store.attach_workspace(job.id, sandbox_id=None, workspace_path=str(workspace))

    try:
        if cancel_file.exists():
            raise RuntimeError("Job was cancelled before start.")
        labels = _current_labels(client, job)
        client.update_issue_labels(job.project_id, job.issue_iid, _labels_without_agent_trigger(labels, job.trigger_label))
        client.add_issue_note(job.project_id, job.issue_iid, f"Agent job `{job.id}` started with `{job.agent}`.")

        previous = store.latest_for_issue_before(job.project_id, job.issue_iid, job.id)
        is_incremental = previous is not None

        sandbox = None
        if settings.agent_execution_backend == "docker_project":
            docker_sandbox = DockerProjectSandbox(settings, store, job)
            sandbox_record = docker_sandbox.ensure()
            store.attach_workspace(job.id, sandbox_id=sandbox_record.id, workspace_path=str(workspace))
            sandbox = docker_sandbox
            sandbox.prepare_issue_branch(
                client.authenticated_repo_url(job.repo_http_url),
                branch,
                job.default_branch,
                settings.job_timeout_seconds,
            )
            initial_head = sandbox.current_head(settings.job_timeout_seconds)
        else:
            prepare_issue_branch(
                client.authenticated_repo_url(job.repo_http_url),
                repo_dir,
                branch,
                job.default_branch,
                settings.job_timeout_seconds,
                settings.git_author_name,
                settings.git_author_email,
            )
            initial_head = current_head(repo_dir)

        notes = client.get_issue_notes(job.project_id, job.issue_iid)
        comments = [
            str(note.get("body") or "")
            for note in notes
            if not note.get("system")
            and note.get("body")
            and not str(note.get("body") or "").startswith("Agent job `")
        ]
        project_rules = sandbox.read_project_rules(settings.job_timeout_seconds) if sandbox else read_project_rules(repo_dir)
        prompt = build_prompt(job, project_rules, comments=comments, is_incremental=is_incremental)
        if sandbox:
            result = sandbox.run_agent(
                job.agent,
                prompt,
                settings.job_timeout_seconds,
                cancel_file=cancel_file,
                pid_file=pid_file,
                log_path=log_path,
            )
        else:
            result = adapter_for(job.agent, settings).run(
                repo_dir,
                prompt,
                settings.job_timeout_seconds,
                cancel_file=cancel_file,
                pid_file=pid_file,
            )
            log_path.write_text(result.output, encoding="utf-8", errors="replace")
        if cancel_file.exists():
            raise RuntimeError("Job was cancelled after agent execution.")

        checks = "Not enforced by orchestrator. The agent may run tests when the issue explicitly asks for them."
        if sandbox:
            changed = sandbox.has_changes(settings.job_timeout_seconds)
            head_changed = sandbox.current_head(settings.job_timeout_seconds) != initial_head
        else:
            changed = has_changes(repo_dir)
            head_changed = current_head(repo_dir) != initial_head
        if not changed and not head_changed:
            existing_mr = client.find_open_merge_request(job.project_id, branch)
            if not existing_mr:
                raise RuntimeError("Agent completed but produced no code changes.")
        if changed:
            if sandbox:
                sandbox.commit_all(
                    f"feat: implement issue #{job.issue_iid} via {job.agent} agent",
                    settings.git_author_name,
                    settings.git_author_email,
                    settings.job_timeout_seconds,
                )
                sandbox.push_branch(branch, settings.job_timeout_seconds)
            else:
                commit_all(
                    repo_dir,
                    f"feat: implement issue #{job.issue_iid} via {job.agent} agent",
                    settings.git_author_name,
                    settings.git_author_email,
                )
                push_branch(repo_dir, branch, settings.job_timeout_seconds)
        elif head_changed:
            if sandbox:
                sandbox.push_branch(branch, settings.job_timeout_seconds)
            else:
                push_branch(repo_dir, branch, settings.job_timeout_seconds)
        else:
            client.add_issue_note(
                job.project_id,
                job.issue_iid,
                f"Agent job `{job.id}` found no additional file changes. Reusing existing branch/MR for this issue.",
            )

        if not changed and not head_changed and not client.find_open_merge_request(job.project_id, branch):
            raise RuntimeError("Agent completed but produced no code changes.")

        mr = client.create_or_get_merge_request(
            job.project_id,
            source_branch=branch,
            target_branch=job.default_branch,
            title=f"[Agent] {job.issue_title}",
            description=(
                "## Agent Summary\n\n"
                f"This MR was generated by `{job.agent}` based on issue #{job.issue_iid}.\n\n"
                "## Checks\n\n"
                f"{checks}\n\n"
                "## Review Checklist\n\n"
                "- [ ] Review generated code\n"
                "- [ ] Confirm tests and CI\n\n"
                f"Closes #{job.issue_iid}\n"
            ),
        )
        mr_iid = int(mr.get("iid")) if mr and mr.get("iid") else None
        store.mark_succeeded(job.id, branch=branch, merge_request_iid=mr_iid, log_path=str(log_path))
        labels = _current_labels(client, job)
        client.update_issue_labels(job.project_id, job.issue_iid, _finish_labels(labels, success=True))
        client.add_issue_note(
            job.project_id,
            job.issue_iid,
            f"Agent job `{job.id}` completed.\n\n- Branch: `{branch}`\n- MR: !{mr_iid}\n- Checks: {checks.splitlines()[0]}",
        )
    except Exception as exc:
        was_cancelled = cancel_file.exists() or "cancelled" in str(exc).lower()
        if was_cancelled:
            store.mark_cancelled(job.id, error=str(exc))
        else:
            store.mark_failed(job.id, error=redact_sensitive_text(str(exc)), branch=branch, log_path=str(log_path) if log_path.exists() else None)
        try:
            labels = _current_labels(client, job)
            if was_cancelled:
                client.update_issue_labels(job.project_id, job.issue_iid, [label for label in labels if label != "agent:running"])
            else:
                client.update_issue_labels(job.project_id, job.issue_iid, _finish_labels(labels, success=False))
            client.add_issue_note(
                job.project_id,
                job.issue_iid,
                f"Agent job `{job.id}` {'cancelled' if was_cancelled else 'failed'}.\n\nStage summary: `{type(exc).__name__}`\n\nError:\n```text\n{redact_sensitive_text(str(exc))[-3000:]}\n```",
            )
        except Exception:
            pass
    finally:
        pid_file.unlink(missing_ok=True)


def run_forever() -> None:
    store = JobStore(settings.database_path)
    client = GitLabClient(settings.gitlab_url, settings.gitlab_token)
    while True:
        job = store.claim_next()
        if job:
            process_job(job, store, client)
            continue
        time.sleep(settings.job_poll_interval_seconds)


if __name__ == "__main__":
    run_forever()
