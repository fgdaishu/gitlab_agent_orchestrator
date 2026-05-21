from __future__ import annotations

import re
import shlex
from fnmatch import fnmatch

from ...handoff import handoff_path
from ..base import WorkflowPreflightContext, WorkflowPreflightResult, WorkflowValidationContext, WorkflowValidationResult


REQUIRED_TASK_CARD_FIELDS = (
    "task_id",
    "title",
    "module",
    "objective",
    "must_follow",
    "files_allowed",
    "forbidden_files",
    "validation_commands",
    "handoff_required",
)


def validate_strict_task(context: WorkflowValidationContext) -> WorkflowValidationResult:
    job = context.job
    task_id = job.workflow_task_id or _task_id_from_title(job.issue_title)
    if not task_id:
        return WorkflowValidationResult(False, "strict_development validation requires a task id.")

    task_card_path = f"task-cards/{task_id}.yaml"
    task_card = context.read_repo_file(task_card_path)
    if not task_card.strip():
        return WorkflowValidationResult(False, f"strict_development task card not found or empty: `{task_card_path}`.")

    handoff = handoff_path(job.issue_iid)
    if not context.repo_file_exists(handoff):
        return WorkflowValidationResult(False, f"Agent completed but did not create `{handoff}`.")

    changed = context.changed_files()
    allowed = parse_list_field(task_card, ("files_allowed", "allowed_files"))
    forbidden = parse_list_field(task_card, ("forbidden_files", "files_forbidden"))
    if forbidden:
        forbidden_changes = [path for path in changed if any(_path_matches(path, pattern) for pattern in forbidden)]
        if forbidden_changes:
            return WorkflowValidationResult(
                False,
                "strict_development validation failed: forbidden files were modified.\n\n"
                + "\n".join(f"- {path}" for path in forbidden_changes),
            )
    if allowed:
        unexpected = [path for path in changed if not any(_path_matches(path, pattern) for pattern in allowed)]
        if unexpected:
            return WorkflowValidationResult(
                False,
                "strict_development validation failed: files outside `files_allowed` were modified.\n\n"
                "Allowed patterns:\n"
                + "\n".join(f"- {pattern}" for pattern in allowed)
                + "\n\nUnexpected changed files:\n"
                + "\n".join(f"- {path}" for path in unexpected),
            )

    commands = parse_validation_commands(task_card)
    files_summary = _files_summary(changed, allowed, forbidden)
    report_path = f"reports/{task_id}-validation.md"
    if not commands:
        summary = f"Handoff present. No validation commands declared in `{task_card_path}`.\n{files_summary}"
        return WorkflowValidationResult(
            True,
            summary,
            report_path=report_path,
            report_content=build_validation_report(
                task_id=task_id,
                status="passed",
                task_card_path=task_card_path,
                handoff=handoff,
                changed=changed,
                allowed=allowed,
                forbidden=forbidden,
                commands=[],
                command_outputs=[],
                summary=summary,
            ),
        )

    outputs: list[str] = []
    for command in commands:
        output = context.run_repo_command(command)
        outputs.append(f"$ {command}\n{output.strip()[-2000:]}")

    summary = "strict_development validation passed.\n" + files_summary + "\n\n" + "\n\n".join(outputs)
    return WorkflowValidationResult(
        True,
        summary,
        report_path=report_path,
        report_content=build_validation_report(
            task_id=task_id,
            status="passed",
            task_card_path=task_card_path,
            handoff=handoff,
            changed=changed,
            allowed=allowed,
            forbidden=forbidden,
            commands=commands,
            command_outputs=outputs,
            summary=summary,
        ),
    )


