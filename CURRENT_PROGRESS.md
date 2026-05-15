# GitLab Agent Orchestrator 当前进展

更新时间：2026-05-15

## 当前目标

基于 PRD 已实现一个 GitLab coding agent 编排 MVP。当前以 GitLab issue label 作为稳定触发入口，支持 `opencode`、`codex`、`gemini` CLI adapter，并已启用 project 级长期 Docker sandbox 执行后端。

## 已实现功能

### Project 级 Docker Sandbox 后端

当前推荐执行后端：

```env
AGENT_EXECUTION_BACKEND=docker_project
```

`docker_project` 后端当前实现：

- 每个 GitLab project 一个长期 Docker 容器，命名为 `gitlab-agent-project-<project_id>`。
- 每个 GitLab project 一个 Docker named volume，命名为 `gitlab-agent-project-<project_id>-workspace`。
- project workspace 通过 named volume 挂载到容器 `/workspace`，不再使用 Windows bind mount。
- project repo 位于：

```text
/workspace/repo
```

- issue 运行记录位于：

```text
/workspace/issues/issue-<issue_iid>
```

- git clone/fetch/checkout/commit/push、agent 执行、validation 都通过 `docker exec` 在容器内执行。
- repo 文件不再同步回宿主机；代码变更只通过容器内 `git push` 同步到 GitLab。
- 宿主机仍保留 job 控制文件和 agent 日志，便于 cancel 和 `GET /jobs/{job_id}/log`。
- 新增 `project_sandboxes` 表记录容器状态、镜像、bootstrap version、last used 和错误信息。
- `jobs` 表新增 `sandbox_id` 和 `workspace_path`。
- worker claim job 时增加 project-level lock，同一 project 已有 running job 时不会再 claim 该 project 的 pending job。
- Codex 在执行前会检查 `codex login status`；未登录时 job 失败并在 issue comment 中提示用户执行：

```powershell
docker exec -it gitlab-agent-project-<project_id> codex login --device-auth
```

- Gemini 在执行前会检查 sandbox 内是否有 Gemini 配置或 `GEMINI_API_KEY` / Vertex 相关环境变量；未配置时 job 失败并在 issue comment 中提示用户执行：

```powershell
docker exec -it gitlab-agent-project-<project_id> gemini
```

Gemini OAuth 已在当前 sandbox 模式下验证可用。若某些环境中仍遇到 Docker 内 localhost callback 不可访问，也可以改用 `GEMINI_API_KEY` 或 Vertex 环境变量，并通过 `SANDBOX_PASS_ENV` 传入。

- Gemini 认证检查已修正：不再把 `/home/agent/.gemini` 下任意文件误判为已认证；当前只认明确的 OAuth 凭据、可识别的 settings 配置，或透传的 Gemini/Vertex 环境变量。
- GitLab REST client 已禁用 urllib 环境代理，避免宿主机 `HTTP_PROXY` / `HTTPS_PROXY` 指向无效代理时导致 issue comment 或 label 回写失败。

- 新增 sandbox 管理 API：

```text
GET  /projects/{project_id}/sandbox
POST /projects/{project_id}/sandbox/restart
POST /projects/{project_id}/sandbox/rebuild
POST /projects/{project_id}/sandbox/stop
GET  /projects/{project_id}/sandbox/agents/{agent}/login-command
```

### Sandbox 基础镜像

已新增并成功构建基础镜像：

```text
gitlab-agent-sandbox:latest
```

镜像定义位于：

```text
docker/sandbox/Dockerfile
docker/sandbox/build.ps1
docker/sandbox/README.md
```

镜像包含：

- Git
- Node.js / npm
- Python 3 / venv / pip
- ripgrep
- build-essential
- OpenCode CLI：`opencode`
- Codex CLI：`codex`
- Gemini CLI：`gemini`

构建命令：

```powershell
.\docker\sandbox\build.ps1
```

已做运行验证：

```text
git --version
node --version
python3 --version
command -v opencode
command -v codex
command -v gemini
```

均通过。注意：镜像不包含 GitLab token、模型 API key 或 CLI 登录态，运行时仍应通过 `.env` 的 `SANDBOX_PASS_ENV` 注入必要环境变量。

已验证 Windows bind mount 会导致 OpenCode 在 VCS 初始化后卡住；改为 Docker named volume 后，同一 repo、同一 prompt、同一 `opencode/big-pickle` 能正常执行。另一个关键修复是：只有需要 stdin 的 agent 才对 `docker exec` 使用 `-i`，OpenCode 不再带 `-i`。

