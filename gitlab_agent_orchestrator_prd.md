# PRD：基于 GitLab 的本地 Coding Agent 编排系统

## 1. 产品概述

### 1.1 产品名称

暂定名：**GitLab Agent Orchestrator**

### 1.2 产品定位

GitLab Agent Orchestrator 是一个部署在本地或私有服务器中的 coding agent 编排系统。它以自建 GitLab 为任务管理、代码托管、Merge Request、CI/CD 和权限控制中心，通过 Webhook 监听 issue、label、assignee、MR、pipeline 等事件，并调用 Codex、Claude Code、Gemini CLI、OpenCode 等 coding agent 在隔离环境中完成代码任务。

系统目标不是替代 GitLab，而是在 GitLab 之上增加一层 agent 调度与执行能力，使 GitLab 具备类似 Linear + Codex、GitHub Copilot coding agent、Symphony 等工具链的自动化开发能力。

---

## 2. 背景与问题

### 2.1 背景

现有 coding agent 已经可以完成一定程度的代码理解、修改、测试和 PR 生成。但在实际产品开发中，单独使用某一个 agent 仍然存在明显问题：

1. 任务入口分散，通常依赖命令行、IDE、网页或单次对话。
2. 多个 agent 之间缺乏统一调度。
3. 任务状态不可追踪，难以知道 agent 当前在做什么、失败在哪里。
4. 缺少和 issue、MR、CI/CD 的稳定闭环。
5. 复杂项目需要拆分为多个子任务，但 agent 之间的交接成本高。
6. Linear + Codex 等方案虽然体验好，但 Linear 需要付费，且系统可控性有限。
7. 对于本地部署、私有代码库、低成本和高可控性的需求，现有 SaaS 方案不完全合适。

用户已经部署了 GitLab，希望在本地 GitLab 基础上实现类似 Linear + Codex 的 agent 工作流，并进一步扩展为多 coding agent 编排平台。

### 2.2 核心问题

需要解决的问题是：

> 如何让用户在 GitLab issue 中用结构化方式描述任务，然后系统自动调用合适的 coding agent，在隔离环境中完成开发、测试、提交，并通过 Merge Request 进入人工审查流程？

---

## 3. 产品目标

### 3.1 核心目标

1. 以自建 GitLab 作为任务和代码中心。
2. 支持通过 issue label、assignee、状态 label、评论命令等方式触发 agent。
3. 支持 Codex 作为第一阶段 coding agent。
4. 后续扩展支持 Claude Code、Gemini CLI、OpenCode 等其他 agent。
5. 每个任务在独立 sandbox 中运行，避免污染主环境。
6. 自动创建分支、提交代码、运行测试、创建 Merge Request。
7. 将执行状态、日志摘要、错误信息、MR 链接回写到 GitLab issue。
8. 形成“任务创建 → agent 执行 → MR → 人类 review → 继续迭代”的闭环。

### 3.2 长期目标

1. 将 GitLab issue 变成 agent 任务队列。
2. 将 GitLab label/assignee/MR/CI 变成 agent 工作流状态机。
3. 支持多个 coding agent 并行执行不同任务。
4. 支持根据任务类型自动选择最合适的 agent。
5. 支持复杂任务拆解、多层子任务、任务依赖和交接。
6. 最终形成一个本地可控的 agentic software development platform。

---

## 4. 非目标

第一阶段不做以下内容：

1. 不直接替代 GitLab 的 issue/MR/CI/CD 功能。
2. 不做完整项目管理 SaaS。
3. 不直接修改主分支。
4. 不在 webhook 请求内直接运行长时间 agent 任务。
5. 不优先做复杂多 agent 协同推理。
6. 不优先做图形化低代码工作流编辑器。
7. 不优先支持所有 Git 平台，第一阶段只支持 GitLab Self-Managed。

---

## 5. 目标用户

### 5.1 个人开发者

已经本地部署 GitLab，希望用 Codex 等 agent 辅助开发项目，减少重复编码和维护成本。

### 5.2 小型开发团队

