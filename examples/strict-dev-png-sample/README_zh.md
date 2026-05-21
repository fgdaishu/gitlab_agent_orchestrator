# Strict Development PNG Sample 中文说明

这是一个最小化的严格开发模式样例项目，用 Rust 实现 PNG 解析的一小部分安全逻辑。它用于展示 `strict_development` 工作流需要怎样组织仓库材料。

目录含义：

- `project-meta/`：项目级约束、模块边界和安全要求。
- `task-cards/`：每个任务的可执行规格，包括目标、允许修改的文件、禁止修改的文件和校验命令。
- `context-packs/`：给 Agent 的任务上下文，补充 task card 中没有展开的背景信息。
- `contracts/`：输入输出、错误行为和边界条件契约。
- `test-oracles/`：有效和异常样例，用于指导测试。
- `.agent/handoffs/`：Agent 完成任务后写入的交接文件位置。
- `reports/`：orchestrator 写入 validation report 的位置。

第一次手动测试建议使用 `PNG-SIGNATURE-001`：

```markdown
## Agent Metadata

Workflow: strict
Task-ID: PNG-SIGNATURE-001
```

第一个任务成功后，可以继续使用 `PNG-CHUNK-001` 测试依赖更完整的严格开发流程。

详细 Issue 内容和预期结果见 `docs/manual_orchestrator_test.md`。
