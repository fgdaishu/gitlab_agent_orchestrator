from __future__ import annotations

import time
from pathlib import Path
import shlex
import base64

from .agent import adapter_for
from .config import settings
from .db import JobStore
from .git_ops import CommandError, changed_files, commit_all, current_head, has_changes, prepare_issue_branch, push_branch, redact_sensitive_text, run, slugify
from .gitlab_client import GitLabClient
from .handoff import build_handoff_context, handoff_path, parse_issue_dependencies
from .models import Job
from .sandbox import DockerProjectSandbox, issue_workspace
from .workflows.base import WorkflowContext, WorkflowPreflightContext, WorkflowValidationContext
from .workflows.default_coding.prompt_builder import read_project_rules
from .workflows.registry import get_workflow


def _current_labels(client: GitLabClient, job: Job) -> list[str]:
    issue = client.get_issue(job.project_id, job.issue_iid)
    labels = issue.get("labels") or []
    return [str(label) for label in labels]


def _repo_dir_for_job(job: Job) -> Path:
    if settings.agent_execution_backend == "docker_project":
        return settings.workspace_root / f"project-{job.project_id}" / "repo"
    return settings.workspace_root / f"project-{job.project_id}" / f"issue-{job.issue_iid}" / "repo"


def _read_dependency_handoff_local(repo_dir: Path, dependency: Job, timeout: int) -> str:
    path = handoff_path(dependency.issue_iid)
    if dependency.branch:
        try:
            run(["git", "fetch", "origin", f"{dependency.branch}:refs/remotes/origin/{dependency.branch}"], cwd=repo_dir, timeout=timeout)
            return run(["git", "show", f"origin/{dependency.branch}:{path}"], cwd=repo_dir, timeout=timeout)
        except CommandError:
            pass
    file_path = repo_dir / path
    if file_path.exists():
        return file_path.read_text(encoding="utf-8", errors="replace")
    return ""


def _read_dependency_handoff_sandbox(sandbox: DockerProjectSandbox, dependency: Job, timeout: int) -> str:
    path = handoff_path(dependency.issue_iid)
    if dependency.branch:
        try:
            sandbox.exec(["git", "fetch", "origin", f"{dependency.branch}:refs/remotes/origin/{dependency.branch}"], cwd="/workspace/repo", timeout=timeout)
            return sandbox.exec(["git", "show", f"origin/{dependency.branch}:{path}"], cwd="/workspace/repo", timeout=timeout)
        except Exception:
            pass
    try:
        return sandbox.exec_shell(f"cat {path}", cwd="/workspace/repo", timeout=timeout)
    except Exception:
        return ""


def _collect_handoff_context(job: Job, store: JobStore, sandbox: DockerProjectSandbox | None, repo_dir: Path) -> str:
    dependencies = parse_issue_dependencies(job.issue_description)
    strict_dependencies = dependencies.depends_on
    context_sources = tuple(iid for iid in (*dependencies.depends_on, *dependencies.context_from) if iid != job.issue_iid)
    handoffs: dict[int, str] = {}

    for issue_iid in context_sources:
        dependency = store.latest_for_issue(job.project_id, issue_iid)
        if dependency is None or dependency.status != "succeeded":
            if issue_iid in strict_dependencies:
                raise RuntimeError(f"Dependency issue #{issue_iid} has not completed successfully yet.")
            continue
        content = (
            _read_dependency_handoff_sandbox(sandbox, dependency, settings.job_timeout_seconds)
            if sandbox
            else _read_dependency_handoff_local(repo_dir, dependency, settings.job_timeout_seconds)
        )
        if not content.strip():
            if issue_iid in strict_dependencies:
                raise RuntimeError(f"Dependency issue #{issue_iid} completed but `{handoff_path(issue_iid)}` was not found.")
            continue
        handoffs[issue_iid] = content

    return build_handoff_context(handoffs)


def _handoff_exists_local(repo_dir: Path, issue_iid: int) -> bool:
    return (repo_dir / handoff_path(issue_iid)).exists()


def _handoff_exists_sandbox(sandbox: DockerProjectSandbox, issue_iid: int) -> bool:
    try:
        sandbox.exec_shell(f"test -s {handoff_path(issue_iid)}", cwd="/workspace/repo", timeout=30)
        return True
    except Exception:
        return False


def _read_repo_file_local(repo_dir: Path, relative_path: str) -> str:
    path = _safe_repo_path(repo_dir, relative_path)
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_repo_file_sandbox(sandbox: DockerProjectSandbox, relative_path: str) -> str:
    safe_path = _safe_relative_path(relative_path)
    try:
        return sandbox.exec_shell(f"cat {safe_path}", cwd="/workspace/repo", timeout=30)
    except Exception:
        return ""


def _repo_file_exists_local(repo_dir: Path, relative_path: str) -> bool:
    path = _safe_repo_path(repo_dir, relative_path)
    return path.exists() and path.is_file()


def _repo_file_exists_sandbox(sandbox: DockerProjectSandbox, relative_path: str) -> bool:
    safe_path = _safe_relative_path(relative_path)
    try:
        sandbox.exec_shell(f"test -s {safe_path}", cwd="/workspace/repo", timeout=30)
        return True
    except Exception:
        return False


def _run_repo_command_local(repo_dir: Path, command: str) -> str:
    args = shlex.split(command)
    if not args:
        return ""
    return run(args, cwd=repo_dir, timeout=settings.job_timeout_seconds)