有私有代码库，不希望依赖 Linear、GitHub Cloud 或其他 SaaS，希望在本地 GitLab 上实现 agent 自动开发流程。

### 5.3 Agent 产品开发者

希望构建一个多 agent 编排平台，将自然语言任务拆解、分配、执行、测试和交付形成标准化流程。

---

## 6. 核心使用场景

### 场景 1：通过 label 触发 Codex

用户在 GitLab issue 中写明需求，并给 issue 添加 label：

```text
agent:codex
```

系统监听到 label 新增事件后，自动触发 Codex 任务。

执行流程：

```text
Issue 添加 agent:codex
→ GitLab Project Webhook 发送 issue event
→ 后端判断 changes.labels 中是否新增 agent:codex
→ 创建任务记录
→ 将 issue 状态改为 agent:running
→ 创建 sandbox
→ clone repo
→ 创建分支 agent/issue-<iid>
→ 拼接 prompt
→ 调用 codex exec
→ 运行测试
→ push branch
→ 创建 Merge Request
→ issue 添加 agent:review
→ 评论执行总结和 MR 链接
```

### 场景 2：通过 assignee 触发 agent

用户将 issue 分配给 bot 用户：

```text
codex-bot
```

系统监听 assignee 变化，并根据 assignee 判断应该调用哪个 agent。

示例：

```text
codex-bot   → Codex
claude-bot  → Claude Code
gemini-bot  → Gemini CLI
opencode-bot → OpenCode
```

### 场景 3：通过状态 label 触发正式任务

用户将 issue 标记为：

```text
status:ready-for-agent
```

并同时指定：

```text
agent:codex
```

系统只在二者同时满足时触发任务。

这比单独使用 `agent:codex` 更适合正式工作流，因为它可以避免误触发。

### 场景 4：通过评论命令触发临时任务

用户在 issue 或 MR 评论：

```text
/agent codex fix this
/agent codex review
/agent codex add tests
```

系统监听 note events，解析命令，并触发相应 agent。

评论触发适合临时指令，但不作为第一阶段核心入口。

### 场景 5：MR review 自动化

当用户创建 MR 或 MR pipeline failed 时，系统可以调用 Codex 对 MR 做 review 或修复 CI 报错。

流程：

```text
MR created / pipeline failed
→ Webhook 触发
→ Agent 分析 diff 或 CI 日志
→ 评论 review 建议
→ 可选：提交修复 commit
```

---

## 7. MVP 范围

第一阶段只实现最小闭环：

```text
GitLab issue + agent:codex label
→ webhook
→ 后端触发 Codex
→ 创建分支
→ 修改代码
→ 测试
→ 创建 MR
→ 回写 issue
```

### 7.1 MVP 必须包含

1. 创建 `codex-bot` 用户。
2. 创建 `agent:codex` label。
3. 配置 GitLab Project Webhook，监听 Issues events。
4. 后端接收 webhook。
5. 校验 GitLab webhook secret。
6. 判断是否新增 `agent:codex` label。
7. 将任务放入后台队列。
8. 拉取 GitLab issue 内容。
9. 拉取目标仓库。
10. 创建任务分支。
11. 调用 `codex exec`。
12. 收集代码变更。
13. 运行测试或 lint。
14. push 分支到 GitLab。
15. 创建 Merge Request。
16. 在 issue 下评论执行结果。
17. 使用 label 标记状态：`agent:running`、`agent:review`、`agent:failed`。

### 7.2 MVP 暂不包含

1. 多 agent 路由。
2. Web 前端管理界面。
3. 复杂任务拆解。
4. 多轮 agent 协作。
5. 自动合并 MR。
6. 高级权限系统。
7. 分布式 agent worker。
8. 完整日志可视化。

---

## 8. 关键用户流程

### 8.1 用户创建任务

用户在 GitLab 创建 issue：

```markdown
标题：实现登录页面手机号校验

描述：
当前登录页面只校验手机号是否为空，需要增加手机号格式校验。

验收标准：
- 手机号为空时提示“请输入手机号”
- 手机号格式错误时提示“手机号格式不正确”
- 通过现有前端测试
- 不影响邮箱登录逻辑
```