def preflight_strict_task(context: WorkflowPreflightContext) -> WorkflowPreflightResult:
    job = context.job
    task_id = job.workflow_task_id or _task_id_from_title(job.issue_title)
    if not task_id:
        return WorkflowPreflightResult(False, "strict_development preflight requires a task id.")

    task_card_path = f"task-cards/{task_id}.yaml"
    context_pack_path = f"context-packs/{task_id}.md"
    task_card = context.read_repo_file(task_card_path)
    if not task_card.strip():
        return WorkflowPreflightResult(False, f"strict_development task card not found or empty: `{task_card_path}`.")
    if not context.read_repo_file(context_pack_path).strip():
        return WorkflowPreflightResult(False, f"strict_development context pack not found or empty: `{context_pack_path}`.")

    errors = validate_task_card_schema(
        task_card,
        expected_task_id=task_id,
        repo_file_exists=context.repo_file_exists,
    )
    errors.extend(_validate_tooling(task_card, job.agent, context.run_repo_command))
    if errors:
        return WorkflowPreflightResult(
            False,
            "strict_development preflight failed:\n\n" + "\n".join(f"- {error}" for error in errors),
        )
    return WorkflowPreflightResult(True, f"strict_development preflight passed for `{task_id}`.")


def validate_task_card_schema(task_card: str, *, expected_task_id: str, repo_file_exists) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_TASK_CARD_FIELDS:
        if field in {"task_id", "title", "module"}:
            if not parse_scalar_field(task_card, field):
                errors.append(f"`{field}` is required.")
        elif field == "objective":
            if not has_field_content(task_card, field):
                errors.append(f"`{field}` is required.")
        elif not parse_list_field(task_card, (field,)):
            errors.append(f"`{field}` must contain at least one item.")

    declared_task_id = parse_scalar_field(task_card, "task_id")
    if declared_task_id and declared_task_id != expected_task_id:
        errors.append(f"`task_id` must match issue Task-ID `{expected_task_id}`, got `{declared_task_id}`.")

    allowed = parse_list_field(task_card, ("files_allowed", "allowed_files"))
    if allowed and not any(_path_matches(".agent/handoffs/issue-0.md", pattern) for pattern in allowed):
        errors.append("`files_allowed` must include `.agent/handoffs/` so the agent can write a handoff.")
    if allowed and not any(_path_matches("reports/example-validation.md", pattern) for pattern in allowed):
        errors.append("`files_allowed` must include `reports/` so the workflow can write a validation report.")

    commands = parse_validation_commands(task_card)
    if any(_command_tool(command) == "cargo" for command in commands) and repo_file_exists("Cargo.toml"):
        if not any(_path_matches("Cargo.lock", pattern) for pattern in allowed):
            errors.append("Rust task cards that run cargo should include `Cargo.lock` in `files_allowed`.")

    for contract in parse_list_field(task_card, ("relevant_contracts", "contracts")):
        if not repo_file_exists(contract):
            errors.append(f"referenced contract not found: `{contract}`.")

    return errors


def parse_scalar_field(task_card: str, field_name: str) -> str:
    pattern = re.compile(rf"^{re.escape(field_name)}\s*:\s*(.+?)\s*$")
    for raw_line in task_card.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = pattern.match(stripped)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    return ""


def has_field_content(task_card: str, field_name: str) -> bool:
    scalar = parse_scalar_field(task_card, field_name)
    if scalar:
        return True
    in_block = False
    block_indent: int | None = None
    for raw_line in task_card.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if re.match(rf"^{re.escape(field_name)}\s*:\s*$", stripped):
            in_block = True
            block_indent = indent
            continue
        if in_block:
            if indent <= (block_indent or 0):
                return False
            return True
    return False


def parse_validation_commands(task_card: str) -> list[str]:
    return parse_list_field(task_card, ("validation_commands", "validation", "validation_commands_to_run"))


