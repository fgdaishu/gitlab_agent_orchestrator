from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    gitlab_url: str
    gitlab_token: str
    gitlab_webhook_secret: str
    default_agent: str
    agent_trigger_label: str
    database_url: str
    workspace_root: Path
    job_poll_interval_seconds: int
    job_timeout_seconds: int
    git_author_name: str
    git_author_email: str
    opencode_command: str
    codex_command: str
    gemini_command: str
    agent_execution_backend: str
    sandbox_docker_image: str
    sandbox_bootstrap_version: str
    sandbox_bootstrap_command: str
    sandbox_user: str
    sandbox_opencode_command: str
    sandbox_opencode_model: str
    sandbox_agent_idle_timeout_seconds: int
    sandbox_agent_max_after_changes_seconds: int
    sandbox_codex_command: str
    sandbox_gemini_command: str
    sandbox_pass_env: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gitlab_url=(_env("GITLAB_URL", "http://192.168.1.251/gitlab") or "").rstrip("/"),
            gitlab_token=_env("GITLAB_TOKEN", "") or "",
            gitlab_webhook_secret=_env("GITLAB_WEBHOOK_SECRET", "") or "",
            default_agent=_env("DEFAULT_AGENT", "opencode") or "opencode",
            agent_trigger_label=_env("AGENT_TRIGGER_LABEL", "agent:opencode") or "agent:opencode",
            database_url=_env("DATABASE_URL", "sqlite:///./orchestrator.sqlite3") or "sqlite:///./orchestrator.sqlite3",
            workspace_root=Path(_env("WORKSPACE_ROOT", "./workspaces") or "./workspaces"),
            job_poll_interval_seconds=int(_env("JOB_POLL_INTERVAL_SECONDS", "2") or "2"),
            job_timeout_seconds=int(_env("JOB_TIMEOUT_SECONDS", "3600") or "3600"),
            git_author_name=_env("GIT_AUTHOR_NAME", "agent-bot") or "agent-bot",
            git_author_email=_env("GIT_AUTHOR_EMAIL", "agent-bot@example.local") or "agent-bot@example.local",
            opencode_command=_env("OPENCODE_COMMAND", "opencode") or "opencode",
            codex_command=_env("CODEX_COMMAND", "codex") or "codex",
            gemini_command=_env("GEMINI_COMMAND", "gemini") or "gemini",
            agent_execution_backend=_env("AGENT_EXECUTION_BACKEND", "local") or "local",
            sandbox_docker_image=_env("SANDBOX_DOCKER_IMAGE", "gitlab-agent-sandbox:latest") or "gitlab-agent-sandbox:latest",
            sandbox_bootstrap_version=_env("SANDBOX_BOOTSTRAP_VERSION", "1") or "1",
            sandbox_bootstrap_command=_env("SANDBOX_BOOTSTRAP_COMMAND", ":") or ":",
            sandbox_user=_env("SANDBOX_USER", "") or "",
            sandbox_opencode_command=_env("SANDBOX_OPENCODE_COMMAND", "opencode") or "opencode",
            sandbox_opencode_model=_env("SANDBOX_OPENCODE_MODEL", "") or "",
            sandbox_agent_idle_timeout_seconds=int(_env("SANDBOX_AGENT_IDLE_TIMEOUT_SECONDS", "120") or "120"),
            sandbox_agent_max_after_changes_seconds=int(_env("SANDBOX_AGENT_MAX_AFTER_CHANGES_SECONDS", "180") or "180"),
            sandbox_codex_command=_env("SANDBOX_CODEX_COMMAND", "codex") or "codex",
            sandbox_gemini_command=_env("SANDBOX_GEMINI_COMMAND", "gemini") or "gemini",
            sandbox_pass_env=tuple(
                name.strip()
                for name in (_env("SANDBOX_PASS_ENV", "OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY") or "").split(",")
                if name.strip()
            ),
        )

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL is supported by the MVP")
        return Path(self.database_url[len(prefix) :])


settings = Settings.from_env()
