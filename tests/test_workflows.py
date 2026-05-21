from orchestrator.models import Job
from orchestrator.workflows import extract_workflow_metadata
from orchestrator.workflows.base import WorkflowContext, WorkflowPreflightContext, WorkflowValidationContext
from orchestrator.workflows.registry import get_workflow
from orchestrator.workflows.strict_development.validation import has_field_content, parse_list_field, parse_scalar_field, parse_validation_commands


def _job(**overrides):
    values = {
        "id": "job_test",
        "project_id": 1,
        "project_path": "group/project",
        "issue_iid": 2,
        "issue_title": "[PNG-CHUNK-001] Implement chunk reader",
        "issue_description": "Workflow: strict_development\nTask-ID: PNG-CHUNK-001",
        "trigger_type": "label_added",
        "trigger_label": "auto:issue-created",
        "agent": "opencode",
        "workflow_id": "strict_development",
        "workflow_task_id": "PNG-CHUNK-001",
        "status": "pending",
        "repo_http_url": "http://gitlab.example/group/project.git",
        "default_branch": "main",
        "branch": None,
        "merge_request_iid": None,
        "created_at": "now",
        "started_at": None,
        "finished_at": None,
        "error": None,
        "log_path": None,
    }
    values.update(overrides)
    return Job(**values)


def _valid_task_card(task_id: str = "PNG-CHUNK-001") -> str:
    return f"""task_id: {task_id}
title: Implement safe PNG chunk reader
module: PNG-CHUNK
objective: Ensure PNG chunk field parsing is implemented safely and covered by tests.
must_follow:
  - no unsafe code
files_allowed:
  - Cargo.lock
  - src/chunk.rs
  - tests/chunk.rs
  - .agent/handoffs/
  - reports/
forbidden_files:
  - memory_safe_strict_development_based_on_gao_prd.md
validation_commands:
  - cargo test --test chunk
handoff_required:
  - implementation summary
relevant_contracts:
  - contracts/png_chunk.yaml
"""


def test_extract_workflow_metadata_accepts_strict_alias():
    meta = extract_workflow_metadata("## Agent Metadata\n\nWorkflow: strict\nTask-ID: PNG-CHUNK-001\n")
    assert meta.workflow_id == "strict_development"
    assert meta.workflow_task_id == "PNG-CHUNK-001"


def test_unknown_workflow_falls_back_to_default():
    meta = extract_workflow_metadata("Workflow: unknown\nTask-ID: SOME-TASK\n")
    assert meta.workflow_id == "default_coding"
    assert meta.workflow_task_id == "SOME-TASK"


def test_default_coding_workflow_builds_general_prompt():
    job = _job(
        workflow_id="default_coding",
        workflow_task_id=None,
        issue_title="Add validation",
        issue_description="Implement this and run tests.",
    )
    prompt = get_workflow(job.workflow_id).build_prompt(
        WorkflowContext(
            job=job,
            project_rules="",
            comments=[],
            is_incremental=False,
            handoff_context="",
            read_repo_file=lambda path: "",
        )
    )
    assert "Implement the following GitLab issue now" in prompt
    assert "explicitly asks for testing" in prompt
    assert ".agent/handoffs/issue-2.md" in prompt


def test_default_coding_validation_requires_handoff():
    job = _job(workflow_id="default_coding", workflow_task_id=None)
    result = get_workflow(job.workflow_id).validate(
        WorkflowValidationContext(
            job=job,
            read_repo_file=lambda path: "",
            repo_file_exists=lambda path: False,
            run_repo_command=lambda command: "",
            changed_files=lambda: [],
        )
    )
    assert not result.passed
    assert ".agent/handoffs/issue-2.md" in result.summary


def test_default_coding_labels_and_comments_match_legacy_flow():
    job = _job(workflow_id="default_coding", workflow_task_id=None)
    workflow = get_workflow(job.workflow_id)
    assert workflow.running_labels(["agent:opencode", "bug"], "agent:opencode") == ["bug", "agent:running"]
    assert workflow.success_labels(["bug", "agent:running"]) == ["bug", "agent:review"]
    assert workflow.failure_labels(["bug", "agent:running"]) == ["bug", "agent:failed"]
    assert workflow.cancelled_labels(["bug", "agent:running"]) == ["bug"]
    assert "Agent job `job_test` started" in workflow.start_comment(job)
    assert "MR: !7" in workflow.completion_comment(job, branch="agent/test", merge_request_iid=7, validation_summary="checks ok")