然后添加 label：

```text
agent:codex
```

### 8.2 系统接收任务

后端收到 GitLab webhook 后：

1. 校验 `X-Gitlab-Token`。
2. 判断 `object_kind == issue`。
3. 判断 `changes.labels.previous/current` 中是否新增 `agent:codex`。
4. 检查是否已经存在运行中的任务。
5. 创建任务记录。
6. 将 issue label 从 `agent:codex` 更新为 `agent:running`。

### 8.3 Agent 执行任务

Worker 执行：

1. clone repository。
2. checkout default branch。
3. 创建分支：

```text
agent/issue-<issue_iid>-<short-title>
```

4. 生成 Codex prompt。
5. 调用：

```bash
codex exec "<task prompt>"
```

6. 运行测试：

```bash
npm test
# 或 pytest
# 或根据项目配置自动判断
```

7. commit 变更。
8. push branch。
9. 创建 MR。

### 8.4 回写 GitLab

任务成功后：

1. issue 移除 `agent:running`。
2. issue 添加 `agent:review`。
3. 评论：

```markdown
Codex 已完成任务。

结果：
- 创建分支：agent/issue-23-login-phone-validation
- 创建 MR：!45
- 测试结果：通过

请 review MR。
```

任务失败后：

1. issue 移除 `agent:running`。
2. issue 添加 `agent:failed`。
3. 评论失败原因、日志摘要和下一步建议。

---

## 9. 功能需求

### 9.1 GitLab Webhook Receiver

#### 功能描述

接收 GitLab project webhook 事件，并根据事件类型决定是否触发 agent 任务。

#### 支持事件

MVP：

- Issues events

后续：

- Note events
- Merge request events
- Pipeline events
- Push events

#### 验收标准

1. 能接收 GitLab issue webhook。
2. 能校验 secret token。
3. 非法 token 返回 401。
4. 非目标事件返回 200，但不触发任务。
5. 新增 `agent:codex` label 时触发任务。
6. 仅已有 `agent:codex` 但没有新增时不重复触发。

---

### 9.2 Label Trigger

#### 功能描述

当 issue 被新增 `agent:codex` label 时，系统触发 Codex 任务。

#### 判断逻辑

```text
payload.object_kind == "issue"
AND changes.labels 存在
AND previous labels 不包含 agent:codex
AND current labels 包含 agent:codex
```

#### 验收标准

1. 新增 `agent:codex` 能触发。
2. 删除 `agent:codex` 不触发。
3. 修改标题、描述、其他 label 不触发。
4. 重复保存 issue 不重复触发。

---

### 9.3 Bot 用户管理

#### 功能描述

使用 `codex-bot` 作为 GitLab 中的自动化身份。

#### 权限建议

MVP 推荐：

```text
Developer
```

需要更高权限时再升级到 Maintainer。

#### Token 权限

推荐 scopes：

```text
api
read_repository
write_repository
```

#### 验收标准

1. bot 可以 clone repo。
2. bot 可以 push 非保护分支。
3. bot 可以创建 MR。
4. bot 可以评论 issue。
5. bot 可以修改 issue labels。

---

### 9.4 Task Queue

#### 功能描述

Webhook Receiver 不直接运行 Codex，而是将任务放入后台队列。

#### MVP 方案

可以使用：

```text
Redis + RQ
或 Redis + Celery
或 SQLite + 本地 worker
```

#### 验收标准

1. webhook 请求能快速返回 200。
2. 长任务在 worker 中执行。
3. 支持任务状态记录。
4. 支持失败重试或人工重试。

---

### 9.5 Codex Adapter

#### 功能描述

封装 Codex CLI 调用，负责执行 coding task。

#### 输入

1. 仓库路径。
2. issue 标题。
3. issue 描述。
4. issue 评论。
5. 项目规则文件。
6. 验收标准。
7. 分支信息。

#### 输出

1. 修改后的代码。
2. 执行日志。
3. 测试结果。
4. 总结信息。
5. 错误信息。

