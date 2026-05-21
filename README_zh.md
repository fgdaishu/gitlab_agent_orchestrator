# GitLab Agent Orchestrator 中文说明

GitLab Agent Orchestrator 是一个本地运行的 GitLab Issue 到编码 Agent 的编排服务。它接收 GitLab Issue webhook，识别新添加的 agent 标签，把任务写入 SQLite 队列，启动本地或 Docker 沙箱中的编码 Agent，随后推送分支、创建 Merge Request，并把结果写回 Issue。

最终用户使用流程见 [`docs/user-guide.md`](docs/user-guide.md)。

本仓库同时提供一个可运行的严格模式模板：[`examples/strict-dev-png-sample`](examples/strict-dev-png-sample)。它展示了严格开发项目中推荐的 `project-meta/`、`task-cards/`、`context-packs/`、`contracts/`、`test-oracles/`、handoff 和 report 目录结构。

## 快速开始

1. 安装 Python 依赖：

```powershell
python -m pip install -e ".[dev]"
```

2. 交互式生成 `.env`：

```powershell
.\scripts\init-env.ps1
```

你需要准备：

- GitLab 地址，例如 `https://gitlab.example.com`
- GitLab access token
- GitLab webhook secret
- 可选的 Agent API key，例如 `OPENAI_API_KEY` 或 `GEMINI_API_KEY`

3. 构建项目沙箱镜像：

```powershell
.\docker\sandbox\build.ps1
```

4. 启动 API 和 worker：

```powershell
.\scripts\start.ps1
```

5. 查看运行状态：

```powershell
.\scripts\status.ps1
```

GitLab 项目的 webhook 地址应配置为：

```text
POST http://<orchestrator-host>:8080/gitlab/webhook
```

只需要开启 `Issues events`，并让 webhook secret 与 `.env` 中的 `GITLAB_WEBHOOK_SECRET` 一致。

## Codex Skill

本仓库包含一个 Codex skill，用来教 Codex 安装、配置、运行和排查本服务。

安装到当前用户的 Codex skills 目录：

```powershell
.\scripts\install-skill.ps1
```

之后可以这样向 Codex 提问：

```text
Use the gitlab-agent-orchestrator skill to set up this service for a new GitLab project.
```

## 触发方式

默认测试 Agent 是 `opencode`。给 Issue 添加下面的标签即可排队执行：

```text
agent:opencode
```

当前支持的 Agent 标签：

```text
agent:opencode
agent:codex
agent:gemini
```

## 工作流

任务工作流由 Issue metadata 指定。未指定时使用 `default_coding`。

```markdown
## Agent Metadata

Workflow: strict
Task-ID: PNG-CHUNK-001
```

`default_coding` 是低摩擦的通用开发模式，会根据 Issue、评论、项目规则和依赖 handoff 生成 prompt，并要求 Agent 写出 handoff 后再创建 MR。

`strict` 会映射到 `strict_development`，这是更严格的 task-card 工作流。Agent 启动前会检查：

- `Task-ID` 存在并与 task card 中的 `task_id` 一致。
- `task-cards/<Task-ID>.yaml` 和 `context-packs/<Task-ID>.md` 存在。
- task card 必填字段存在。
- 引用的 contracts 存在。
- `files_allowed` 包含 `.agent/handoffs/` 和 `reports/`。
- Rust 任务如果运行 `cargo`，`files_allowed` 中应包含 `Cargo.lock`。
- 执行环境中存在所需 Agent 和校验工具。

Agent 结束后，`strict_development` 还会继续校验修改文件边界、禁止修改文件、handoff、validation commands 和 validation report。

## Docker 项目沙箱

推荐使用 `docker_project` 后端，让同一个 GitLab 项目的所有任务运行在同一个长期存在的 Docker 容器中：

```env
AGENT_EXECUTION_BACKEND=docker_project
SANDBOX_DOCKER_IMAGE=gitlab-agent-sandbox:latest
```

第一个任务触发时会自动创建名为 `gitlab-agent-project-<project_id>` 的容器。项目工作区保存在 Docker volume 中，并挂载到容器的 `/workspace`。

## 运维命令

运行诊断：

```powershell
.\scripts\doctor.ps1
```

停止服务：

```powershell
.\scripts\stop.ps1
```

查看任务：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>
```

查看 Agent 输出：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>/log
```

取消排队或运行中的任务：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/cancel
```

所有密钥都通过环境变量读取。不要提交 `.env`。可用配置见 `.env.example`。