def test_strict_development_prompt_loads_task_card_and_context_pack():
    job = _job()
    files = {
        "task-cards/PNG-CHUNK-001.yaml": "task_id: PNG-CHUNK-001\nfiles_allowed:\n  - src/chunk.rs\n",
        "context-packs/PNG-CHUNK-001.md": "# Context Pack\nImplement safe chunk reader.\n",
    }
    prompt = get_workflow(job.workflow_id).build_prompt(
        WorkflowContext(
            job=job,
            project_rules="",
            comments=[],
            is_incremental=False,
            handoff_context="",
            read_repo_file=lambda path: files.get(path, ""),
        )
    )
    assert "Workflow: strict_development" in prompt
    assert "task_id: PNG-CHUNK-001" in prompt
    assert "# Context Pack" in prompt
    assert ".agent/handoffs/issue-2.md" in prompt


def test_parse_validation_commands_from_task_card():
    task_card = """
task_id: PNG-CHUNK-001
validation_commands:
  - python -m pytest tests/test_chunk.py
  - cargo test chunk
files_allowed:
  - src/chunk.rs
"""
    assert parse_validation_commands(task_card) == [
        "python -m pytest tests/test_chunk.py",
        "cargo test chunk",
    ]
    assert parse_list_field(task_card, ("files_allowed",)) == ["src/chunk.rs"]
    assert parse_scalar_field(task_card, "task_id") == "PNG-CHUNK-001"
    assert has_field_content("objective:\n  Ensure safe parsing.\n", "objective")


def test_strict_development_preflight_passes_valid_task_card():
    job = _job()
    files = {
        "task-cards/PNG-CHUNK-001.yaml": _valid_task_card(),
        "context-packs/PNG-CHUNK-001.md": "# Context Pack\nImplement safe chunk reader.\n",
        "Cargo.toml": "[package]\nname = \"demo\"\n",
        "contracts/png_chunk.yaml": "name: chunk\n",
    }
    commands: list[str] = []
    result = get_workflow(job.workflow_id).preflight(
        WorkflowPreflightContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path in files,
            run_repo_command=lambda command: commands.append(command) or "ok",
        )
    )
    assert result.passed
    assert "PNG-CHUNK-001" in result.summary
    assert "cargo --version" in commands
    assert "opencode --version" in commands


def test_strict_development_preflight_rejects_task_id_mismatch():
    job = _job()
    files = {
        "task-cards/PNG-CHUNK-001.yaml": _valid_task_card("OTHER-TASK"),
        "context-packs/PNG-CHUNK-001.md": "# Context Pack\n",
        "Cargo.toml": "[package]\nname = \"demo\"\n",
        "contracts/png_chunk.yaml": "name: chunk\n",
    }
    result = get_workflow(job.workflow_id).preflight(
        WorkflowPreflightContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path in files,
            run_repo_command=lambda command: "ok",
        )
    )
    assert not result.passed
    assert "must match issue Task-ID" in result.summary


def test_strict_development_preflight_requires_context_pack():
    job = _job()
    files = {
        "task-cards/PNG-CHUNK-001.yaml": _valid_task_card(),
        "Cargo.toml": "[package]\nname = \"demo\"\n",
        "contracts/png_chunk.yaml": "name: chunk\n",
    }
    result = get_workflow(job.workflow_id).preflight(
        WorkflowPreflightContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path in files,
            run_repo_command=lambda command: "ok",
        )
    )
    assert not result.passed
    assert "context pack not found" in result.summary


def test_strict_development_preflight_requires_cargo_lock_for_rust_tasks():
    job = _job()
    task_card = _valid_task_card().replace("  - Cargo.lock\n", "")
    files = {
        "task-cards/PNG-CHUNK-001.yaml": task_card,
        "context-packs/PNG-CHUNK-001.md": "# Context Pack\n",
        "Cargo.toml": "[package]\nname = \"demo\"\n",
        "contracts/png_chunk.yaml": "name: chunk\n",
    }
    result = get_workflow(job.workflow_id).preflight(
        WorkflowPreflightContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path in files,
            run_repo_command=lambda command: "ok",
        )
    )
    assert not result.passed
    assert "Cargo.lock" in result.summary


def test_strict_development_preflight_reports_missing_tools():
    job = _job()
    files = {
        "task-cards/PNG-CHUNK-001.yaml": _valid_task_card(),
        "context-packs/PNG-CHUNK-001.md": "# Context Pack\n",
        "Cargo.toml": "[package]\nname = \"demo\"\n",
        "contracts/png_chunk.yaml": "name: chunk\n",
    }

    def run_command(command: str) -> str:
        if command == "cargo --version":
            raise RuntimeError("cargo not found")
        return "ok"

    result = get_workflow(job.workflow_id).preflight(
        WorkflowPreflightContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path in files,
            run_repo_command=run_command,
        )
    )
    assert not result.passed
    assert "required tool `cargo`" in result.summary


