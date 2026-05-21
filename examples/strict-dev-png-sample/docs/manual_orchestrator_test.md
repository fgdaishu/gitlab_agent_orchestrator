# Manual Orchestrator Test

Use this repository as a GitLab project, then create issues with the following metadata.

For Rust strict-development tasks, include `Cargo.lock` in each task card's `files_allowed`.
Any `cargo test`, `cargo check`, or `cargo build` command may normalize the lockfile even when the agent did not intentionally edit dependencies.

## Preflight Troubleshooting

The `strict_development` workflow runs preflight before starting the agent. Common failures:

- `context pack not found`: create `context-packs/<Task-ID>.md` or fix the issue `Task-ID`.
- `task_id must match issue Task-ID`: update either the issue metadata or the task card `task_id`.
- `Cargo.lock` missing from `files_allowed`: add `Cargo.lock` for Rust task cards that run `cargo`.
- `referenced contract not found`: fix `relevant_contracts` or add the missing contract file.
- `required tool ... is not available`: rebuild the sandbox image or install the required CLI.
- `required tool ... is not recognized`: use a supported validation command tool or extend preflight tooling detection.

When preflight fails, the issue should become `strict:validation-failed` and no agent code generation should be needed.

## Test 1: PNG-SIGNATURE-001

```markdown
## Agent Metadata

Workflow: strict

Task-ID: PNG-SIGNATURE-001

## Request

Validate the PNG signature module against the task card.

Follow `task-cards/PNG-SIGNATURE-001.yaml` and `context-packs/PNG-SIGNATURE-001.md`.

Do not expand the scope beyond signature validation.
```

Expected orchestrator behavior:

- workflow resolves to `strict_development`
- preflight confirms the task card, context pack, contract, allowed artifact paths, `Cargo.lock`, and required tools
- prompt includes `task-cards/PNG-SIGNATURE-001.yaml`
- prompt includes `context-packs/PNG-SIGNATURE-001.md`
- agent may modify only files allowed by the task card
- agent creates `.agent/handoffs/issue-<iid>.md`
- orchestrator runs `cargo test --test signature`
- orchestrator writes `reports/PNG-SIGNATURE-001-validation.md`
- successful issue label becomes `strict:review`

## Test 2: PNG-CHUNK-001

Run this after Test 1 succeeds. Replace `#<signature_issue_iid>` with the first issue number.

```markdown
## Agent Metadata

Workflow: strict

Task-ID: PNG-CHUNK-001

Depends-On: #<signature_issue_iid>

## Request

Implement and validate the PNG chunk parsing module against the task card.

Follow `task-cards/PNG-CHUNK-001.yaml` and `context-packs/PNG-CHUNK-001.md`.

Use the handoff from issue #<signature_issue_iid> as upstream context. Do not expand the scope beyond PNG chunk parsing.
```

Expected orchestrator behavior:

- preflight confirms the task card, context pack, contract, allowed artifact paths, `Cargo.lock`, and required tools
- dependency handoff from the first issue is injected
- orchestrator runs `cargo test --test chunk`
- orchestrator writes `reports/PNG-CHUNK-001-validation.md`
- successful issue label becomes `strict:review`
