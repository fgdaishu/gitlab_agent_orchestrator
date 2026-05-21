---
name: gitlab-agent-orchestrator
description: Operate and use the GitLab Agent Orchestrator service. Use when a user asks Codex to start/stop/debug the service, configure GitLab webhooks, create GitLab issues for agent execution, choose between default_coding and strict_development workflows, prepare strict task cards/context packs, retry/cancel jobs, inspect labels/MRs/logs, or troubleshoot preflight failures.
---

# GitLab Agent Orchestrator

## Overview

Use this skill as the runbook for GitLab Agent Orchestrator. The service turns GitLab issue labels into agent jobs, then pushes a branch and creates an MR.

There are two supported workflow modes:

- `default_coding`: low-friction general development. This is the default when issue metadata does not specify a workflow.
- `strict_development`: strict task-card development with preflight, file boundaries, validation commands, handoff, and report generation.

Use `Workflow: strict` for strict mode. It resolves to `strict_development`.

## Initial Checks

1. Confirm the current directory is the orchestrator repo by checking for:
   - `orchestrator/main.py`
   - `orchestrator/worker.py`
   - `.env.example`
   - `docker/sandbox/Dockerfile`
2. Run `scripts/doctor.ps1` when diagnosing setup.
3. Verify the API:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/healthz
```

4. Check that no old process is occupying the API port:

```powershell
netstat -ano | Select-String ':8080'
```

Use `scripts/stop.ps1 -Port 8080` before restarting.

## Service Operations

Run scripts from the repository root.

Start:

```powershell
.\scripts\start.ps1 -Port 8080
```

Stop:

```powershell
.\scripts\stop.ps1 -Port 8080
```

Status:

```powershell
.\scripts\status.ps1
```

Build sandbox image:

```powershell
.\docker\sandbox\build.ps1
```

Install this skill:

```powershell
.\scripts\install-skill.ps1
```

## GitLab Webhook

Webhook URL:

```text
http://<orchestrator-host-ip>:8080/gitlab/webhook
```

Enable only:

```text
Issues events
```

The webhook secret must match `.env`:

```text
GITLAB_WEBHOOK_SECRET
```

The webhook must point to the machine running the orchestrator API. If the user wants local gao/orchestrator, do not point GitLab to an old server-side service.

## Agent Labels

Adding one of these labels to an issue triggers a job:

```text
agent:opencode
agent:codex
agent:gemini
```

Recommended smoke-test label:

```text
agent:opencode
```

## Default Coding Workflow

Use this for ordinary coding tasks.

Issue body example:

```markdown
Fix the parser so it rejects empty input.

Please add or update tests if needed.
```

Then add:

```text
agent:opencode
```

Expected labels:

- running: `agent:running`
- success: `agent:review`
- failure: `agent:failed`

Default mode still requires the agent to create:

```text
.agent/handoffs/issue-<iid>.md
```

## Strict Development Workflow

Use this for structured, auditable tasks with explicit boundaries.

Issue body template:

```markdown
## Agent Metadata

Workflow: strict

Task-ID: <TASK-ID>

## Request

Implement and validate the task described by `task-cards/<TASK-ID>.yaml`.

Follow `context-packs/<TASK-ID>.md`.

Do not expand scope beyond the task card.
```

Then add:

```text
agent:opencode
```

Expected labels:

- running: `strict:running`
- success: `strict:review`
- failure: `strict:validation-failed`

## Strict Repo Materials

Strict mode expects these repo materials:

```text
task-cards/<TASK-ID>.yaml
context-packs/<TASK-ID>.md
contracts/...
.agent/handoffs/
reports/
```

Minimum task card shape:

```yaml
task_id: <TASK-ID>
title: Short task title
module: MODULE-NAME

objective:
  Describe what must be achieved.

must_follow:
  - no unsafe code

relevant_contracts:
  - contracts/example.yaml

files_allowed:
  - Cargo.lock
  - src/example.rs
  - tests/example.rs
  - .agent/handoffs/
  - reports/

forbidden_files:
  - docs/original-prd.md

validation_commands:
  - cargo test --test example

handoff_required:
  - implementation summary
  - tests run
  - edge cases handled
```

For Rust tasks that run `cargo`, include `Cargo.lock` in `files_allowed`. If dependencies must not change, forbid `Cargo.toml` rather than forbidding `Cargo.lock`.

## Dependencies Between Issues

Use hard dependency:

```markdown
Depends-On: #3
```

Use best-effort context:

```markdown
Context-From: #4
```

`Depends-On` requires the referenced issue to have a successful job and an existing handoff file.

## Preflight Troubleshooting

Strict mode preflight runs before the agent starts.

Common failures:

- `task card not found`: create `task-cards/<TASK-ID>.yaml` or fix `Task-ID`.
- `context pack not found`: create `context-packs/<TASK-ID>.md` or fix `Task-ID`.
- `task_id must match issue Task-ID`: align task card and issue metadata.
- `files_allowed must include .agent/handoffs/`: allow handoff output.
- `files_allowed must include reports/`: allow validation report output.
- `Cargo.lock`: add it to `files_allowed` for Rust cargo tasks.
- `referenced contract not found`: fix `relevant_contracts`.
- `required tool ... is not available`: rebuild sandbox or install/configure the tool.
- `required tool ... is not recognized`: use a supported validation command tool or extend preflight detection.

If preflight fails, do not edit code first. Fix repo materials or sandbox tooling, then retry the job.

## Job API

Check job:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>
```

View log:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>/log
```

Retry:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/retry
```

Cancel:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/cancel
```

## Sandbox Tools

The default sandbox image includes:

```text
opencode
codex
gemini
cargo
rustc
git
node
python
ripgrep
```

Codex may require:

```powershell
docker exec -it gitlab-agent-project-<project_id> codex login --device-auth
```

Gemini may require:

```powershell
docker exec -it gitlab-agent-project-<project_id> gemini
```

If OAuth is unsuitable, configure API keys and include them in `SANDBOX_PASS_ENV`.

## Example User Prompts For Codex

Start local service:

```text
Use the gitlab-agent-orchestrator skill. Start the local orchestrator on port 8080 and verify health.
```

Create a default coding issue:

```text
Use the gitlab-agent-orchestrator skill. Create a default coding issue in project 49 to fix empty input handling, then add agent:opencode.
```

Create a strict issue:

```text
Use the gitlab-agent-orchestrator skill. Create a strict workflow issue for Task-ID PNG-SIGNATURE-001 in project 49 and trigger agent:opencode.
```

Diagnose no reaction after label:

```text
Use the gitlab-agent-orchestrator skill. The issue label was added but nothing happened. Check webhook delivery, API logs, worker status, DB jobs, and Docker access.
```

Diagnose strict preflight failure:

```text
Use the gitlab-agent-orchestrator skill. Explain why the strict workflow issue failed preflight and tell me exactly which repo material to fix.
```

Retry failed job:

```text
Use the gitlab-agent-orchestrator skill. Retry job <job_id> after I fixed the task card.
```