#### 调用方式

MVP：

```bash
codex exec "<prompt>"
```

后续可以支持：

```text
codex exec --json
codex exec --sandbox workspace-write
codex exec --approval never
```

具体参数根据本地 Codex CLI 版本确认。

#### 验收标准

1. 可以在指定仓库目录中执行。
2. 可以读取 issue 需求。
3. 可以修改代码。
4. 可以输出执行日志。
5. 执行失败时能返回错误信息。

---

### 9.6 Sandbox 执行环境

#### 功能描述

每个任务必须在隔离环境中运行。

#### MVP 方案

可以先使用本地临时目录：

```text
/workspaces/agent-jobs/<job_id>
```

每个任务独立 clone repo。

#### 推荐正式方案

使用 Docker 容器：

```text
每个 job 一个 container
每个 job 一个 workspace
每个 job 一个临时 token
任务结束后销毁环境
```

#### 验收标准

1. 不直接在主仓库目录中修改代码。
2. 每个任务目录独立。
3. 任务失败不影响其他任务。
4. 能清理旧 workspace。

---

### 9.7 Git 操作模块

#### 功能描述

负责 clone、branch、commit、push。

#### 分支命名

```text
agent/issue-<issue_iid>-<slug>
```

示例：

```text
agent/issue-23-login-phone-validation
```

#### Commit message

```text
feat: implement issue #23 via codex agent
```

#### 验收标准

1. 能 clone 指定项目。
2. 能创建新分支。
3. 能检测是否有代码变更。
4. 能 commit。
5. 能 push 到远程。
6. 如果没有代码变更，应回写 issue 说明原因。

---

### 9.8 Merge Request 创建

#### 功能描述

任务成功后自动创建 MR。

#### MR 标题

```text
[Agent] <issue title>
```

#### MR 描述

包含：

1. 关联 issue。
2. agent 类型。
3. 执行摘要。
4. 测试结果。
5. 人类 review checklist。

示例：

```markdown
## Agent Summary

This MR was generated by Codex based on issue #23.

## Changes

- Added phone number format validation
- Updated error message handling
- Added related tests

## Validation

- npm test: passed

Closes #23
```

#### 验收标准

1. 能通过 GitLab API 创建 MR。
2. MR source branch 正确。
3. MR target branch 正确。
4. MR 描述包含 issue 链接和测试结果。
5. issue 中能看到 MR 链接。

---

### 9.9 Issue 状态回写

#### 功能描述

系统通过 labels 和 comments 回写执行状态。

#### 状态 label

```text
agent:codex
agent:running
agent:review
agent:failed
agent:done
```

#### 状态流转

```text
agent:codex
→ agent:running
→ agent:review
→ agent:done
```

失败：

```text
agent:codex
→ agent:running
→ agent:failed
```

#### 验收标准

1. 任务开始时添加 `agent:running`。
2. 任务开始后移除 `agent:codex`，避免重复触发。
3. 任务成功后添加 `agent:review`。
4. 任务失败后添加 `agent:failed`。
5. 每次状态变化都有评论记录。

---

## 10. 非功能需求

### 10.1 安全性

1. Webhook 必须校验 secret token。
2. bot token 不得写入代码仓库。
3. bot token 通过环境变量或 secret manager 注入。
4. agent 任务不得访问宿主机敏感目录。
5. 每个任务使用独立 workspace。
6. 禁止直接 push protected branch。
7. 默认只允许创建 MR，不允许自动 merge。
8. 高风险命令需要记录日志。
9. 后续应增加命令 allowlist/denylist。

### 10.2 稳定性

1. webhook 接口必须快速返回。
2. agent 长任务必须异步执行。
3. worker 崩溃后任务状态可恢复或可人工重试。
4. 重复 webhook 事件不能导致重复任务。
5. 任务超时后应标记失败。

### 10.3 可观测性

MVP 至少记录：

1. job id。
2. project id。
3. issue iid。
4. trigger type。
5. agent type。
6. start time。
7. end time。
8. status。
9. branch name。
10. MR iid。
11. error message。

