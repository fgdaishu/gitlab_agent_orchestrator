# Strict Development PNG Sample

This repository is a minimal strict-development sample for a safe PNG parser subset in Rust.

中文说明见 [`README_zh.md`](README_zh.md).

The first manual orchestrator test should use the `PNG-SIGNATURE-001` task:

```markdown
## Agent Metadata

Workflow: strict
Task-ID: PNG-SIGNATURE-001
```

The second test can use `PNG-CHUNK-001` after the first task succeeds.

See `docs/manual_orchestrator_test.md` for exact issue bodies and expected results.
