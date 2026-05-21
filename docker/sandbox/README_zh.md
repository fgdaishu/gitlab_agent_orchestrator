# GitLab Agent Sandbox Image 中文说明

这是 GitLab Agent Orchestrator 的 Docker 项目沙箱镜像，用于 `AGENT_EXECUTION_BACKEND=docker_project` 模式。

镜像包含：

- Git
- Node.js 和 npm
- Python 3 和 venv
- ripgrep
- build-essential
- OpenCode CLI
- Codex CLI
- Gemini CLI

构建镜像：

```powershell
.\docker\sandbox\build.ps1
```

等价的 Docker 命令：

```powershell
docker build -t gitlab-agent-sandbox:latest -f docker/sandbox/Dockerfile .
```

在 `.env` 中启用：

```env
AGENT_EXECUTION_BACKEND=docker_project
SANDBOX_DOCKER_IMAGE=gitlab-agent-sandbox:latest
SANDBOX_PASS_ENV=OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY
```

注意事项：

- 不要把 GitLab token、模型 API key 或 CLI 登录文件写入镜像。
- 运行时密钥应通过 `SANDBOX_PASS_ENV` 传入容器。
- 容器默认使用非 root 的 `agent` 用户运行。
- 项目工作区会挂载到 `/workspace`。

构建时可以覆盖 npm 包名：

```powershell
docker build -t gitlab-agent-sandbox:latest -f docker/sandbox/Dockerfile `
  --build-arg OPENCODE_NPM_PACKAGE=opencode-ai `
  --build-arg CODEX_NPM_PACKAGE=@openai/codex `
  --build-arg GEMINI_NPM_PACKAGE=@google/gemini-cli `
  .
```
