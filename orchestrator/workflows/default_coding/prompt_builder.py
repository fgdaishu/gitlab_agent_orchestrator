from __future__ import annotations

from pathlib import Path

from ...models import Job

RULE_FILES = ("AGENTS.md", "CODEX.md", "CONTRIBUTING.md")
TEST_REQUEST_KEYWORDS = (
    "test",
    "tests",
    "testing",
    "pytest",
    "jest",
    "npm test",
    "unit test",
    "测试",
    "单测",
    "跑测试",
    "验证",
    "编译并测试",
)


def read_project_rules(repo: Path) -> str:
    for name in RULE_FILES:
        path = repo / name
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")[:12000]
    return ""


def build_default_prompt(
    job: Job,
    project_rules: str,
    comments: list[str] | None = None,
    is_incremental: bool = False,
    handoff_context: str = "",
) -> str:
    rules_block = f"\nProject rules from repository:\n{project_rules}\n" if project_rules else ""
    comment_block = ""
    if comments:
        comment_block = "\nIssue comments, oldest to newest:\n" + "\n\n".join(f"- {comment}" for comment in comments[-20:]) + "\n"
    handoff_block = f"\nDependency handoff context:\n{handoff_context}\n" if handoff_context else ""
    mode = "This issue already has an agent branch. Continue from the current branch state and implement only the new or still-missing requested changes." if is_incremental else "This is the first agent pass for this issue."
    requested_text = "\n".join([job.issue_title, job.issue_description, *(comments or [])]).lower()
    should_test = any(keyword in requested_text for keyword in TEST_REQUEST_KEYWORDS)
    test_instruction = (
        "- The issue explicitly asks for testing or verification. Run the relevant tests/build/checks if practical, and fix failures caused by your changes."
        if should_test
        else "- Do not run broad test suites unless needed for your implementation; the issue did not explicitly ask for testing."
    )
    return f"""Implement the following GitLab issue now. Modify the repository files directly in the current working directory.

Task source:
- Project: {job.project_path}
- Issue: #{job.issue_iid}
- Title: {job.issue_title}

Issue description:
{job.issue_description}
{comment_block}
{handoff_block}
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
- Maintain a structured handoff document at `.agent/handoffs/issue-{job.issue_iid}.md`.
- The handoff must be concise and include: Summary, Changed Files, Decisions, Interfaces / Contracts, Follow-up Needed, Test Notes, and Context For Next Issues.
{test_instruction}
- If the task is ambiguous, make the smallest reasonable implementation and document assumptions.
- Do not push directly to main/master.

Expected output:
- Implement the requested change.
- Add or update tests when appropriate.
- Add or update `.agent/handoffs/issue-{job.issue_iid}.md`.
- Provide a concise summary of changes.
"""
