from __future__ import annotations

from pathlib import Path

from .git_ops import CommandError, run


def run_validation(repo: Path, timeout: int) -> str:
    candidates = [
        ("package.json", ["npm", "test"]),
        ("pyproject.toml", ["python", "-m", "pytest"]),
        ("pytest.ini", ["python", "-m", "pytest"]),
    ]
    for marker, command in candidates:
        if (repo / marker).exists():
            try:
                output = run(command, cwd=repo, timeout=timeout)
                return f"{' '.join(command)}: passed\n{output[-2000:]}"
            except CommandError as exc:
                raise RuntimeError(f"{' '.join(command)} failed\n{exc.output[-4000:]}") from exc
    return "No test command detected."
