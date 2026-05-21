# GitLab Agent Orchestrator 用户使用说明

## 1. 服务用途

GitLab Agent Orchestrator 用于把 GitLab issue 转换成自动化 agent 开发任务。

基本流程：

```text
创建 GitLab issue
-> 添加 agent label
-> GitLab webhook 调用 orchestrator
-> orchestrator 创建 job
-> worker 在 sandbox 中运行 agent
-> agent 修改代码并写 handoff
-> orchestrator 校验、提交分支、创建 MR
-> 回写 issue label 和 comment
```

当前支持两种 workflow：

- `default_coding`：默认开发模式，适合低摩擦普通开发。
- `strict_development`：严格开发模式，适合有任务卡、文件边界、验证命令和审计要求的开发。

## 2. 触发方式

给 issue 添加 agent label 会触发任务。

支持的 label：

```text
agent:opencode
agent:codex
agent:gemini
```

当前推荐先使用：

```text
agent:opencode
```

## 3. 默认开发模式

不写 `Workflow` 时，默认使用 `default_coding`。

适合：

- 普通 bugfix
- 小功能
- 文档修改
- 维护任务
- 不需要强文件边界的任务

issue 示例：

```md
Fix the parser so it rejects empty input.

Please add or update tests if needed.
```

然后添加 label：

```text
agent:opencode
```

成功后 issue 会进入：

```text
agent:review
```

失败时进入：

```text
agent:failed
```

## 4. 严格开发模式

严格开发模式使用：

```md
Workflow: strict
```

它要求 repo 内存在结构化任务材料：

```text
task-cards/<Task-ID>.yaml
context-packs/<Task-ID>.md
contracts/...
.agent/handoffs/
reports/
```

适合：

- 安全敏感改动
- 高风险模块
- 需要强审计的任务
- 分阶段任务
- 需要限制可修改文件的任务

issue 示例：

```md
## Agent Metadata

Workflow: strict

Task-ID: PNG-SIGNATURE-001

## Request

Validate the PNG signature module against the task card.

Follow `task-cards/PNG-SIGNATURE-001.yaml` and `context-packs/PNG-SIGNATURE-001.md`.

Do not expand the scope beyond signature validation.
```

然后添加 label：

```text
agent:opencode
```

成功后 issue 会进入：

```text
strict:review
```

失败时进入：

```text
strict:validation-failed
```

## 5. 严格模式 repo 材料

### `task-cards/`

任务卡是严格模式的核心输入。它定义任务目标、允许修改文件、禁止修改文件、验证命令和 handoff 要求。

示例：

```yaml
task_id: PNG-SIGNATURE-001
title: Implement safe PNG signature validation
module: PNG-SIGNATURE

objective:
  Ensure PNG signature validation is implemented safely and covered by tests.

must_follow:
  - no unsafe code
  - no allocation
  - never panic on malformed input

relevant_contracts:
  - contracts/png_signature.yaml

files_allowed:
  - Cargo.lock
  - src/signature.rs
  - src/error.rs
  - src/lib.rs
  - tests/signature.rs
  - .agent/handoffs/
  - reports/

forbidden_files:
  - project requirements and design notes

validation_commands:
  - cargo test --test signature

handoff_required:
  - implementation summary
  - tests run
  - edge cases handled
```

### `context-packs/`

上下文包解释任务背景、设计约束、模块关系和注意事项。

### `contracts/`

契约描述模块必须满足的行为、输入输出、错误类型和边界情况。

### `.agent/handoffs/`

agent 完成任务后必须写交接文件：

```text
.agent/handoffs/issue-<iid>.md
```

后续任务可以通过 `Depends-On` 读取它。

### `reports/`

orchestrator 会写 validation report：

```text
reports/<Task-ID>-validation.md
```

## 6. 任务依赖

如果一个 issue 必须依赖前一个 issue 的结果，在 issue metadata 中写：

```md
Depends-On: #3
```

示例：

```md
## Agent Metadata

Workflow: strict

Task-ID: PNG-CHUNK-001

Depends-On: #3
```

`Depends-On` 是强依赖：被依赖 issue 必须已有 successful job，并且 repo 中必须存在对应 handoff。

## 7. Preflight 检查

严格模式会在启动 agent 前做 preflight。常见失败：

- task card 不存在或为空
- context pack 不存在或为空
- task card `task_id` 与 issue `Task-ID` 不一致
- `files_allowed` 没有 `.agent/handoffs/`
- `files_allowed` 没有 `reports/`
- Rust cargo 任务没有把 `Cargo.lock` 放入 `files_allowed`
- `relevant_contracts` 指向的文件不存在
- validation command 需要的工具不存在或不被识别

preflight 失败时，agent 不应该启动，issue 会进入：

```text
strict:validation-failed
```

## 8. Rust 项目注意事项

Rust 任务如果运行：

```text
cargo test
cargo check
cargo build
```

建议在 `files_allowed` 中默认包含：

```yaml
- Cargo.lock
```

原因是 Cargo 可能自动规范化 lockfile，即使 agent 没有主动修改依赖。

如果不允许依赖变更，可以禁止修改 `Cargo.toml`，但允许 `Cargo.lock`。

## 9. 服务操作

在 orchestrator repo 根目录执行。

启动：

```powershell
.\scripts\start.ps1 -Port 8080
```

停止：

```powershell
.\scripts\stop.ps1 -Port 8080
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/healthz
```

查看 job：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/jobs/<job_id>
```

重试 job：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/retry
```

取消 job：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/jobs/<job_id>/cancel
```

## 10. Webhook 配置

GitLab project webhook URL：

```text
http://<orchestrator-host-ip>:8080/gitlab/webhook
```

启用：

```text
Issues events
```

Webhook secret 必须等于 `.env` 中的：

```text
GITLAB_WEBHOOK_SECRET
```

## 11. Sandbox 工具

当前默认 sandbox 镜像包含：

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

Codex/Gemini 可能需要在项目 sandbox 中完成登录或配置 API key。

## 12. 推荐使用顺序

1. 普通任务先用默认开发模式。
2. 有明确边界、验证和审计要求时用严格开发模式。
3. 严格模式任务先写 task card，再写 context pack，最后创建 issue。
4. 每个严格任务都应该产生 handoff 和 validation report。
