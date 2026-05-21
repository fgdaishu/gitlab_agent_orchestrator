from tests.test_db import create_job_for_issue

from orchestrator.prompt import build_prompt


def test_prompt_does_not_request_tests_by_default(tmp_path):
    from orchestrator.db import JobStore

    store = JobStore(tmp_path / "jobs.sqlite3")
    job = create_job_for_issue(store, issue_iid=1)

    prompt = build_prompt(job, project_rules="")

    assert "did not explicitly ask for testing" in prompt


def test_prompt_requests_tests_when_issue_asks(tmp_path):
    from orchestrator.db import JobStore

    store = JobStore(tmp_path / "jobs.sqlite3")
    job = store.create_job(
        project_id=1,
        project_path="group/project",
        issue_iid=2,
        issue_title="Add calculator",
        issue_description="Implement this and run tests.",
        trigger_label="agent:opencode",
        agent="opencode",
        repo_http_url="http://gitlab.example/group/project.git",
        default_branch="main",
    )

    prompt = build_prompt(job, project_rules="")

    assert "explicitly asks for testing" in prompt


def test_prompt_includes_handoff_instructions_and_context(tmp_path):
    from orchestrator.db import JobStore

    store = JobStore(tmp_path / "jobs.sqlite3")
    job = create_job_for_issue(store, issue_iid=3)

    prompt = build_prompt(job, project_rules="", handoff_context="## Handoff from issue #2\n\nUse the new API.")

    assert ".agent/handoffs/issue-3.md" in prompt
    assert "Dependency handoff context" in prompt
    assert "Use the new API." in prompt
