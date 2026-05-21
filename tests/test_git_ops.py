from pathlib import Path

from orchestrator.git_ops import CommandError, changed_files, current_head, prepare_issue_branch, redact_sensitive_text, run


def git(command: list[str], cwd: Path) -> str:
    return run(["git", *command], cwd=cwd)


def test_prepare_issue_branch_uses_orphan_branch_for_empty_remote(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(["init", "--bare", str(remote)], tmp_path)

    prepare_issue_branch(str(remote), repo, "agent/issue-1-test", "main", timeout=30)

    assert git(["branch", "--show-current"], repo).strip() == "agent/issue-1-test"
    assert current_head(repo) != ""


def test_prepare_issue_branch_falls_back_to_existing_remote_branch(tmp_path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    repo = tmp_path / "repo"
    git(["init", "--bare", str(remote)], tmp_path)
    git(["init", str(seed)], tmp_path)
    git(["config", "user.name", "Test"], seed)
    git(["config", "user.email", "test@example.local"], seed)
    (seed / "README.md").write_text("hello\n", encoding="utf-8")
    git(["add", "README.md"], seed)
    git(["commit", "-m", "init"], seed)
    git(["branch", "-M", "master"], seed)
    git(["remote", "add", "origin", str(remote)], seed)
    git(["push", "-u", "origin", "master"], seed)

    prepare_issue_branch(str(remote), repo, "agent/issue-1-test", "main", timeout=30)

    assert git(["branch", "--show-current"], repo).strip() == "agent/issue-1-test"
    assert current_head(repo) != ""


def test_command_error_redacts_secrets():
    exc = CommandError(
        ["docker", "exec", "-e", "OPENAI_API_KEY=sk-proj-secretvalue", "container"],
        128,
        "token glpat-secret and OPENAI_API_KEY=sk-proj-secretvalue",
    )

    text = str(exc)
    assert "sk-proj-secretvalue" not in text
    assert "glpat-secret" not in text
    assert "OPENAI_API_KEY=<redacted>" in text
    assert redact_sensitive_text("GEMINI_API_KEY=abc123") == "GEMINI_API_KEY=<redacted>"


def test_changed_files_includes_modified_and_untracked(tmp_path):
    repo = tmp_path / "repo"
    git(["init", str(repo)], tmp_path)
    git(["config", "user.name", "Test"], repo)
    git(["config", "user.email", "test@example.local"], repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    git(["add", "README.md"], repo)
    git(["commit", "-m", "init"], repo)

    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    assert changed_files(repo) == ["README.md", "new.txt"]
