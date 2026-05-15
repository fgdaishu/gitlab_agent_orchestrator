from __future__ import annotations

import re
import subprocess
from pathlib import Path


class CommandError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, output: str):
        safe_command = [part if "oauth2:" not in part else "<redacted-repo-url>" for part in command]
        super().__init__(f"Command failed ({returncode}): {' '.join(safe_command)}\n{output[-4000:]}")
        self.output = output


def run(command: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
    proc = subprocess.run(
        command,
        cwd=cwd,
        timeout=timeout,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise CommandError(command, proc.returncode, proc.stdout)
    return proc.stdout


def slugify(value: str, fallback: str = "task") -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or fallback)[:48].strip("-") or fallback


def clone_repo(repo_url: str, destination: Path, timeout: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", repo_url, str(destination)], timeout=timeout)


def prepare_issue_branch(repo_url: str, repo: Path, branch: str, base: str, timeout: int) -> None:
    if not (repo / ".git").exists():
        clone_repo(repo_url, repo, timeout)
    else:
        run(["git", "remote", "set-url", "origin", repo_url], cwd=repo)

    run(["git", "fetch", "origin", "--prune"], cwd=repo, timeout=timeout)
    current = run(["git", "branch", "--show-current"], cwd=repo).strip()
    if current == branch:
        return

    try:
        run(["git", "checkout", branch], cwd=repo)
        return
    except CommandError:
        pass

    try:
        run(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=repo)
        return
    except CommandError:
        pass

    run(["git", "checkout", "-B", branch, f"origin/{base}"], cwd=repo)


def has_changes(repo: Path) -> bool:
    status = run(["git", "status", "--porcelain"], cwd=repo)
    return bool(status.strip())


def current_head(repo: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=repo).strip()


def commit_all(repo: Path, message: str, author_name: str, author_email: str) -> None:
    run(["git", "config", "user.name", author_name], cwd=repo)
    run(["git", "config", "user.email", author_email], cwd=repo)
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)


def push_branch(repo: Path, branch: str, timeout: int) -> None:
    try:
        run(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=repo, timeout=timeout)
    except CommandError:
        run(["git", "fetch", "origin", branch], cwd=repo, timeout=timeout)
        run(["git", "pull", "--rebase", "origin", branch], cwd=repo, timeout=timeout)
        run(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=repo, timeout=timeout)