def test_strict_development_preflight_rejects_unknown_validation_tool():
    job = _job()
    task_card = _valid_task_card().replace("cargo test --test chunk", "nonexistent-tool --version")
    files = {
        "task-cards/PNG-CHUNK-001.yaml": task_card,
        "context-packs/PNG-CHUNK-001.md": "# Context Pack\n",
        "Cargo.toml": "[package]\nname = \"demo\"\n",
        "contracts/png_chunk.yaml": "name: chunk\n",
    }
    result = get_workflow(job.workflow_id).preflight(
        WorkflowPreflightContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path in files,
            run_repo_command=lambda command: "ok",
        )
    )
    assert not result.passed
    assert "required tool `nonexistent-tool` is not recognized" in result.summary


def test_strict_development_validation_runs_declared_commands():
    job = _job()
    files = {
        "task-cards/PNG-CHUNK-001.yaml": "task_id: PNG-CHUNK-001\nvalidation_commands:\n  - python -m pytest tests/test_chunk.py\n",
    }
    commands: list[str] = []
    result = get_workflow(job.workflow_id).validate(
        WorkflowValidationContext(
            job=job,
            read_repo_file=lambda path: files.get(path, ""),
            repo_file_exists=lambda path: path == ".agent/handoffs/issue-2.md",
            run_repo_command=lambda command: commands.append(command) or "passed",
            changed_files=lambda: ["src/chunk.rs"],
        )
    )
    assert result.passed
    assert commands == ["python -m pytest tests/test_chunk.py"]
    assert "strict_development validation passed" in result.summary
    assert result.report_path == "reports/PNG-CHUNK-001-validation.md"
    assert result.report_content is not None
    assert "# Validation Report: PNG-CHUNK-001" in result.report_content
    assert "python -m pytest tests/test_chunk.py" in result.report_content


def test_strict_development_validation_fails_without_handoff():
    job = _job()
    result = get_workflow(job.workflow_id).validate(
        WorkflowValidationContext(
            job=job,
            read_repo_file=lambda path: "task_id: PNG-CHUNK-001\n",
            repo_file_exists=lambda path: False,
            run_repo_command=lambda command: "",
            changed_files=lambda: [],
        )
    )
    assert not result.passed
    assert ".agent/handoffs/issue-2.md" in result.summary


def test_strict_development_validation_rejects_changes_outside_allowed_files():
    job = _job()
    result = get_workflow(job.workflow_id).validate(
        WorkflowValidationContext(
            job=job,
            read_repo_file=lambda path: "task_id: PNG-CHUNK-001\nfiles_allowed:\n  - src/chunk.rs\n",
            repo_file_exists=lambda path: path == ".agent/handoffs/issue-2.md",
            run_repo_command=lambda command: "",
            changed_files=lambda: ["src/chunk.rs", "src/decoder.rs"],
        )
    )
    assert not result.passed
    assert "outside `files_allowed`" in result.summary
    assert "src/decoder.rs" in result.summary


def test_strict_development_validation_rejects_forbidden_files():
    job = _job()
    result = get_workflow(job.workflow_id).validate(
        WorkflowValidationContext(
            job=job,
            read_repo_file=lambda path: "task_id: PNG-CHUNK-001\nforbidden_files:\n  - src/legacy/\n",
            repo_file_exists=lambda path: path == ".agent/handoffs/issue-2.md",
            run_repo_command=lambda command: "",
            changed_files=lambda: ["src/legacy/parser.c"],
        )
    )
    assert not result.passed
    assert "forbidden files" in result.summary
    assert "src/legacy/parser.c" in result.summary


def test_strict_development_labels_and_comments_use_strict_statuses():
    job = _job()
    workflow = get_workflow(job.workflow_id)
    assert workflow.running_labels(["agent:opencode", "strict:ready", "bug"], "agent:opencode") == ["bug", "strict:running"]
    assert workflow.success_labels(["bug", "strict:running"]) == ["bug", "strict:review"]
    assert workflow.failure_labels(["bug", "strict:running"]) == ["bug", "strict:validation-failed"]
    assert workflow.cancelled_labels(["bug", "strict:running", "agent:running"]) == ["bug"]
    assert "Task ID: `PNG-CHUNK-001`" in workflow.start_comment(job)
    comment = workflow.completion_comment(job, branch="agent/test", merge_request_iid=9, validation_summary="strict_development validation passed")
    assert "Strict Development job `job_test` completed" in comment
    assert "task-cards/PNG-CHUNK-001.yaml" in comment
    assert "reports/PNG-CHUNK-001-validation.md" in comment
    assert "MR: !9" in comment