后续增加：

1. Web UI。
2. 实时日志流。
3. agent 执行步骤可视化。
4. 任务耗时统计。
5. 成功率统计。

---

## 11. 系统架构

### 11.1 MVP 架构

```text
GitLab Self-Managed
  ├─ Issues
  ├─ Labels
  ├─ Repository
  ├─ Merge Requests
  └─ Project Webhooks

        ↓ Issues Event

Webhook Receiver
  ├─ 校验 GitLab secret
  ├─ 解析 issue event
  ├─ 判断 agent:codex 是否新增
  └─ 写入任务队列

        ↓

Task Worker
  ├─ 读取任务
  ├─ 更新 issue label: agent:running
  ├─ clone repo
  ├─ 创建 branch
  ├─ 调用 Codex Adapter
  ├─ 运行测试
  ├─ commit + push
  ├─ 创建 MR
  └─ 回写 issue

        ↓

Codex Adapter
  └─ codex exec
```

### 11.2 长期架构

```text
GitLab / Linear / GitHub Issues
        ↓
Issue Adapter Layer
        ↓
Agent Orchestrator
  ├─ Task Router
  ├─ State Machine
  ├─ Permission Manager
  ├─ Context Builder
  ├─ Sandbox Manager
  ├─ Log Manager
  └─ Result Reporter
        ↓
Agent Adapter Layer
  ├─ Codex Adapter
  ├─ Claude Code Adapter
  ├─ Gemini CLI Adapter
  ├─ OpenCode Adapter
  └─ Custom Agent Adapter
        ↓
Execution Layer
  ├─ Docker
  ├─ VM
  ├─ Git worktree
  ├─ CI runner
  └─ Secret manager
        ↓
Git Provider
  ├─ Branch
  ├─ Commit
  ├─ MR / PR
  └─ Review
```

---

## 12. 数据模型

### 12.1 Job

```json
{
  "id": "job_001",
  "project_id": 123,
  "project_path": "group/project",
  "issue_iid": 23,
  "issue_title": "实现手机号校验",
  "trigger_type": "label_added",
  "trigger_label": "agent:codex",
  "agent": "codex",
  "status": "running",
  "branch": "agent/issue-23-phone-validation",
  "merge_request_iid": null,
  "created_at": "2026-05-13T00:00:00Z",
  "started_at": "2026-05-13T00:01:00Z",
  "finished_at": null,
  "error": null
}
```

### 12.2 Job Status

```text
pending
running
succeeded
failed
cancelled
```

### 12.3 Agent Type

```text
codex
claude-code
gemini-cli
opencode
custom
```

---

## 13. Prompt 构建规则

### 13.1 Codex Prompt 基本结构

```markdown
You are working in a GitLab repository.

Task source:
- Project: <project_path>
- Issue: #<issue_iid>
- Title: <issue_title>

Issue description:
<issue_description>

Acceptance criteria:
<acceptance_criteria>

Relevant comments:
<comments>

Rules:
- Do not modify unrelated files.
- Do not commit secrets.
- Prefer small, reviewable changes.
- Run available tests if possible.
- If the task is ambiguous, make the smallest reasonable implementation and document assumptions.
- Do not push directly to main/master.

Expected output:
- Implement the requested change.
- Add or update tests when appropriate.
- Provide a concise summary of changes.
```

### 13.2 项目规则文件

支持从仓库读取：

```text
CODEX.md
AGENTS.md
CONTRIBUTING.md
README.md
```

优先级：

```text
AGENTS.md > CODEX.md > CONTRIBUTING.md > README.md
```

---

## 14. API 设计草案

### 14.1 Webhook Endpoint

```http
POST /gitlab/webhook
```

请求头：

```text
X-Gitlab-Token: <secret>
```

返回：

```json
{
  "ok": true,
  "triggered": true,
  "job_id": "job_001"
}
```

### 14.2 Job 查询

```http
GET /jobs/:id
```

返回：

