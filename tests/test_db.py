from orchestrator.db import JobStore


def create_job(store: JobStore):
    return create_job_for_issue(store, issue_iid=2)


def create_job_for_issue(store: JobStore, issue_iid: int, project_id: int = 1):
    return store.create_job(
        project_id=project_id,
        project_path="group/project",
        issue_iid=issue_iid,
        issue_title="Title",
        issue_description="Body",
        trigger_label="agent:opencode",
        agent="opencode",
        repo_http_url="http://gitlab.example/group/project.git",
        default_branch="main",
    )


def test_create_and_claim_job(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    job = create_job(store)
    assert job.status == "pending"
    assert job.workflow_id == "default_coding"
    assert job.workflow_task_id is None

    claimed = store.claim_next()
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "running"


def test_dedupes_pending_job(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    first = create_job(store)
    second = create_job(store)
    assert second.id == first.id


def test_claim_skips_project_with_running_job(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    first = create_job_for_issue(store, issue_iid=2, project_id=1)
    second = create_job_for_issue(store, issue_iid=3, project_id=1)
    third = create_job_for_issue(store, issue_iid=4, project_id=2)

    claimed = store.claim_next()
    assert claimed.id == first.id
    claimed = store.claim_next()
    assert claimed.id == third.id
    assert claimed.id != second.id


def test_sandbox_record_and_workspace_attachment(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    job = create_job(store)
    sandbox = store.get_or_create_sandbox(
        project_id=job.project_id,
        project_path=job.project_path,
        container_name="gitlab-agent-project-1",
        image="gitlab-agent-sandbox:latest",
    )
    store.attach_workspace(job.id, sandbox_id=sandbox["id"], workspace_path="workspaces/project-1/issues/issue-2")
    reloaded = store.get_job(job.id)
    assert reloaded.sandbox_id == sandbox["id"]
    assert reloaded.workspace_path.endswith("issue-2")
