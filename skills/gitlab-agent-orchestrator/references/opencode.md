# OpenCode Usage

Use `opencode` first when the server cannot install authenticated agents such as Codex or Gemini.

## Server Defaults

Configure the orchestrator host with:

```env
DEFAULT_AGENT=opencode
AGENT_TRIGGER_LABEL=agent:opencode
AGENT_EXECUTION_BACKEND=docker_project
SANDBOX_DOCKER_IMAGE=gitlab-agent-sandbox:latest
SANDBOX_OPENCODE_MODEL=opencode/big-pickle
SANDBOX_PASS_ENV=
SANDBOX_CODEX_COMMAND=codex-disabled
SANDBOX_GEMINI_COMMAND=gemini-disabled
```

Build the sandbox image with OpenCode only:

```bash
docker build --tag gitlab-agent-sandbox:latest --file docker/sandbox/Dockerfile --build-arg INSTALL_OPENCODE=true --build-arg INSTALL_CODEX=false --build-arg INSTALL_GEMINI=false .
```

## GitLab Trigger

Add this label to an issue:

```text
agent:opencode
```

The job should change the label to `agent:running`, create or reuse a project container named `gitlab-agent-project-<project_id>`, push an `agent/issue-...` branch, create or update a merge request, and comment back on the issue.

## Agent Behavior

Issue text and comments are the task source. If the issue explicitly asks for tests, OpenCode should run the relevant tests and fix failures. Otherwise, it should focus on producing code changes and let GitLab review/merge handle the rest.

When an issue depends on another issue, write this in the issue description:

```markdown
## Agent Metadata

Depends-On: #2
```

Every OpenCode run must create or update:

```text
.agent/handoffs/issue-<iid>.md
```

Use this structure: Summary, Changed Files, Decisions, Interfaces / Contracts, Follow-up Needed, Test Notes, and Context For Next Issues.

Do not commit secrets, do not print tokens, and do not expect Codex or Gemini OAuth to be available in this opencode-only deployment.