```json
{
  "id": "job_001",
  "status": "running",
  "agent": "codex",
  "issue_iid": 23,
  "branch": "agent/issue-23-phone-validation"
}
```

### 14.3 Job 重试

```http
POST /jobs/:id/retry
```

### 14.4 Job 取消

```http
POST /jobs/:id/cancel
```

---

## 15. 权限与安全策略

### 15.1 GitLab 权限

MVP：

```text
codex-bot: Developer
```

权限允许：

1. clone repo。
2. push 非保护分支。
3. 创建 MR。
4. 评论 issue。
5. 修改 labels。

权限禁止：

1. push protected branch。
2. merge protected branch。
3. 修改项目关键设置。

### 15.2 Token 管理

环境变量：

```bash
GITLAB_URL="https://gitlab.example.com"
GITLAB_TOKEN="glpat_xxx"
GITLAB_WEBHOOK_SECRET="random-secret"
OPENAI_API_KEY="sk-xxx"
```

要求：

1. 不提交 `.env`。
2. 不在日志中打印 token。
3. 生产环境使用 secret manager。
4. token 定期轮换。

### 15.3 Sandbox 权限

MVP：

1. 每个任务单独目录。
2. 限制工作目录。
3. 任务结束后清理。

正式版：

1. 每个任务单独容器。
2. 只挂载必要目录。
3. 限制网络访问。
4. 限制 CPU/内存。
5. 设置任务超时。

---

## 16. 失败处理

### 16.1 常见失败类型

1. webhook token 校验失败。
2. GitLab API 调用失败。
3. clone repo 失败。
4. branch 已存在。
5. Codex 执行失败。
6. 没有产生代码变更。
7. 测试失败。
8. push 失败。
9. 创建 MR 失败。
10. worker 超时或崩溃。

### 16.2 失败回写格式

```markdown
Codex 任务失败。

Issue: #23
阶段：运行测试
错误摘要：npm test failed

建议：
- 检查测试日志
- 修改 issue 描述后重新添加 agent:codex
- 或手动触发 retry
```

### 16.3 重试机制

MVP：

1. 人工移除 `agent:failed`。
2. 重新添加 `agent:codex`。
3. 系统再次触发。

后续：

1. 提供 `/agent retry` 评论命令。
2. 提供 Web UI retry 按钮。
3. 自动重试部分临时错误。

---

## 17. 里程碑

### Milestone 1：Webhook 触发 MVP

目标：跑通 `agent:codex` label 触发。

任务：

1. 创建 codex-bot 用户。
2. 创建 agent labels。
3. 配置 project webhook。
4. 实现 FastAPI webhook receiver。
5. 判断 label 新增。
6. 打印触发日志。

验收：

添加 `agent:codex` 后，后端能正确识别并输出触发信息。

---

### Milestone 2：任务队列与状态回写

目标：将 webhook 事件变为异步 job。

任务：

1. 引入 Redis/RQ 或 SQLite job queue。
2. 创建 job 数据表。
3. 任务开始时添加 `agent:running`。
4. 任务结束时添加 `agent:review` 或 `agent:failed`。
5. issue 评论执行摘要。

验收：

GitLab issue 能展示任务状态变化。

---

### Milestone 3：Codex 执行与 MR 创建

目标：Codex 自动修改代码并创建 MR。

任务：

1. 实现 Git clone。
2. 创建任务分支。
3. 构建 Codex prompt。
4. 调用 `codex exec`。
5. 检测代码变更。
6. commit + push。
7. 创建 MR。
8. 回写 MR 链接。

验收：

issue 添加 `agent:codex` 后，系统自动创建 MR。

---

### Milestone 4：安全隔离与稳定性

目标：提升执行安全性。

任务：

1. 每个任务独立 workspace。
2. 任务超时控制。
3. 日志保存。
4. 防重复触发。
5. token 脱敏。
6. 可清理旧任务目录。

验收：

多个任务并行执行时互不影响，失败不会污染环境。

---

### Milestone 5：多 Agent Adapter

目标：从 Codex 扩展到更多 coding agent。

任务：

