from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


BLOCKED_INHERITED_ENV = {
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CODEX_THREAD_ID",
}


@dataclass
class AgentResult:
    output: str


class AgentAdapter:
    def run(self, repo: Path, prompt: str, timeout: int, cancel_file: Path | None = None, pid_file: Path | None = None) -> AgentResult:
        raise NotImplementedError


def _agent_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in BLOCKED_INHERITED_ENV:
        env.pop(key, None)
        env.pop(key.lower(), None)
    env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    return env


class CliAgentAdapter(AgentAdapter):
    def __init__(self, command: list[str]):
        self.command = command

    def run(self, repo: Path, prompt: str, timeout: int, cancel_file: Path | None = None, pid_file: Path | None = None) -> AgentResult:
        return _run_with_live_log([*self.command, prompt], repo, timeout, cancel_file, pid_file)


class PromptFileAgentAdapter(AgentAdapter):
    def __init__(self, command: list[str], prompt_file_name: str = "agent-prompt.md"):
        self.command = command
        self.prompt_file_name = prompt_file_name

    def run(self, repo: Path, prompt: str, timeout: int, cancel_file: Path | None = None, pid_file: Path | None = None) -> AgentResult:
        prompt_file = (repo / ".git" / self.prompt_file_name).resolve()
        prompt_file.write_text(prompt, encoding="utf-8", errors="replace")
        return _run_with_live_log([*self.command, str(prompt_file)], repo, timeout, cancel_file, pid_file)


class StdinAgentAdapter(AgentAdapter):
    def __init__(self, command: list[str]):
        self.command = command

    def run(self, repo: Path, prompt: str, timeout: int, cancel_file: Path | None = None, pid_file: Path | None = None) -> AgentResult:
        output_path = repo / ".git" / "agent-output.log"
        with output_path.open("w", encoding="utf-8", errors="replace") as output_file:
            proc = subprocess.Popen(
                self.command,
                cwd=repo,
                env=_agent_env(),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.PIPE,
                stdout=output_file,
                stderr=subprocess.STDOUT,
            )
            if pid_file:
                pid_file.write_text(str(proc.pid), encoding="utf-8")
            if proc.stdin:
                proc.stdin.write(prompt)
                proc.stdin.close()
            _wait_for_process(proc, timeout, cancel_file)

        output = output_path.read_text(encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"Agent command failed ({proc.returncode}):\n{output[-4000:]}")
        return AgentResult(output=output)


def _run_with_live_log(
    command: list[str],
    repo: Path,
    timeout: int,
    cancel_file: Path | None,
    pid_file: Path | None,
) -> AgentResult:
    output_path = repo / ".git" / "agent-output.log"
    with output_path.open("w", encoding="utf-8", errors="replace") as output_file:
        proc = subprocess.Popen(
            command,
            cwd=repo,
            env=_agent_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=output_file,
            stderr=subprocess.STDOUT,
        )
        if pid_file:
            pid_file.write_text(str(proc.pid), encoding="utf-8")
        _wait_for_process(proc, timeout, cancel_file)

    output = output_path.read_text(encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Agent command failed ({proc.returncode}):\n{output[-4000:]}")
    return AgentResult(output=output)


def _wait_for_process(proc: subprocess.Popen[str], timeout: int, cancel_file: Path | None) -> None:
    started = time.monotonic()
    while proc.poll() is None:
        if cancel_file and cancel_file.exists():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise RuntimeError("Agent command cancelled.")
        if time.monotonic() - started > timeout:
            proc.kill()
            proc.wait()
            raise RuntimeError(f"Agent command timed out after {timeout} seconds.")
        time.sleep(1)
    if cancel_file and cancel_file.exists():
        raise RuntimeError("Agent command cancelled.")


class OpenCodeAdapter(AgentAdapter):
    def __init__(self, command: str):
        self.command = command

    def run(self, repo: Path, prompt: str, timeout: int, cancel_file: Path | None = None, pid_file: Path | None = None) -> AgentResult:
        prompt_file = (repo / ".git" / "agent-prompt.md").resolve()
        prompt_file.write_text(prompt, encoding="utf-8", errors="replace")
        return _run_with_live_log(
            [
                self.command,
                "run",
                "--dangerously-skip-permissions",
                "Read the attached prompt and implement the requested code changes in this repository.",
                "--file",
                str(prompt_file),
            ],
            repo,
            timeout,
            cancel_file,
            pid_file,
        )


def adapter_for(agent: str, settings: Settings) -> AgentAdapter:
    if agent == "opencode":
        return OpenCodeAdapter(settings.opencode_command)
    if agent == "codex":
        return StdinAgentAdapter([
            settings.codex_command,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "-",
        ])
    if agent == "gemini-cli":
        return CliAgentAdapter([settings.gemini_command, "--yolo", "--prompt"])
    raise ValueError(f"Unsupported agent for MVP: {agent}")
