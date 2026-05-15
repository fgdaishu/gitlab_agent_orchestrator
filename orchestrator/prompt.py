from __future__ import annotations

from pathlib import Path

from .models import Job

RULE_FILES = ("AGENTS.md", "CODEX.md", "CONTRIBUTING.md")


def read_project_rules(repo: Path) -> str:
    for name in RULE_FILES:
        path = repo / name
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:12000]
    return ""


def build_prompt(job: Job, project_rules: str, comments: list[str] | None = None, is_incremental: bool = False) -> str:
    rules_block = f"\nProject rules from repository:\n{project_rules}\n" if project_rules else ""
    comment_block = ""
    if comments:
        comment_block = "\nIssue comments, oldest to newest:\n" + "\n\n".join(f"- {comment}" for comment in comments[-20:]) + "\n"
    mode = "This issue already has an agent branch. Continue from the current branch state and implement only the new or still-missing requested changes." if is_incremental else "This is the first agent pass for this issue."
    return f"""Implement the following GitLab issue now. Modify the repository files directly in the current working directory.

Task source:
- Project: {job.project_path}
- Issue: #{job.issue_iid}
- Title: {job.issue_title}

Issue description:
{job.issue_description}
{comment_block}
{rules_block}
Execution mode:
{mode}

Rules:
- Do not modify unrelated files.
- Treat newer issue comments as incremental instructions or clarifications.
- Do not edit the GitLab issue description; report progress by adding comments only.
- Do not run git commit.
- Do not run git push.
- Leave all file changes unstaged or staged for the orchestrator to commit and push.
- Do not commit secrets.
- Prefer small, reviewable changes.
- Run available tests if possible.
- If the task is ambiguous, make the smallest reasonable implementation and document assumptions.
- Do not push directly to main/master.

Expected output:
- Implement the requested change.
- Add or update tests when appropriate.
- Provide a concise summary of changes.
"""
