# GitLab Agent Orchestrator

Local GitLab issue-to-agent orchestrator. The MVP receives GitLab issue webhooks, detects a newly added agent label, queues a job in SQLite, runs a coding agent, pushes a branch, creates a Merge Request, and writes the result back to the issue.

## Quick Start

1. Install Python dependencies:

```powershell
python -m pip install -e ".[dev]"
```

2. Create `.env` interactively:

```powershell
.\scripts\init-env.ps1
```

You will need:

- GitLab URL, for example `http://<gitlab-host>/gitlab`
- GitLab access token
- GitLab webhook secret
- Optional agent API keys, such as `OPENAI_API_KEY` or `GEMINI_API_KEY`

3. Build the project sandbox image:

```powershell
.\docker\sandbox\build.ps1
```

4. Start API and worker in the background:

```powershell
.\scripts\start.ps1
```

5. Check status:

```powershell
.\scripts\status.ps1
```

Configure the GitLab project webhook to call:

```text
POST http://<orchestrator-host>:8080/gitlab/webhook
```

Enable `Issues events` and set the webhook secret to the same value as `GITLAB_WEBHOOK_SECRET`.

For GitLab.com, expose the orchestrator API through a public HTTPS URL or tunnel before configuring the webhook.

## Codex Skill

This repository includes a Codex skill that teaches Codex how to install, configure, operate, and troubleshoot this service.

Install it into the current user's Codex skills directory:

```powershell
.\scripts\install-skill.ps1
```

Then ask Codex something like:

```text
Use the gitlab-agent-orchestrator skill to set up this service for a new GitLab project.
```

## MVP Trigger

The default test agent is `opencode`, so adding this issue label queues a job:

```text
agent:opencode
```

These labels are supported by the adapter layer:

```text
agent:opencode
agent:codex
agent:gemini
```

The worker maps them to local CLI commands:

```text
OPENCODE_COMMAND=opencode
CODEX_COMMAND=codex
GEMINI_COMMAND=gemini
```

The recommended default is `AGENT_EXECUTION_BACKEND=docker_project`. In the legacy `local` backend, each GitLab issue uses a persistent workspace:

```text
workspaces/project-<project_id>/issue-<issue_iid>/repo
```

Running the same issue again reuses the same local clone, same branch, and existing Merge Request when present. New issue comments are included in the next prompt as incremental instructions.

## Docker Project Sandbox

Set this to run all jobs for the same GitLab project inside one long-lived Docker container:

```env
AGENT_EXECUTION_BACKEND=docker_project
SANDBOX_DOCKER_IMAGE=gitlab-agent-sandbox:latest
```

The first triggered issue for a project automatically creates and bootstraps a container named:

```text
gitlab-agent-project-<project_id>
```

The project workspace is stored in a Docker named volume and mounted into the container at `/workspace`:

```text
gitlab-agent-project-<project_id>-workspace
  mounted at /workspace
  repo/
  issues/issue-<issue_iid>/
  cache/
  logs/
```

In `docker_project` mode, git operations and agent execution run inside the container via `docker exec`. Repository files are not synchronized back to the Windows host; changes are pushed to GitLab from inside the container. The MVP keeps a project-level lock, so only one job per project runs at a time.

The orchestrator does not enforce an automatic validation step by default. If the issue or follow-up comments explicitly ask for tests, the prompt tells the agent to run the relevant tests/build/checks and fix failures. Otherwise, producing code changes is enough for the job to proceed to branch push and MR creation.

The sandbox image must contain the tools you want to use, for example `git`, `node`, `python`, `opencode`, `codex`, and `gemini`. Project-specific setup can be configured with:

```env
SANDBOX_BOOTSTRAP_VERSION=1
SANDBOX_BOOTSTRAP_COMMAND=:
SANDBOX_OPENCODE_MODEL=opencode/big-pickle
SANDBOX_PASS_ENV=OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY,GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_GENAI_USE_GCA
```

A ready-to-build base image is provided in `docker/sandbox`:

```powershell
.\docker\sandbox\build.ps1
```

Sandbox management APIs:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/projects/<project_id>/sandbox
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/restart
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/stop
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/rebuild
```

Agents that require OAuth, such as Codex, must be logged in once inside the project sandbox. If a job detects that Codex is not authenticated, it writes a GitLab issue comment with a command like:

```powershell
docker exec -it gitlab-agent-project-<project_id> codex login --device-auth
```

You can also query the command directly:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/projects/<project_id>/sandbox/agents/codex/login-command
```

Gemini uses an interactive auth picker or environment variables. OAuth has been verified in the current project sandbox flow. If Gemini is not authenticated, the issue comment will show:

```powershell
docker exec -it gitlab-agent-project-<project_id> gemini
```

If Gemini OAuth redirects to an unreachable localhost callback in another environment, prefer API-key or Vertex configuration:

```env
GEMINI_API_KEY=...
SANDBOX_PASS_ENV=GEMINI_API_KEY,GOOGLE_API_KEY,GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_GENAI_USE_GCA
```

## Operations

Run a preflight check:

```powershell
.\scripts\doctor.ps1
```

Stop services started by `scripts\start.ps1`:

```powershell
.\scripts\stop.ps1
```

Check a job:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>
```

View agent output:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>/log
```

Cancel a queued or running job:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/cancel
```

## Configuration

All secrets are read from environment variables. Do not commit `.env`.

See `.env.example` for available settings.
