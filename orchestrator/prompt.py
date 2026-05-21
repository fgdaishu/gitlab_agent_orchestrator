from __future__ import annotations

from pathlib import Path

from .models import Job
from .workflows.default_coding.prompt_builder import build_default_prompt, read_project_rules as read_default_project_rules


def read_project_rules(repo: Path) -> str:
    return read_default_project_rules(repo)


def build_prompt(
    job: Job,
    project_rules: str,
    comments: list[str] | None = None,
    is_incremental: bool = False,
    handoff_context: str = "",
) -> str:
    return build_default_prompt(
        job,
        project_rules,
        comments=comments,
        is_incremental=is_incremental,
        handoff_context=handoff_context,
    )