def parse_list_field(task_card: str, field_names: tuple[str, ...]) -> list[str]:
    commands: list[str] = []
    in_block = False
    block_indent: int | None = None
    field_pattern = "|".join(re.escape(name) for name in field_names)
    for raw_line in task_card.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if re.match(rf"^({field_pattern})\s*:\s*$", stripped):
            in_block = True
            block_indent = indent
            continue
        if in_block:
            if indent <= (block_indent or 0) and not stripped.startswith("-"):
                in_block = False
                block_indent = None
                continue
            if stripped.startswith("-"):
                command = stripped[1:].strip().strip('"').strip("'")
                if command:
                    commands.append(command)
    return commands


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.strip().replace("\\", "/")
    normalized_pattern = pattern.strip().replace("\\", "/").strip("/")
    if not normalized_path or not normalized_pattern:
        return False
    if normalized_pattern.endswith("/"):
        return normalized_path.startswith(normalized_pattern)
    if any(char in normalized_pattern for char in "*?[]"):
        return fnmatch(normalized_path, normalized_pattern)
    return normalized_path == normalized_pattern or normalized_path.startswith(f"{normalized_pattern}/")


def _files_summary(changed: list[str], allowed: list[str], forbidden: list[str]) -> str:
    changed_line = ", ".join(changed) if changed else "none detected"
    allowed_line = ", ".join(allowed) if allowed else "not declared"
    forbidden_line = ", ".join(forbidden) if forbidden else "not declared"
    return f"Changed files: {changed_line}\nAllowed files: {allowed_line}\nForbidden files: {forbidden_line}"


def _validate_tooling(task_card: str, agent: str, run_repo_command) -> list[str]:
    errors: list[str] = []
    tools = {_command_tool(command) for command in parse_validation_commands(task_card)}
    if agent == "opencode":
        tools.add("opencode")
    elif agent == "codex":
        tools.add("codex")
    elif agent == "gemini-cli":
        tools.add("gemini")

    for tool in sorted(tool for tool in tools if tool):
        check = _tool_check_command(tool)
        if not check:
            errors.append(f"required tool `{tool}` is not recognized by strict_development preflight.")
            continue
        try:
            run_repo_command(check)
        except Exception as exc:
            errors.append(f"required tool `{tool}` is not available or failed `{check}`: {str(exc).strip()}")
    return errors


def _command_tool(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return ""
    if not parts:
        return ""
    tool = parts[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if tool.endswith(".exe"):
        tool = tool[:-4]
    if tool == "python3":
        return "python"
    return tool


def _tool_check_command(tool: str) -> str:
    checks = {
        "cargo": "cargo --version",
        "rustc": "rustc --version",
        "python": "python --version",
        "pytest": "pytest --version",
        "npm": "npm --version",
        "node": "node --version",
        "opencode": "opencode --version",
        "codex": "codex --version",
        "gemini": "gemini --version",
    }
    return checks.get(tool, "")


def build_validation_report(
    *,
    task_id: str,
    status: str,
    task_card_path: str,
    handoff: str,
    changed: list[str],
    allowed: list[str],
    forbidden: list[str],
    commands: list[str],
    command_outputs: list[str],
    summary: str,
) -> str:
    return "\n".join(
        [
            f"# Validation Report: {task_id}",
            "",
            f"Status: {status}",
            f"Task Card: `{task_card_path}`",
            f"Handoff: `{handoff}`",
            "",
            "## Changed Files",
            _markdown_list(changed),
            "",
            "## Allowed Files",
            _markdown_list(allowed),
            "",
            "## Forbidden Files",
            _markdown_list(forbidden),
            "",
            "## Validation Commands",
            _markdown_list(commands),
            "",
            "## Command Output",
            "\n\n".join(f"```text\n{output.strip()}\n```" for output in command_outputs) if command_outputs else "No validation commands declared.",
            "",
            "## Summary",
            "```text",
            summary.strip(),
            "```",
            "",
        ]
    )


def _markdown_list(values: list[str]) -> str:
    if not values:
        return "- None"
    return "\n".join(f"- `{value}`" for value in values)


def _task_id_from_title(title: str) -> str | None:
    stripped = (title or "").strip()
    if not stripped.startswith("[") or "]" not in stripped:
        return None
    candidate = stripped[1 : stripped.index("]")].strip()
    return candidate or None
