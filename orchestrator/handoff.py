from __future__ import annotations

import re
from dataclasses import dataclass


HANDOFF_PATH_TEMPLATE = ".agent/handoffs/issue-{issue_iid}.md"
MAX_HANDOFF_CHARS = 16000


@dataclass(frozen=True)
class IssueDependencies:
    depends_on: tuple[int, ...]
    context_from: tuple[int, ...]


def parse_issue_dependencies(description: str) -> IssueDependencies:
    depends_on = _parse_metadata_issue_refs(description, "Depends-On")
    context_from = _parse_metadata_issue_refs(description, "Context-From")
    return IssueDependencies(depends_on=depends_on, context_from=context_from)


def handoff_path(issue_iid: int) -> str:
    return HANDOFF_PATH_TEMPLATE.format(issue_iid=issue_iid)


def build_handoff_context(handoffs: dict[int, str]) -> str:
    if not handoffs:
        return ""
    blocks: list[str] = []
    for issue_iid, content in sorted(handoffs.items()):
        trimmed = content.strip()[:MAX_HANDOFF_CHARS]
        blocks.append(f"## Handoff from issue #{issue_iid}\n\n{trimmed}")
    return "\n\n".join(blocks)


def _parse_metadata_issue_refs(description: str, field: str) -> tuple[int, ...]:
    values: list[int] = []
    pattern = re.compile(rf"(?im)^\s*{re.escape(field)}\s*:\s*(.+?)\s*$")
    for match in pattern.finditer(description or ""):
        for ref in re.findall(r"#(\d+)", match.group(1)):
            iid = int(ref)
            if iid not in values:
                values.append(iid)
    return tuple(values)
