from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .config import settings
from .db import JobStore
from .sandbox import issue_workspace, project_container_name, project_volume_name
from .webhook import extract_issue_job, newly_added_agent_label

app = FastAPI(title="GitLab Agent Orchestrator")
store = JobStore(settings.database_path)


class JobResponse(BaseModel):
    id: str
    status: str
    agent: str
    workflow_id: str
    workflow_task_id: str | None = None
    issue_iid: int
    branch: str | None = None
    merge_request_iid: int | None = None
    error: str | None = None


class SandboxResponse(BaseModel):
    project_id: int
    container_name: str
    image: str
    status: str
    bootstrap_version: str | None = None
    last_used_at: str | None = None
    error: str | None = None


class AgentLoginCommandResponse(BaseModel):
    project_id: int
    agent: str
    container_name: str
    powershell: str
    bash: str


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.post("/gitlab/webhook")
async def gitlab_webhook(request: Request, x_gitlab_token: str | None = Header(default=None)) -> dict[str, object]:
    if not settings.gitlab_webhook_secret:
        raise HTTPException(status_code=500, detail="GITLAB_WEBHOOK_SECRET is not configured")
    if x_gitlab_token != settings.gitlab_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid GitLab webhook token")

    payload = await request.json()
    trigger = newly_added_agent_label(payload, settings.agent_trigger_label)
    if not trigger:
        return {"ok": True, "triggered": False}

    trigger_label, agent = trigger
    data = extract_issue_job(payload, trigger_label, agent or settings.default_agent)
    job = store.create_job(**data)
    return {"ok": True, "triggered": True, "job_id": job.id, "status": job.status}


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(
        id=job.id,
        status=job.status,
        agent=job.agent,
        workflow_id=job.workflow_id,
        workflow_task_id=job.workflow_task_id,
        issue_iid=job.issue_iid,
        branch=job.branch,
        merge_request_iid=job.merge_request_iid,
        error=job.error,
    )


@app.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: str) -> JobResponse:
    existing = store.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="job not found")
    workspace = _issue_workspace(existing.project_id, existing.issue_iid)
    (workspace / f"{existing.id}.cancel").unlink(missing_ok=True)
    (workspace / f"{existing.id}.pid").unlink(missing_ok=True)
    job = store.retry(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(
        id=job.id,
        status=job.status,
        agent=job.agent,
        workflow_id=job.workflow_id,
        workflow_task_id=job.workflow_task_id,
        issue_iid=job.issue_iid,
        branch=job.branch,
        merge_request_iid=job.merge_request_iid,
        error=job.error,
    )


def _issue_workspace(project_id: int, issue_iid: int) -> Path:
    return issue_workspace(settings, project_id, issue_iid)


@app.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str) -> JobResponse:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    workspace = _issue_workspace(job.project_id, job.issue_iid)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / f"{job.id}.cancel").write_text("cancelled", encoding="utf-8")

    pid_file = workspace / f"{job.id}.pid"
    if pid_file.exists():
        pid_text = pid_file.read_text(encoding="utf-8", errors="replace").strip()
        if pid_text.isdigit():
            subprocess.run(["taskkill", "/PID", pid_text, "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    if job.status == "pending":
        store.mark_cancelled(job_id, error="cancelled before start")
    job = store.get_job(job_id)
    return JobResponse(
        id=job.id,
        status=job.status,
        agent=job.agent,
        workflow_id=job.workflow_id,
        workflow_task_id=job.workflow_task_id,
        issue_iid=job.issue_iid,
        branch=job.branch,
        merge_request_iid=job.merge_request_iid,
        error=job.error,
    )


@app.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
def get_job_log(job_id: str) -> str:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.log_path:
        workspace = _issue_workspace(job.project_id, job.issue_iid)
        log_dir = workspace / "logs"
        if log_dir.exists():
            logs = sorted(log_dir.glob(f"{job.id}.log"))
            if logs:
                return logs[-1].read_text(encoding="utf-8", errors="replace")
        return "No log is available yet."
    path = Path(job.log_path)
    if not path.exists():
        return "Log path is recorded but the file does not exist."
    return path.read_text(encoding="utf-8", errors="replace")


@app.get("/projects/{project_id}/sandbox", response_model=SandboxResponse)
def get_project_sandbox(project_id: int) -> SandboxResponse:
    row = store.get_sandbox(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="sandbox not found")
    return _sandbox_response(row)


@app.post("/projects/{project_id}/sandbox/restart", response_model=SandboxResponse)
def restart_project_sandbox(project_id: int) -> SandboxResponse:
    row = store.get_sandbox(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="sandbox not found")
    name = str(row["container_name"])
    _docker(["restart", name])
    store.update_sandbox(int(row["id"]), status="ready", error=None, touch_used=True)
    row = store.get_sandbox(project_id)
    return _sandbox_response(row)


@app.post("/projects/{project_id}/sandbox/stop", response_model=SandboxResponse)
def stop_project_sandbox(project_id: int) -> SandboxResponse:
    row = store.get_sandbox(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="sandbox not found")
    name = str(row["container_name"])
    _docker(["stop", name])
    store.update_sandbox(int(row["id"]), status="stopped", error=None)
    row = store.get_sandbox(project_id)
    return _sandbox_response(row)


@app.post("/projects/{project_id}/sandbox/rebuild", response_model=SandboxResponse)
def rebuild_project_sandbox(project_id: int) -> SandboxResponse:
    row = store.get_sandbox(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="sandbox not found")
    name = str(row["container_name"] or project_container_name(project_id))
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    subprocess.run(["docker", "volume", "rm", "-f", project_volume_name(project_id)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    store.update_sandbox(int(row["id"]), status="missing", bootstrap_version=None, error=None)
    row = store.get_sandbox(project_id)
    return _sandbox_response(row)


@app.get("/projects/{project_id}/sandbox/agents/{agent}/login-command", response_model=AgentLoginCommandResponse)
def get_agent_login_command(project_id: int, agent: str) -> AgentLoginCommandResponse:
    row = store.get_sandbox(project_id)
    container_name = str(row["container_name"]) if row else project_container_name(project_id)
    if agent == "codex":
        command = f"docker exec -it {container_name} codex login --device-auth"
    elif agent in {"gemini", "gemini-cli"}:
        command = f"docker exec -it {container_name} gemini"
    else:
        command = f"docker exec -it {container_name} {agent} login"
    return AgentLoginCommandResponse(
        project_id=project_id,
        agent=agent,
        container_name=container_name,
        powershell=command,
        bash=command,
    )


def _sandbox_response(row) -> SandboxResponse:
    return SandboxResponse(
        project_id=int(row["project_id"]),
        container_name=str(row["container_name"]),
        image=str(row["image"]),
        status=str(row["status"]),
        bootstrap_version=row["bootstrap_version"],
        last_used_at=row["last_used_at"],
        error=row["error"],
    )


def _docker(args: list[str]) -> str:
    proc = subprocess.run(
        ["docker", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=proc.stdout[-2000:])
    return proc.stdout