OpenCode sandbox 执行已支持显式模型配置：

```env
SANDBOX_OPENCODE_MODEL=opencode/big-pickle
```

未指定模型时，OpenCode 可能进入默认认证/模型选择路径，在非交互容器里表现为长时间 running。

### 新用户安装脚本与 Codex Skill

已新增仓库内 Codex skill：

```text
skills/gitlab-agent-orchestrator/
```

用途是让新用户可以直接要求 Codex 安装、配置、启动、诊断本服务。安装到当前用户 Codex skills 目录：

```powershell
.\scripts\install-skill.ps1
```

已新增运维脚本：

```text
scripts/init-env.ps1      交互式生成 .env
scripts/doctor.ps1        检查 Python/Git/Docker/.env/镜像/API 健康状态
scripts/start.ps1         后台启动 API 与 worker
scripts/status.ps1        查看服务与 Docker sandbox 状态
scripts/stop.ps1          停止由 start.ps1 启动的 API 与 worker
scripts/install-skill.ps1 安装仓库内 Codex skill
```

### Webhook 与触发

- FastAPI 服务入口：`POST /gitlab/webhook`
- 校验 `X-Gitlab-Token`
- 当前只保留 issue label 触发
- 支持 label：
  - `agent:opencode`
  - `agent:codex`
  - `agent:gemini`
- 已关闭 GitLab hook 的 `note_events`
- GitLab hook 当前应只开启：
  - `issues_events: true`
  - `note_events: false`

### Job 队列与状态

- 使用 SQLite 保存 job
- job 状态：
  - `pending`
  - `running`
  - `succeeded`
  - `failed`
  - `cancelled`
- API：
  - `GET /jobs/{job_id}`
  - `POST /jobs/{job_id}/retry`
  - `POST /jobs/{job_id}/cancel`
  - `GET /jobs/{job_id}/log`

### GitLab 回写

- 任务开始时：
  - 移除触发 label，例如 `agent:opencode`
  - 添加 `agent:running`
  - 写入开始 comment
- 成功时：
  - 添加 `agent:review`
  - 创建或复用 MR
  - 写入 branch / MR / validation comment
- 失败时：
  - 添加 `agent:failed`
  - 写入错误摘要

### Workspace 策略

已经从“每个 job 一个 workspace”改成“每个 issue 一个持久 workspace”：

```text
workspaces/project-<project_id>/issue-<issue_iid>/repo
```

同一个 issue 再次执行时：

- 复用同一个本地 clone
- 复用同一个分支
- 复用已有 MR
- 在已有分支基础上增量执行

### 分支与 MR

分支格式：

```text
agent/issue-<issue_iid>-<slug>
```

重复执行时：

- 如果远端分支存在，checkout 到 `origin/<branch>`
- push 被拒时会尝试 `fetch + pull --rebase + push`
- 如果已有 open MR，会复用 MR，不重复创建

### Agent Adapter

当前支持：

```text
agent:opencode -> opencode run
agent:codex    -> codex exec
agent:gemini   -> gemini --yolo --prompt
```

`.env` 当前命令路径：

```text
OPENCODE_COMMAND=C:\Users\admin\AppData\Roaming\npm\opencode.cmd
CODEX_COMMAND=C:\Users\admin\.local\bin\codex.cmd
GEMINI_COMMAND=C:\Users\admin\AppData\Roaming\npm\gemini.cmd
```

## 已解决的问题

### GitLab 权限问题

早期 `develop/just4test` 项目失败：

```text
404 Project Not Found
```

原因是 `bot0` token 对该项目无权限。后续测试改用 `bot0/just4test`，项目 ID 为 `28`。

### 创建 issue 时自带 label 不触发

已修复。现在 GitLab issue 创建 webhook 如果 `object_attributes.labels` 中包含 agent label，也会触发。

### 同一 issue 重复执行 push rejected

已修复。重复执行会复用 issue workspace 和远端分支，push 前后可处理 rebase。

### Agent 自己 commit/push 导致误判无变更

已修复。prompt 中明确禁止 agent 自己执行：

```text
git commit
git push
```

worker 也能识别：

- agent 留下未提交变更
- agent 自己已经提交 commit
- 没有新变更但已有 MR 可复用

### Codex 命令行太长

已修复。`codex exec` 改为：

```text
codex exec ... -
```

通过 stdin 传 prompt，避免 Windows 命令行长度限制。

### Codex 输出导致 stdout pipe 阻塞

