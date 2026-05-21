from __future__ import annotations

import time
from typing import Any

from .config import settings
from .db import JobStore
from .gitlab_client import GitLabClient
from .workflows import extract_workflow_metadata


POLL_STATE_KEY_PREFIX = "auto_issue_poll_seeded:"
AUTO_TRIGGER_LABEL = "auto:issue-created"


def _issue_iid(issue: dict[str, Any]) -> int:
    iid = issue.get("iid")
    if iid is None:
        raise ValueError(f"GitLab issue is missing iid: {issue}")
    return int(iid)


def _project_id(issue: dict[str, Any]) -> int:
    project_id = issue.get("project_id")
    if project_id is None:
        raise ValueError(f"GitLab issue is missing project_id: {issue}")
    return int(project_id)


def _project_path(project: dict[str, Any]) -> str:
    return str(project.get("path_with_namespace") or project.get("name_with_namespace") or project.get("id"))


def _repo_http_url(project: dict[str, Any]) -> str:
    return str(project.get("http_url_to_repo") or project.get("web_url") or "")


def _default_branch(project: dict[str, Any]) -> str:
    return str(project.get("default_branch") or "main")


def poll_once(store: JobStore, client: GitLabClient) -> int:
    group_path = settings.auto_issue_group_path
    issues = client.list_group_open_issues(group_path)
    state_key = f"{POLL_STATE_KEY_PREFIX}{group_path}"

    if settings.auto_issue_seed_existing and store.get_poller_state(state_key) != "true":
        for issue in issues:
            store.mark_auto_issue_seen(
                project_id=_project_id(issue),
                issue_iid=_issue_iid(issue),
                issue_id=int(issue["id"]) if issue.get("id") is not None else None,
                project_path=str(issue.get("references", {}).get("full") or ""),
            )
        store.set_poller_state(state_key, "true")
        print(f"Seeded {len(issues)} existing open issue(s) for group {group_path}; no jobs queued.", flush=True)
        return 0

    queued = 0
    project_cache: dict[int, dict[str, Any]] = {}
    for issue in issues:
        project_id = _project_id(issue)
        issue_iid = _issue_iid(issue)
        if store.is_auto_issue_seen(project_id, issue_iid):
            continue

        project = project_cache.get(project_id)
        if project is None:
            project = client.get_project(project_id)
            project_cache[project_id] = project

        description = str(issue.get("description") or "")
        workflow = extract_workflow_metadata(description)
        job = store.create_job(
            project_id=project_id,
            project_path=_project_path(project),
            issue_iid=issue_iid,
            issue_title=str(issue.get("title") or f"Issue #{issue_iid}"),
            issue_description=description,
            trigger_label=AUTO_TRIGGER_LABEL,
            agent=settings.default_agent,
            repo_http_url=_repo_http_url(project),
            default_branch=_default_branch(project),
            workflow_id=workflow.workflow_id,
            workflow_task_id=workflow.workflow_task_id,
        )
        store.mark_auto_issue_seen(
            project_id=project_id,
            issue_iid=issue_iid,
            issue_id=int(issue["id"]) if issue.get("id") is not None else None,
            project_path=_project_path(project),
            job_id=job.id,
        )
        print(f"Queued {job.id} for {project_id}#{issue_iid} with {settings.default_agent}/{job.workflow_id}.", flush=True)
        queued += 1

    return queued


def main() -> None:
    if not settings.auto_issue_poll_enabled:
        print("AUTO_ISSUE_POLL_ENABLED is false; issue poller exiting.", flush=True)
        return
    store = JobStore(settings.database_path)
    client = GitLabClient(settings.gitlab_url, settings.gitlab_token)
    print(
        f"Auto issue poller started for group {settings.auto_issue_group_path}; "
        f"interval={settings.auto_issue_poll_interval_seconds}s agent={settings.default_agent}.",
        flush=True,
    )
    while True:
        try:
            poll_once(store, client)
        except Exception as exc:
            print(f"Auto issue poll failed: {exc}", flush=True)
        time.sleep(settings.auto_issue_poll_interval_seconds)


if __name__ == "__main__":
    main()