def _run_repo_command_sandbox(sandbox: DockerProjectSandbox, command: str) -> str:
    return sandbox.exec_shell(command, cwd="/workspace/repo", timeout=settings.job_timeout_seconds)


def _write_repo_file_local(repo_dir: Path, relative_path: str, content: str) -> None:
    path = _safe_repo_path(repo_dir, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")


def _write_repo_file_sandbox(sandbox: DockerProjectSandbox, relative_path: str, content: str) -> None:
    safe_path = _safe_relative_path(relative_path)
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    sandbox.exec_shell(f"mkdir -p \"$(dirname '{safe_path}')\" && printf '%s' '{encoded}' | base64 -d > '{safe_path}'", cwd="/workspace/repo", timeout=30)


def _changed_files_sandbox(sandbox: DockerProjectSandbox) -> list[str]:
    output = sandbox.exec(["git", "status", "--porcelain", "--untracked-files=all"], cwd="/workspace/repo", timeout=30)
    files: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        normalized = path.replace("\\", "/")
        if normalized and normalized not in files:
            files.append(normalized)
    return files


def _safe_repo_path(repo_dir: Path, relative_path: str) -> Path:
    safe_path = _safe_relative_path(relative_path)
    path = (repo_dir / safe_path).resolve()
    repo_root = repo_dir.resolve()
    if repo_root != path and repo_root not in path.parents:
        raise RuntimeError(f"Unsafe workflow artifact path: {relative_path}")
    return path


def _safe_relative_path(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized or normalized == "..":
        raise RuntimeError(f"Unsafe workflow artifact path: {relative_path}")
    if any(char in normalized for char in ("'", '"', "`", "$", "|", "&", ";", "<", ">")):
        raise RuntimeError(f"Unsafe workflow artifact path: {relative_path}")
    return normalized


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
    workflow = get_workflow(job.workflow_id)

    try:
        if cancel_file.exists():
            raise RuntimeError("Job was cancelled before start.")
        labels = _current_labels(client, job)
        client.update_issue_labels(job.project_id, job.issue_iid, workflow.running_labels(labels, job.trigger_label))
        client.add_issue_note(job.project_id, job.issue_iid, workflow.start_comment(job))

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
        handoff_context = _collect_handoff_context(job, store, sandbox, repo_dir)
        preflight = workflow.preflight(
            WorkflowPreflightContext(
                job=job,
                read_repo_file=(lambda path: _read_repo_file_sandbox(sandbox, path))
                if sandbox
                else (lambda path: _read_repo_file_local(repo_dir, path)),
                repo_file_exists=(lambda path: _repo_file_exists_sandbox(sandbox, path))
                if sandbox
                else (lambda path: _repo_file_exists_local(repo_dir, path)),
                run_repo_command=(lambda command: _run_repo_command_sandbox(sandbox, command))
                if sandbox
                else (lambda command: _run_repo_command_local(repo_dir, command)),
            )
        )
        if not preflight.passed:
            raise RuntimeError(preflight.summary)
        prompt = workflow.build_prompt(
            WorkflowContext(
                job=job,
                project_rules=project_rules,
                comments=comments,
                is_incremental=is_incremental,
                handoff_context=handoff_context,
                read_repo_file=(lambda path: _read_repo_file_sandbox(sandbox, path))
                if sandbox
                else (lambda path: _read_repo_file_local(repo_dir, path)),
            )
        )
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

        validation = workflow.validate(
            WorkflowValidationContext(
                job=job,
                read_repo_file=(lambda path: _read_repo_file_sandbox(sandbox, path))
                if sandbox
                else (lambda path: _read_repo_file_local(repo_dir, path)),
                repo_file_exists=(lambda path: _repo_file_exists_sandbox(sandbox, path))
                if sandbox
                else (lambda path: _repo_file_exists_local(repo_dir, path)),
                run_repo_command=(lambda command: _run_repo_command_sandbox(sandbox, command))
                if sandbox
                else (lambda command: _run_repo_command_local(repo_dir, command)),
                changed_files=(lambda: _changed_files_sandbox(sandbox)) if sandbox else (lambda: changed_files(repo_dir)),
            )
        )
        if not validation.passed:
            raise RuntimeError(validation.summary)
        if validation.report_path and validation.report_content is not None:
            if sandbox:
                _write_repo_file_sandbox(sandbox, validation.report_path, validation.report_content)
            else:
                _write_repo_file_local(repo_dir, validation.report_path, validation.report_content)

        checks = validation.summary
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
                f"This MR was generated by `{job.agent}` using workflow `{job.workflow_id}` based on issue #{job.issue_iid}.\n\n"
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
        client.update_issue_labels(job.project_id, job.issue_iid, workflow.success_labels(labels))
        client.add_issue_note(
            job.project_id,
            job.issue_iid,
            workflow.completion_comment(job, branch=branch, merge_request_iid=mr_iid, validation_summary=checks),
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
                client.update_issue_labels(job.project_id, job.issue_iid, workflow.cancelled_labels(labels))
            else:
                client.update_issue_labels(job.project_id, job.issue_iid, workflow.failure_labels(labels))
            client.add_issue_note(
                job.project_id,
                job.issue_iid,
                (
                    f"Agent job `{job.id}` cancelled.\n\nStage summary: `{type(exc).__name__}`\n\nError:\n```text\n{redact_sensitive_text(str(exc))[-3000:]}\n```"
                    if was_cancelled
                    else workflow.failure_comment(job, error_type=type(exc).__name__, error=redact_sensitive_text(str(exc)))
                ),
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