1. 抽象 Agent Adapter 接口。
2. 增加 Claude Code Adapter。
3. 增加 Gemini CLI Adapter。
4. 增加 OpenCode Adapter。
5. 通过 label 或 assignee 选择 agent。

验收：

不同 label 可以触发不同 agent：

```text
agent:codex
agent:claude
agent:gemini
agent:opencode
```

---

## 18. 成功指标

### MVP 指标

1. issue label 触发成功率 ≥ 95%。
2. webhook 平均响应时间 < 1 秒。
3. 任务状态回写成功率 ≥ 95%。
4. 能成功创建 MR。
5. 不发生重复触发导致的重复 MR。

### 长期指标

1. agent 任务成功完成率。
2. MR 被接受比例。
3. 人工修改 agent 生成代码的比例。
4. 平均任务完成时间。
5. 平均节省人工时间。
6. 测试通过率。
7. 失败原因分布。
8. 不同 agent 在不同任务类型上的表现。

---

## 19. 风险与应对

### 风险 1：Agent 生成代码质量不稳定

应对：

1. 强制走 MR review。
2. 强制运行测试。
3. 限制每次变更范围。
4. 完善 issue 模板和验收标准。

### 风险 2：Webhook 重复触发

应对：

1. 只在 label 新增时触发。
2. 任务开始后移除 `agent:codex`。
3. 使用 job 去重键：`project_id + issue_iid + trigger_label + event_time`。

### 风险 3：权限过大导致安全问题

应对：

1. bot 只给 Developer。
2. 不允许 push protected branch。
3. 不自动 merge。
4. token 最小权限。
5. 后续使用 project access token 替代 personal access token。

### 风险 4：Codex 执行长任务卡死

应对：

1. 设置任务超时。
2. worker watchdog。
3. 失败后回写 issue。
4. 支持人工 retry。

### 风险 5：任务描述不清晰

应对：

1. 提供 issue 模板。
2. 要求验收标准。
3. agent 不确定时只做最小合理实现。
4. 对模糊任务回写澄清问题，而不是盲目大改。

---

## 20. Issue 模板建议

```markdown
## 任务背景

请说明为什么需要这个改动。

## 具体需求

请描述需要实现什么。

## 验收标准

- [ ] 标准 1
- [ ] 标准 2
- [ ] 标准 3

## 影响范围

可能涉及的模块或文件：

## 不希望修改的内容

请列出 agent 不应该碰的部分。

## 测试要求

请说明需要运行哪些测试。
```

---

## 21. 第一版推荐技术栈

### 后端

```text
Python + FastAPI
```

### 队列

MVP：

```text
SQLite + background worker
```

更稳：

```text
Redis + RQ / Celery
```

### GitLab API

```text
python-gitlab
或 requests 直接调用 REST API
```

### Agent 执行

```text
Codex CLI
```

### 隔离环境

MVP：

```text
本地临时 workspace
```

正式版：

```text
Docker container
```

---

## 22. 最小实现顺序

推荐按这个顺序开发：

```text
1. 创建 codex-bot 和 agent:codex label
2. 配置 GitLab project webhook
3. FastAPI 接收 webhook
4. 判断是否新增 agent:codex
5. 创建 job 记录
6. 回写 agent:running
7. clone repo + branch
8. 构建 prompt
9. codex exec
10. git diff 检查
11. commit + push
12. 创建 MR
13. 回写 agent:review / agent:failed
14. 增加 sandbox 和日志
15. 抽象多 agent adapter
```

---

## 23. 产品判断

这个产品的核心价值不在于“让 Codex 能写代码”，而在于：

1. 把自然语言需求变成标准化 agent 任务。
2. 把 GitLab issue 变成 agent 可消费的任务队列。
3. 把 agent 执行过程变成可追踪、可回滚、可 review 的工程流程。
4. 把单个 coding agent 封装成可替换的 adapter。
5. 把复杂产品开发拆解成多个小任务，并让 agent 在清晰边界内完成。

最终目标是形成一个本地可控、低成本、可扩展的 agentic development workflow。

