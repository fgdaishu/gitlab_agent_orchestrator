from __future__ import annotations


AGENT_STATUS_LABELS = {"agent:running", "agent:failed", "agent:review", "agent:done"}
STRICT_STATUS_LABELS = {"strict:ready", "strict:running", "strict:review", "strict:done", "strict:validation-failed"}


def without_status(labels: list[str], statuses: set[str]) -> list[str]:
    return [label for label in labels if label not in statuses]
