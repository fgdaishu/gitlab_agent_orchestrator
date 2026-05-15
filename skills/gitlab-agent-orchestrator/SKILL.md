---
name: gitlab-agent-orchestrator
description: Install, configure, operate, and troubleshoot the GitLab Agent Orchestrator service that turns GitLab issue labels into opencode, codex, or gemini agent jobs. Use when a user asks Codex to deploy this service, initialize a new GitLab integration, start or stop the API/worker, build the Docker sandbox image, configure GitLab URL/token/webhook secrets, set agent API keys or OAuth, create webhook instructions, or debug why issue labels are not triggering agent work.
---

# GitLab Agent Orchestrator

## Overview

Use this skill as the operator runbook for the GitLab Agent Orchestrator repository. Prefer the repository scripts over hand-written commands so setup is repeatable.

## Workflow

1. Confirm the current directory is the orchestrator repo by checking for `orchestrator/main.py`, `orchestrator/worker.py`, `.env.example`, and `docker/sandbox/Dockerfile`.
2. Run `scripts/doctor.ps1` to inspect Python, Git, Docker, `.env`, the sandbox image, and current API health.
3. If `.env` is missing, collect only the required secrets from the user and run `scripts/init-env.ps1`. Never print or commit tokens.
4. Build the sandbox image with `docker/sandbox/build.ps1` when `gitlab-agent-sandbox:latest` is missing or the Dockerfile changed.
5. Start services with `scripts/start.ps1`, then verify with `scripts/status.ps1` and `GET /healthz`.
6. Give the user the webhook URL: `http://<orchestrator-host-ip>:8080/gitlab/webhook`, plus the `GITLAB_WEBHOOK_SECRET` value they configured.
7. For Codex or Gemini, initialize auth inside the project sandbox after the first project container exists, or use API keys through `SANDBOX_PASS_ENV`.
8. Test with a GitLab issue label: `agent:opencode`, `agent:codex`, or `agent:gemini`.

## Scripts

Run scripts from the repository root:

- `scripts/doctor.ps1` - preflight checks.
- `scripts/init-env.ps1` - create `.env` from `.env.example`; use `-Force` only when the user explicitly wants to rewrite `.env`.
- `docker/sandbox/build.ps1` - build `gitlab-agent-sandbox:latest`.
- `scripts/start.ps1` - start FastAPI and worker in hidden background PowerShell processes.
- `scripts/status.ps1` - show service, health, and Docker project sandbox status.
- `scripts/stop.ps1` - stop API and worker processes started by `scripts/start.ps1`.
- `scripts/install-skill.ps1` - copy this skill into `$CODEX_HOME/skills` or `~/.codex/skills`.

## Required User Inputs

Ask for these when `.env` does not exist:

- GitLab URL, for example `http://192.168.1.251/gitlab` or `https://gitlab.com`.
- GitLab access token with enough permissions to read/write issues, labels, branches, and merge requests.
- GitLab webhook secret.
- Desired default agent, usually `opencode`.
- Optional model/API credentials: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or Vertex variables. These can be written by `scripts/init-env.ps1` and passed into Docker by `SANDBOX_PASS_ENV`.

Do not ask for a token if `.env` already exists and appears complete. Do not echo secret values in summaries.

## Agent Auth

Use `opencode` with `SANDBOX_OPENCODE_MODEL=opencode/big-pickle` for the lowest-friction smoke test.

Codex requires sandbox-local auth unless an API key flow is configured. Once the project container exists, use:

```powershell
docker exec -it gitlab-agent-project-<project_id> codex login --device-auth
```

Gemini OAuth is usable in the current Docker sandbox flow. Once the project container exists, use:

```powershell
docker exec -it gitlab-agent-project-<project_id> gemini
```

If OAuth is unsuitable in the user's environment, configure `GEMINI_API_KEY` or Vertex variables on the orchestrator host and include them in `SANDBOX_PASS_ENV`, then restart the service.

## Webhook Guidance

The webhook URL must point to the machine running the orchestrator API, not necessarily the GitLab host:

```text
http://<orchestrator-host-ip>:8080/gitlab/webhook
```

In GitLab, enable issue events. Keep note/comment events disabled unless the code is explicitly changed to support them.

For GitLab.com, the orchestrator must be reachable from the public internet over an acceptable URL, usually HTTPS via a reverse proxy or tunnel.

## Troubleshooting

Read `references/troubleshooting.md` when labels do not trigger jobs, jobs stay running, Docker containers are missing, GitLab comments are not written, or agent authentication fails.