已修复。agent 输出改为实时写入：

```text
workspaces/project-<id>/issue-<iid>/repo/.git/agent-output.log
```

job 完成后复制记录到：

```text
workspaces/project-<id>/issue-<iid>/logs/<job_id>.log
```

### Codex 每次启动 5 次 reconnect

原因：Codex 子进程继承了坏代理环境变量：

```text
HTTP_PROXY=http://127.0.0.1:9
HTTPS_PROXY=http://127.0.0.1:9
ALL_PROXY=http://127.0.0.1:9
GIT_HTTP_PROXY=http://127.0.0.1:9
GIT_HTTPS_PROXY=http://127.0.0.1:9
CODEX_SANDBOX_NETWORK_DISABLED=1
```

已做两层修复：

1. orchestrator 启动 agent 子进程时会清理这些变量。
2. 新建全局 wrapper：

```text
C:\Users\admin\.local\bin\codex.cmd
```

该 wrapper 会清理坏代理变量后调用真正的：

```text
%APPDATA%\npm\codex.cmd
```

并且已把 `C:\Users\admin\.local\bin` 放到用户 PATH 最前面。

## 当前运行状态

最近一次记录：

```text
API wrapper PID: 19948
worker wrapper PID: 32584
```

如果进程已变化，以实际 `Get-Process` 为准。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/healthz
```

## 手动测试方式

### 触发任务

在 GitLab issue 上操作 label：

1. 移除旧状态 label：
   - `agent:review`
   - `agent:failed`
   - `agent:running`
2. 添加一个 agent label：
   - `agent:opencode`
   - `agent:codex`
   - `agent:gemini`

### 查询最近 jobs

```powershell
python -B -c "from orchestrator.config import settings; from orchestrator.db import JobStore; s=JobStore(settings.database_path); c=s.connect(); rows=c.execute('select id,issue_iid,agent,status,branch,merge_request_iid,error from jobs order by created_at desc limit 10').fetchall(); import json; print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))"
```

### 查看单个 job

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>
```

### 查看日志

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>/log
```

### 取消 job

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/cancel
```

### 重试 job

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/retry
```

## 已知限制

- 当前只有单 worker；不同 project 可以通过 project-level lock 避免互相抢同一容器，但整体并发能力还未扩展。
- comment trigger 已移除，当前只使用 label 触发。
- Codex/Gemini 依赖 project sandbox 内的 CLI 登录状态、网络和模型配置；认证状态需要在对应 project 容器内完成一次初始化。
- 当前 GitLab API retry 只是基础重试；已禁用环境代理污染，但 GitLab 服务临时不可达仍可能导致 job failed。
- job cancel 通过 cancel file + taskkill，Windows 下仍可能残留子进程，需要继续加固。

## 重要文件

```text
orchestrator/main.py          FastAPI API
orchestrator/webhook.py       GitLab issue label trigger
orchestrator/db.py            SQLite job store
orchestrator/worker.py        worker 主流程
orchestrator/agent.py         opencode/codex/gemini adapters
orchestrator/git_ops.py       clone/branch/commit/push
orchestrator/gitlab_client.py GitLab REST client
orchestrator/prompt.py        prompt 构建
.env                          本地真实配置，不提交
.env.example                  配置模板
README.md                     使用说明
```

## 下一步计划

### 1. Project 级长期 Docker Sandbox 后续增强

Project 级长期 Docker sandbox 已落地。当前模式是每个 GitLab project 一个长期 Docker 容器，同一个 project 的后续 issue 复用这个容器、依赖缓存、repo 和基础配置。后续重点是完善可观测性、认证初始化体验、并发控制和容器生命周期管理。

建议模型：

```text
GitLab Project
  -> Project Sandbox Container
      -> /workspace
          -> repo
          -> issues/
              -> issue-<iid>/
          -> cache/
          -> logs/
```

宿主机持久目录：

```text
workspaces/project-<project_id>/
  container.json
  repo/
  issues/
    issue-<iid>/
      prompt.md
      agent.log
      run.json
  cache/
  logs/
```

容器命名建议：

```text
gitlab-agent-project-<project_id>
```

### 2. 自动创建和初始化容器

不要强制“第一个 issue 必须是初始化 issue”。任意 issue 被 label 触发时都执行：

1. 检查 project container 是否存在。
2. 不存在则创建并启动。
3. 检查基础环境是否 ready。
4. 不 ready 则执行 bootstrap。
5. 再执行当前 issue job。

可选保留一个显式初始化 label：

```text
agent:init
```

但它只作为手动初始化入口，不作为唯一入口。

### 3. 新增 sandbox 状态表

新增 `project_sandboxes` 表，避免只依赖 Docker 查询状态：

```text
project_sandboxes
  id
  project_id
  project_path
  container_name
  image
  status: missing | creating | bootstrapping | ready | unhealthy | stopped | failed
  created_at
  updated_at
  last_used_at
  bootstrap_version
  error
