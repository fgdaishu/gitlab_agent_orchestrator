from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .agent import AgentResult, BLOCKED_INHERITED_ENV
from .config import Settings
from .db import JobStore
from .git_ops import CommandError
from .models import Job


CONTAINER_WORKSPACE = "/workspace"
CONTAINER_REPO = f"{CONTAINER_WORKSPACE}/repo"


@dataclass(frozen=True)
class ProjectSandbox:
    id: int
    project_id: int
    container_name: str
    image: str
    host_workspace: Path
    volume_name: str


def project_container_name(project_id: int) -> str:
    return f"gitlab-agent-project-{project_id}"


def project_volume_name(project_id: int) -> str:
    return f"gitlab-agent-project-{project_id}-workspace"


def project_workspace(settings: Settings, project_id: int) -> Path:
    return settings.workspace_root / f"project-{project_id}"


def issue_workspace(settings: Settings, project_id: int, issue_iid: int) -> Path:
    if settings.agent_execution_backend == "docker_project":
        return project_workspace(settings, project_id) / "issues" / f"issue-{issue_iid}"
    return settings.workspace_root / f"project-{project_id}" / f"issue-{issue_iid}"


class DockerProjectSandbox:
    def __init__(self, settings: Settings, store: JobStore, job: Job):
        self.settings = settings
        self.store = store
        self.job = job
        self.host_workspace = project_workspace(settings, job.project_id).resolve()
        self.container_name = project_container_name(job.project_id)
        self.volume_name = project_volume_name(job.project_id)

    def ensure(self) -> ProjectSandbox:
        self.host_workspace.mkdir(parents=True, exist_ok=True)
        row = self.store.get_or_create_sandbox(
            project_id=self.job.project_id,
            project_path=self.job.project_path,
            container_name=self.container_name,
            image=self.settings.sandbox_docker_image,
        )
        sandbox_id = int(row["id"])
        try:
            self.store.update_sandbox(sandbox_id, status="creating", touch_used=True)
            if not self._container_exists():
                self._create_container()
            if not self._container_running():
                self._docker(["start", self.container_name], timeout=60)

            current_version = self._read_bootstrap_version()
            if current_version != self.settings.sandbox_bootstrap_version:
                self.store.update_sandbox(sandbox_id, status="bootstrapping", touch_used=True)
                self.exec_shell(self.settings.sandbox_bootstrap_command, cwd=CONTAINER_WORKSPACE, timeout=self.settings.job_timeout_seconds)
                self.exec_shell(
                    f"printf %s {shlex.quote(self.settings.sandbox_bootstrap_version)} > .sandbox-bootstrap-version",
                    cwd=CONTAINER_WORKSPACE,
                    timeout=30,
                )

            self.store.update_sandbox(
                sandbox_id,
                status="ready",
                bootstrap_version=self.settings.sandbox_bootstrap_version,
                touch_used=True,
            )
            return ProjectSandbox(
                id=sandbox_id,
                project_id=self.job.project_id,
                container_name=self.container_name,
                image=self.settings.sandbox_docker_image,
                host_workspace=self.host_workspace,
                volume_name=self.volume_name,
            )
        except Exception as exc:
            self.store.update_sandbox(sandbox_id, status="failed", error=str(exc))
            raise

    def login_command(self, agent: str) -> str:
        if agent == "codex":
            return f"docker exec -it {self.container_name} {self.settings.sandbox_codex_command} login --device-auth"
        if agent == "gemini-cli":
            return f"docker exec -it {self.container_name} {self.settings.sandbox_gemini_command}"
        return f"docker exec -it {self.container_name} {agent} login"

    def ensure_agent_ready(self, agent: str) -> None:
        if agent == "codex":
            try:
                output = self.exec([self.settings.sandbox_codex_command, "login", "status"], cwd=CONTAINER_WORKSPACE, timeout=30)
            except CommandError as exc:
                output = exc.output
            if "not logged in" in output.lower():
                command = self.login_command(agent)
                raise RuntimeError(
                    "Codex is not authenticated in this project sandbox.\n\n"
                    "Run this on the orchestrator host:\n\n"
                    "```powershell\n"
                    f"{command}\n"
                    "```\n\n"
                    "After login completes, retry this job by removing `agent:failed` and adding `agent:codex` again."
                )
        if agent == "gemini-cli":
            if self._has_any_env("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_GCA"):
                return
            if self._container_has_gemini_credentials():
                return
            command = self.login_command(agent)
            raise RuntimeError(
                "Gemini is not authenticated in this project sandbox.\n\n"
                "Run this on the orchestrator host and select an auth method:\n\n"
                "```powershell\n"
                f"{command}\n"
                "```\n\n"
                "Note: Gemini OAuth uses a browser localhost callback. If that does not work from Docker, configure "
                "`GEMINI_API_KEY` or Vertex AI environment variables and include them in `SANDBOX_PASS_ENV`.\n\n"
                "After authentication is configured, retry this job by removing `agent:failed` and adding `agent:gemini` again."
            )

    def prepare_issue_branch(self, repo_url: str, branch: str, base: str, timeout: int) -> None:
        if not self._container_path_exists(f"{CONTAINER_REPO}/.git"):
            self.exec(["git", "clone", repo_url, CONTAINER_REPO], cwd=CONTAINER_WORKSPACE, timeout=timeout)
        else:
            self.exec(["git", "remote", "set-url", "origin", repo_url], cwd=CONTAINER_REPO, timeout=timeout)

        self.exec(["git", "fetch", "origin", "--prune"], cwd=CONTAINER_REPO, timeout=timeout)
        current = self.exec(["git", "branch", "--show-current"], cwd=CONTAINER_REPO, timeout=timeout).strip()
        if current == branch:
            self.clean_worktree(timeout)
            return

        if self._try_exec(["git", "checkout", branch], cwd=CONTAINER_REPO, timeout=timeout):
            self.clean_worktree(timeout)
            return
        if self._try_exec(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=CONTAINER_REPO, timeout=timeout):
            self.clean_worktree(timeout)
            return
        self.exec(["git", "checkout", "-B", branch, f"origin/{base}"], cwd=CONTAINER_REPO, timeout=timeout)
        self.clean_worktree(timeout)

    def clean_worktree(self, timeout: int) -> None:
        self.exec(["git", "reset", "--hard"], cwd=CONTAINER_REPO, timeout=timeout)
        self.exec(["git", "clean", "-fd"], cwd=CONTAINER_REPO, timeout=timeout)

    def current_head(self, timeout: int) -> str:
        return self.exec(["git", "rev-parse", "HEAD"], cwd=CONTAINER_REPO, timeout=timeout).strip()

    def has_changes(self, timeout: int) -> bool:
        return bool(self.exec(["git", "status", "--porcelain"], cwd=CONTAINER_REPO, timeout=timeout).strip())

    def commit_all(self, message: str, author_name: str, author_email: str, timeout: int) -> None:
        self.exec(["git", "config", "user.name", author_name], cwd=CONTAINER_REPO, timeout=timeout)
        self.exec(["git", "config", "user.email", author_email], cwd=CONTAINER_REPO, timeout=timeout)
        self.exec(["git", "add", "-A"], cwd=CONTAINER_REPO, timeout=timeout)
        self.exec(["git", "commit", "-m", message], cwd=CONTAINER_REPO, timeout=timeout)

    def push_branch(self, branch: str, timeout: int) -> None:
        try:
            self.exec(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=CONTAINER_REPO, timeout=timeout)
        except CommandError:
            self.exec(["git", "fetch", "origin", branch], cwd=CONTAINER_REPO, timeout=timeout)
            self.exec(["git", "pull", "--rebase", "origin", branch], cwd=CONTAINER_REPO, timeout=timeout)
            self.exec(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=CONTAINER_REPO, timeout=timeout)

    def run_agent(
        self,
        agent: str,
        prompt: str,
        timeout: int,
        *,
        cancel_file: Path | None,
        pid_file: Path | None,
        log_path: Path,
    ) -> AgentResult:
        prompt_file = self.host_workspace / "issues" / f"issue-{self.job.issue_iid}" / f"{self.job.id}-agent-prompt.md"
        output_file = log_path
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt, encoding="utf-8", errors="replace")
        container_prompt_file = f"{CONTAINER_WORKSPACE}/issues/issue-{self.job.issue_iid}/{self.job.id}-agent-prompt.md"
        self.exec_shell(f"mkdir -p {shlex.quote(CONTAINER_WORKSPACE + '/issues/issue-' + str(self.job.issue_iid))}", cwd=CONTAINER_WORKSPACE, timeout=30)
        self._docker(["cp", str(prompt_file), f"{self.container_name}:{container_prompt_file}"], timeout=30)

        if agent == "opencode":
            self.exec_shell("rm -f /workspace/repo/.git/opencode", cwd=CONTAINER_WORKSPACE, timeout=30)
            self.exec_shell(
                "rm -rf /home/agent/.local/share/opencode /home/agent/.cache/opencode",
                cwd=CONTAINER_WORKSPACE,
                timeout=30,
            )
            command = [
                self.settings.sandbox_opencode_command,
                "run",
                "--dangerously-skip-permissions",
                "--print-logs",
                "--log-level",
                "INFO",
                "Read the attached prompt and implement the requested code changes in this repository.",
                "--file",
                container_prompt_file,
            ]
            if self.settings.sandbox_opencode_model:
                command[2:2] = ["--model", self.settings.sandbox_opencode_model]
            self.exec_live(
                command,
                cwd=CONTAINER_REPO,
                output_path=output_file,
                timeout=timeout,
                cancel_file=cancel_file,
                pid_file=pid_file,
                idle_success_after_changes=True,
            )
        elif agent == "codex":
            self.ensure_agent_ready(agent)
            command = [
                self.settings.sandbox_codex_command,
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "-",
            ]
            self.exec_live(
                command,
                cwd=CONTAINER_REPO,
                output_path=output_file,
                timeout=timeout,
                cancel_file=cancel_file,
                pid_file=pid_file,
                stdin_text=prompt,
            )
        elif agent == "gemini-cli":
            self.ensure_agent_ready(agent)
            command = [self.settings.sandbox_gemini_command, "--yolo", "--prompt", prompt]
            self.exec_live(command, cwd=CONTAINER_REPO, output_path=output_file, timeout=timeout, cancel_file=cancel_file, pid_file=pid_file)
        else:
            raise ValueError(f"Unsupported agent for docker_project backend: {agent}")

        return AgentResult(output=output_file.read_text(encoding="utf-8", errors="replace"))

    def read_project_rules(self, timeout: int) -> str:
        chunks: list[str] = []
        for name in ("AGENTS.md", "CODEX.md", "CONTRIBUTING.md"):
            path = f"{CONTAINER_REPO}/{name}"
            if self._container_path_exists(path):
                content = self.exec_shell(f"cat {shlex.quote(path)}", cwd=CONTAINER_REPO, timeout=timeout)
                chunks.append(f"## {name}\n\n{content.strip()}")
        return "\n\n".join(chunks)

    def run_validation(self, timeout: int) -> str:
        candidates = [
            ("package.json", ["npm", "test"]),
            ("pyproject.toml", ["python", "-m", "pytest"]),
            ("pytest.ini", ["python", "-m", "pytest"]),
        ]
        for marker, command in candidates:
            if self._container_path_exists(f"{CONTAINER_REPO}/{marker}"):
                try:
                    output = self.exec(command, cwd=CONTAINER_REPO, timeout=timeout)
                    return f"{' '.join(command)}: passed\n{output[-2000:]}"
                except CommandError as exc:
                    raise RuntimeError(f"{' '.join(command)} failed\n{exc.output[-4000:]}") from exc
        return "No test command detected."

    def exec(self, command: list[str], *, cwd: str, timeout: int | None = None) -> str:
        script = f"cd {shlex.quote(cwd)} && {' '.join(shlex.quote(part) for part in command)}"
        return self.exec_shell(script, cwd=CONTAINER_WORKSPACE, timeout=timeout)

    def exec_shell(self, script: str, *, cwd: str, timeout: int | None = None) -> str:
        docker_command = ["exec", *self._exec_env_args(), "-w", cwd, self.container_name, "sh", "-lc", script]
        return self._docker(docker_command, timeout=timeout)

    def exec_live(
        self,
        command: list[str],
        *,
        cwd: str,
        output_path: Path,
        timeout: int,
        cancel_file: Path | None,
        pid_file: Path | None,
        stdin_text: str | None = None,
        idle_success_after_changes: bool = False,
    ) -> None:
        script = f"cd {shlex.quote(cwd)} && {' '.join(shlex.quote(part) for part in command)}"
        docker_command = ["docker", "exec"]
        if stdin_text is not None:
            docker_command.append("-i")
        docker_command.extend([*self._exec_env_args(), "-w", cwd, self.container_name, "sh", "-lc", script])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", errors="replace") as output_file:
            proc = subprocess.Popen(
                docker_command,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.PIPE if stdin_text is not None else None,
                stdout=output_file,
                stderr=subprocess.STDOUT,
            )
            if pid_file:
                pid_file.write_text(str(proc.pid), encoding="utf-8")
            if proc.stdin and stdin_text is not None:
                proc.stdin.write(stdin_text)
                proc.stdin.close()
            self._wait(proc, timeout, cancel_file, output_path, idle_success_after_changes)

        output = output_path.read_text(encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"Docker agent command failed ({proc.returncode}):\n{output[-4000:]}")

    def _try_exec(self, command: list[str], *, cwd: str, timeout: int) -> bool:
        try:
            self.exec(command, cwd=cwd, timeout=timeout)
            return True
        except CommandError:
            return False

    def _container_exists(self) -> bool:
        proc = subprocess.run(["docker", "inspect", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return proc.returncode == 0

    def _container_running(self) -> bool:
        output = self._docker(["inspect", "-f", "{{.State.Running}}", self.container_name], timeout=30).strip()
        return output.lower() == "true"

    def _create_container(self) -> None:
        self._docker(["volume", "create", self.volume_name], timeout=60)
        command = [
            "create",
            "--name",
            self.container_name,
            "-v",
            f"{self.volume_name}:{CONTAINER_WORKSPACE}",
            "-w",
            CONTAINER_WORKSPACE,
        ]
        if self.settings.sandbox_user:
            command.extend(["--user", self.settings.sandbox_user])
        command.extend([self.settings.sandbox_docker_image, "sh", "-lc", "sleep infinity"])
        self._docker(command, timeout=120)

    def _read_bootstrap_version(self) -> str | None:
        proc = subprocess.run(
            ["docker", "exec", "-w", CONTAINER_WORKSPACE, self.container_name, "sh", "-lc", "cat .sandbox-bootstrap-version 2>/dev/null"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    def _exec_env_args(self) -> list[str]:
        args: list[str] = []
        env = os.environ.copy()
        for key in BLOCKED_INHERITED_ENV:
            env.pop(key, None)
            env.pop(key.lower(), None)
        for name in self.settings.sandbox_pass_env:
            value = env.get(name)
            if value:
                args.extend(["-e", f"{name}={value}"])
        return args

    def _docker(self, args: list[str], timeout: int | None = None) -> str:
        command = ["docker", *args]
        proc = subprocess.run(
            command,
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

    def _container_path_exists(self, path: str) -> bool:
        proc = subprocess.run(
            ["docker", "exec", self.container_name, "sh", "-lc", f"test -e {shlex.quote(path)}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode == 0

    def _container_has_gemini_credentials(self) -> bool:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                self.container_name,
                "sh",
                "-lc",
                (
                    "test -s /home/agent/.gemini/oauth_creds.json "
                    "|| (test -s /home/agent/.gemini/settings.json "
                    "&& grep -Eq 'GEMINI_API_KEY|GOOGLE_API_KEY|vertexai|google-auth' /home/agent/.gemini/settings.json)"
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode == 0

    def _has_any_env(self, *names: str) -> bool:
        env = os.environ
        return any(bool(env.get(name)) for name in names)

    def _wait(
        self,
        proc: subprocess.Popen[str],
        timeout: int,
        cancel_file: Path | None,
        output_path: Path,
        idle_success_after_changes: bool,
    ) -> None:
        started = time.monotonic()
        last_output_mtime = output_path.stat().st_mtime if output_path.exists() else 0.0
        last_activity = time.monotonic()
        first_changes_at: float | None = None
        while proc.poll() is None:
            if cancel_file and cancel_file.exists():
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise RuntimeError("Docker agent command cancelled.")
            if time.monotonic() - started > timeout:
                proc.kill()
                proc.wait()
                raise RuntimeError(f"Docker agent command timed out after {timeout} seconds.")
            current_mtime = output_path.stat().st_mtime if output_path.exists() else 0.0
            if current_mtime != last_output_mtime:
                last_output_mtime = current_mtime
                last_activity = time.monotonic()
            if idle_success_after_changes and first_changes_at is None and self._repo_has_changes():
                first_changes_at = time.monotonic()
            if idle_success_after_changes and time.monotonic() - last_activity > self.settings.sandbox_agent_idle_timeout_seconds:
                if self._repo_has_changes():
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    if proc.returncode != 0:
                        proc.returncode = 0
                    return
            if (
                idle_success_after_changes
                and first_changes_at is not None
                and time.monotonic() - first_changes_at > self.settings.sandbox_agent_max_after_changes_seconds
            ):
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                if proc.returncode != 0:
                    proc.returncode = 0
                return
            time.sleep(1)
        if cancel_file and cancel_file.exists():
            raise RuntimeError("Docker agent command cancelled.")

    def _repo_has_changes(self) -> bool:
        try:
            return bool(self.exec(["git", "status", "--porcelain"], cwd=CONTAINER_REPO, timeout=30).strip())
        except Exception:
            return False
