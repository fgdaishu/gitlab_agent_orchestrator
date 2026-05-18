from __future__ import annotations

import re
import subprocess
from pathlib import Path


SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GITLAB_TOKEN",
    "PRIVATE_TOKEN",
)


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for name in SECRET_ENV_NAMES:
        redacted = re.sub(rf"({name}=)[^\s]+", rf"\1<redacted>", redacted)
    redacted = re.sub(r"oauth2:[^@\s]+@", "oauth2:<redacted>@", redacted)
    redacted = re.sub(r"glpat-[A-Za-z0-9_.-]+", "glpat-<redacted>", redacted)
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "sk-<redacted>", redacted)
    return redacted


def _safe_command_part(part: str) -> str:
    return redact_sensitive_text(part)


class CommandError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, output: str):
        safe_command = [_safe_command_part(part) for part in command]
        safe_output = redact_sensitive_text(output[-4000:])
        super().__init__(f"Command failed ({returncode}): {' '.join(safe_command)}\n{safe_output}")
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


def prepare_issue_branch(
    repo_url: str,
    repo: Path,
    branch: str,
    base: str,
    timeout: int,
    author_name: str = "agent-bot",
    author_email: str = "agent-bot@example.local",
) -> None:
    if not (repo / ".git").exists():
        clone_repo(repo_url, repo, timeout)
    else:
        run(["git", "remote", "set-url", "origin", repo_url], cwd=repo)

    run(["git", "fetch", "origin", "--prune"], cwd=repo, timeout=timeout)
    ensure_remote_base_branch(repo, base, timeout, author_name, author_email)
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


def ensure_remote_base_branch(repo: Path, base: str, timeout: int, author_name: str, author_email: str) -> None:
    if ref_exists(repo, f"origin/{base}"):
        return

    current = run(["git", "branch", "--show-current"], cwd=repo).strip()
    worktree_state = run(["git", "status", "--porcelain"], cwd=repo)
    if worktree_state.strip():
        run(["git", "reset", "--hard"], cwd=repo, timeout=timeout)
        run(["git", "clean", "-fd"], cwd=repo, timeout=timeout)

    run(["git", "checkout", "--orphan", base], cwd=repo, timeout=timeout)
    try:
        run(["git", "rm", "-rf", "."], cwd=repo, timeout=timeout)
    except CommandError:
        pass
    run(["git", "config", "user.name", author_name], cwd=repo, timeout=timeout)
    run(["git", "config", "user.email", author_email], cwd=repo, timeout=timeout)
    run(["git", "commit", "--allow-empty", "-m", f"chore: initialize {base} branch"], cwd=repo, timeout=timeout)
    run(["git", "push", "-u", "origin", f"HEAD:{base}"], cwd=repo, timeout=timeout)
    if current and current != base:
        try:
            run(["git", "checkout", current], cwd=repo, timeout=timeout)
        except CommandError:
            pass


def ref_exists(repo: Path, ref: str) -> bool:
    try:
        run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo)
        return True
    except CommandError:
        return False


def remote_base_ref(repo: Path, base: str) -> str | None:
    candidates = [f"origin/{base}"]
    try:
        head = run(["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd=repo).strip()
        if head:
            candidates.append(head)
    except CommandError:
        pass

    for candidate in candidates:
        try:
            run(["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"], cwd=repo)
            return candidate
        except CommandError:
            pass

    try:
        refs = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"], cwd=repo)
    except CommandError:
        return None
    for ref in refs.splitlines():
        ref = ref.strip()
        if ref and ref != "origin/HEAD":
            return ref
    return None


def has_changes(repo: Path) -> bool:
    status = run(["git", "status", "--porcelain"], cwd=repo)
    return bool(status.strip())


def current_head(repo: Path) -> str:
    try:
        return run(["git", "rev-parse", "HEAD"], cwd=repo).strip()
    except CommandError:
        return ""


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