```

`jobs` 表新增或关联：

```text
jobs.sandbox_id
jobs.workspace_path
```

### 4. 容器执行方式

长期容器不使用每次 `docker run` 的模型，而是：

```text
docker start gitlab-agent-project-<project_id>
docker exec gitlab-agent-project-<project_id> <agent command>
```

worker 主流程调整为：

```text
receive issue label
  -> ensure_project_sandbox(project)
  -> ensure_repo(project)
  -> prepare_issue_branch(issue)
  -> docker exec agent command in /workspace/repo
  -> validate
  -> commit/push/MR
```

第一版建议把 clone/fetch/branch/commit/push 也统一放在容器里执行，避免宿主机 git 状态和容器内 agent 修改状态割裂。

### 5. 并发策略

MVP 阶段建议：

```text
一个 project 一个容器
一个 project 同时只运行一个 job
一个 issue 一个 branch
一个 issue 一个持久目录
```

也就是先做 project-level lock，避免多个 issue 同时改同一个 repo 工作区。

后续再升级为：

```text
/workspace/issues/issue-4/repo
/workspace/issues/issue-5/repo
```

每个 issue 使用独立 clone 或 git worktree，从而支持同 project 内多 issue 并发。

### 6. 基础环境与 bootstrap

分两层：

1. 基础镜像：
   - Python
   - Node
   - Git
   - GitLab CA / 网络配置
   - opencode / codex / gemini CLI
   - 常用构建工具
2. project bootstrap：
   - clone repo
   - 检测项目类型
   - 安装项目依赖
   - 写入 agent 配置
   - 记录 `bootstrap_version`

可通过配置控制版本：

```env
SANDBOX_BOOTSTRAP_VERSION=1
```

当代码中的 bootstrap version 高于容器记录版本时，重新执行 project bootstrap。

### 7. 安全边界

长期容器默认要求：

- 使用非 root 用户运行。
- 只挂载当前 project 的 workspace。
- 不挂载 Docker socket。
- 不挂载宿主机 SSH key。
- GitLab token 不写入镜像和 repo，只在执行时通过 env 或只读 secret 文件注入。
- 默认限制网络，只开放 GitLab 和 agent 必需服务。
- 每个 job 有 timeout。
- 每个 job 可 cancel。
- 定期清理长期未使用容器。

### 8. Sandbox 管理 API

建议新增：

```text
GET  /projects/{project_id}/sandbox
POST /projects/{project_id}/sandbox/restart
POST /projects/{project_id}/sandbox/rebuild
POST /projects/{project_id}/sandbox/stop
```

GitLab comment 回写时可以包含：

```text
Agent job started.
Sandbox: gitlab-agent-project-<project_id>
Log: http://<orchestrator>/jobs/<job_id>/log
```

### 9. 实施顺序

第一阶段：

1. 新增 `AGENT_EXECUTION_BACKEND=local|docker_project` 配置，默认保持 `local`。
2. 新增 `DockerProjectSandbox` executor。
3. 新增 `project_sandboxes` 表和 project-level lock。
4. 支持自动创建、启动、bootstrap project 容器。
5. agent 命令通过 `docker exec` 在 `/workspace/repo` 执行。
6. 保留现有 label 触发、MR、comment、日志逻辑。

第二阶段：

1. 增加 sandbox 健康检查。
2. 增加 restart/rebuild/stop API。
3. 增加 bootstrap version 自动升级。
4. 增强容器日志和 agent 实时日志。
5. 引入 per-issue worktree，支持同 project 多 issue 并发。

### 10. 其他增强项

1. 给 GitLab API 操作补更完整的 retry/backoff。
2. 增加 Web UI 或简单 dashboard 查看 running job、日志、取消按钮。
3. 对 agent adapters 增加 capability check，例如启动前检测 CLI 是否可用、是否已登录。
4. 对 Codex/Gemini 的命令参数继续做实测和配置化。
5. 增加 job event 表，记录 clone/agent/validation/push/MR 各阶段耗时。
6. 增加 webhook payload 调试日志，但注意脱敏 token。
