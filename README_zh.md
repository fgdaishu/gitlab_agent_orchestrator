# GitLab Agent Orchestrator

本地 GitLab 问题到智能体的编排器。该 MVP 接收 GitLab Issue 的 Webhook，检测新添加的智能体标签，在 SQLite 中排队任务，运行编码智能体，推送分支，创建合并请求，并将结果写回 Issue。

## 快速开始

1. 安装 Python 依赖：

```powershell
python -m pip install -e ".[dev]"
```

2. 交互式创建 `.env`：

```powershell
.\scripts\init-env.ps1
```

你需要准备：

- GitLab URL，例如 `http://<gitlab-host>/gitlab`
- GitLab 访问令牌
- GitLab Webhook 密钥
- 可选的智能体 API 密钥，如 `OPENAI_API_KEY` 或 `GEMINI_API_KEY`

3. 构建项目沙箱镜像：

```powershell
.\docker\sandbox\build.ps1
```

4. 在后台启动 API 和 Worker：

```powershell
.\scripts\start.ps1
```

5. 检查状态：

```powershell
.\scripts\status.ps1
```

配置 GitLab 项目 Webhook，调用地址为：

```text
POST http://<orchestrator-host>:8080/gitlab/webhook
```

启用 `Issues events` 并将 Webhook 密钥设置为与 `GITLAB_WEBHOOK_SECRET` 相同的值。

对于 GitLab.com，请先通过公共 HTTPS URL 或隧道公开编排器 API，然后再配置 Webhook。

## Codex 技能

本仓库包含一个 Codex 技能，用于指导 Codex 如何安装、配置、操作和排查此服务。

安装到当前用户的 Codex 技能目录：

```powershell
.\scripts\install-skill.ps1
```

然后向 Codex 提问，例如：

```text
使用 gitlab-agent-orchestrator 技能为一个新的 GitLab 项目设置此服务。
```

## MVP 触发

默认测试智能体是 `opencode`，因此添加以下 Issue 标签即可排队任务：

```text
agent:opencode
```

适配器层支持以下标签：

```text
agent:opencode
agent:codex
agent:gemini
```

Worker 将它们映射到本地 CLI 命令：

```text
OPENCODE_COMMAND=opencode
CODEX_COMMAND=codex
GEMINI_COMMAND=gemini
```

推荐的默认值为 `AGENT_EXECUTION_BACKEND=docker_project`。在传统的 `local` 后端中，每个 GitLab Issue 使用持久化工作区：

```text
workspaces/project-<project_id>/issue-<issue_iid>/repo
```

再次运行同一 Issue 会复用相同的本地克隆、相同的分支以及现有的合并请求。新的 Issue 评论将作为增量指令包含在下一个提示中。

## Docker 项目沙箱

设置以下环境变量，使同一 GitLab 项目的所有任务在同一个长期运行的 Docker 容器内执行：

```env
AGENT_EXECUTION_BACKEND=docker_project
SANDBOX_DOCKER_IMAGE=gitlab-agent-sandbox:latest
```

项目的第一个触发 Issue 会自动创建并初始化一个名为以下内容的容器：

```text
gitlab-agent-project-<project_id>
```

项目工作区存储在 Docker 命名卷中，并挂载到容器的 `/workspace` 目录：

```text
gitlab-agent-project-<project_id>-workspace
  挂载于 /workspace
  repo/
  issues/issue-<issue_iid>/
  cache/
  logs/
```

在 `docker_project` 模式下，Git 操作、智能体执行和验证均通过 `docker exec` 在容器内部运行。仓库文件不会同步回 Windows 主机；更改会从容器内部推送到 GitLab。MVP 保持项目级锁定，因此每个项目一次只能运行一个任务。

沙箱镜像必须包含你要使用的工具，例如 `git`、`node`、`python`、`opencode`、`codex` 和 `gemini`。项目特定设置可通过以下环境变量配置：

```env
SANDBOX_BOOTSTRAP_VERSION=1
SANDBOX_BOOTSTRAP_COMMAND=:
SANDBOX_OPENCODE_MODEL=opencode/big-pickle
SANDBOX_PASS_ENV=OPENAI_API_KEY,ANTHROPIC_API_KEY,GEMINI_API_KEY,GOOGLE_API_KEY,GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_GENAI_USE_GCA
```

`docker/sandbox` 中提供了可供构建的基础镜像：

```powershell
.\docker\sandbox\build.ps1
```

沙箱管理 API：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/projects/<project_id>/sandbox
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/restart
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/stop
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/rebuild
```

需要 OAuth 的智能体（如 Codex）必须在项目沙箱内登录一次。如果任务检测到 Codex 未认证，它会写入一条 GitLab Issue 评论，内容类似于：

```powershell
docker exec -it gitlab-agent-project-<project_id> codex login --device-auth
```

你也可以直接查询命令：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/projects/<project_id>/sandbox/agents/codex/login-command
```

Gemini 使用交互式认证选择器或环境变量。在当前项目沙箱流程中已验证 OAuth 可用。如果 Gemini 未认证，Issue 评论将显示：

```powershell
docker exec -it gitlab-agent-project-<project_id> gemini
```

如果 Gemini OAuth 重定向到其他环境中不可访问的本地主机回调，请优先使用 API 密钥或 Vertex 配置：

```env
GEMINI_API_KEY=...
SANDBOX_PASS_ENV=GEMINI_API_KEY,GOOGLE_API_KEY,GOOGLE_GENAI_USE_VERTEXAI,GOOGLE_GENAI_USE_GCA
```

## 运维

运行预检查：

```powershell
.\scripts\doctor.ps1
```

停止由 `scripts\start.ps1` 启动的服务：

```powershell
.\scripts\stop.ps1
```

查看任务：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>
```

查看智能体输出：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>/log
```

取消排队中或运行中的任务：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/cancel
```

## 配置

所有密钥均从环境变量读取。请勿提交 `.env`。

有关可用设置，请参见 `.env.example`。
