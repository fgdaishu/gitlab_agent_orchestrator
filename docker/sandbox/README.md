# GitLab Agent Sandbox Image

This image is used by `AGENT_EXECUTION_BACKEND=docker_project`.

It includes:

- Git
- Node.js and npm
- Python 3 and venv
- ripgrep
- build-essential
- OpenCode CLI
- Codex CLI
- Gemini CLI

Build:

```powershell
.\docker\sandbox\build.ps1
```

Equivalent Docker command:

```powershell
docker build -t gitlab-agent-sandbox:latest -f docker/sandbox/Dockerfile .
```

Use it in `.env`:

```env
AGENT_EXECUTION_BACKEND=docker_project
SANDBOX_DOCKER_IMAGE=gitlab-agent-sandbox:latest
SANDBOX_PASS_ENV=OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY
```

Notes:

- Do not bake GitLab tokens, model API keys, or CLI login files into the image.
- Runtime secrets should be passed through `SANDBOX_PASS_ENV`.
- The container runs as the non-root `agent` user.
- Project workspaces are mounted at `/workspace`.

Package names can be overridden at build time:

```powershell
docker build -t gitlab-agent-sandbox:latest -f docker/sandbox/Dockerfile `
  --build-arg OPENCODE_NPM_PACKAGE=opencode-ai `
  --build-arg CODEX_NPM_PACKAGE=@openai/codex `
  --build-arg GEMINI_NPM_PACKAGE=@google/gemini-cli `
  .
```
