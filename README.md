# GitLab Agent Orchestrator

Local GitLab issue-to-agent orchestrator. The MVP receives GitLab issue webhooks, detects a newly added agent label, queues a job in SQLite, runs a coding agent, pushes a branch, creates a Merge Request, and writes the result back to the issue.

For end-user workflow instructions, see [`docs/user-guide.md`](docs/user-guide.md).

中文说明见 [`README_zh.md`](README_zh.md).

The repository includes a runnable strict-mode template at [`examples/strict-dev-png-sample`](examples/strict-dev-png-sample). It shows the expected `project-meta/`, `task-cards/`, `context-packs/`, `contracts/`, `test-oracles/`, handoff, and report structure for strict development projects.

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

- GitLab URL, for example `https://gitlab.example.com`
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

For a self-hosted GitLab server where the orchestrator runs on the same host, a common deployment is:

```text
http://<gitlab-host-ip>:18081/gitlab/webhook
```

When group-level webhooks are unavailable, use `ops/sync_develop_project_hooks.sh` on the GitLab host to add or update issue-event project webhooks for every project in the `develop` group. Run it once manually, or install it as a systemd timer.

Alternatively, enable server-side group polling so users do not need to configure webhooks or labels. With this mode, every newly created open issue in the configured group automatically queues the default agent:

```env
AUTO_ISSUE_POLL_ENABLED=true
AUTO_ISSUE_GROUP_PATH=develop
AUTO_ISSUE_POLL_INTERVAL_SECONDS=30
AUTO_ISSUE_SEED_EXISTING=true
DEFAULT_AGENT=opencode
```

Run the poller as a long-lived service:

```bash
python -m orchestrator.issue_poller
```

`AUTO_ISSUE_SEED_EXISTING=true` prevents the first poll from running every historical open issue.

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

## Workflows

Jobs run through a workflow selected from issue metadata. When no workflow is declared, the service uses `default_coding`.

```markdown
## Agent Metadata

Workflow: strict
Task-ID: PNG-CHUNK-001
```

`default_coding` is the low-friction general coding workflow. It builds a prompt from the issue, comments, project rules, and dependency handoffs, then requires a handoff before creating an MR.

`strict` maps to `strict_development`, a stricter task-card workflow. Before starting the agent, it performs preflight checks:

- `Task-ID` is present and matches the task card `task_id`.
- `task-cards/<Task-ID>.yaml` and `context-packs/<Task-ID>.md` exist.
- required task card fields are present.
- referenced contracts exist.
- `files_allowed` includes `.agent/handoffs/` and `reports/`.
- Rust task cards that run `cargo` include `Cargo.lock` in `files_allowed`.
- required agent and validation tools are available in the execution environment.

After the agent exits, `strict_development` still enforces changed-file boundaries, forbidden files, handoff presence, validation commands, and validation report generation.

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

Issue dependencies can be declared in the issue description:

```markdown
## Agent Metadata

Depends-On: #2
Context-From: #4
```

`Depends-On` is strict: the referenced issue must have a successful agent job and a handoff file before the dependent issue runs. `Context-From` is best-effort context. Handoff files live in the repository:

```text
.agent/handoffs/issue-<iid>.md
```

The worker asks every agent run to create or update its own handoff file and includes dependency handoffs in the next prompt.

The sandbox image must contain the tools you want to use, for example `git`, `node`, `python`, `opencode`, `codex`, `gemini`, and language toolchains. The default image installs OpenCode, Codex CLI, Gemini CLI, and Rust through `rustup` with the `stable` toolchain so Rust projects do not fail on modern `Cargo.lock` files. Project-specific setup can be configured with:

```env
SANDBOX_BOOTSTRAP_VERSION=1
SANDBOX_BOOTSTRAP_COMMAND=:
SANDBOX_OPENCODE_MODEL=opencode/big-pickle
SANDBOX_PASS_ENV=OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY,GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_GENAI_USE_GCA
```

For an opencode-only server without VPN access to install authenticated agents:

```env
DEFAULT_AGENT=opencode
AGENT_TRIGGER_LABEL=agent:opencode
SANDBOX_OPENCODE_MODEL=opencode/big-pickle
SANDBOX_PASS_ENV=
SANDBOX_CODEX_COMMAND=codex-disabled
SANDBOX_GEMINI_COMMAND=gemini-disabled
```

Build only OpenCode into the sandbox image:

```bash
docker build --tag gitlab-agent-sandbox:latest --file docker/sandbox/Dockerfile --build-arg INSTALL_OPENCODE=true --build-arg INSTALL_CODEX=false --build-arg INSTALL_GEMINI=false .
```

Select a specific Rust toolchain for the sandbox image when a project requires it:

```bash
docker build --tag gitlab-agent-sandbox:latest --file docker/sandbox/Dockerfile --build-arg RUSTUP_TOOLCHAIN=1.78.0 .
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

`stop.ps1` also clears any leftover process still listening on the configured API port:

```powershell
.\scripts\stop.ps1 -Port 8080
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
