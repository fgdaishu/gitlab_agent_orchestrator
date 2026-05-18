from __future__ import annotations

from pathlib import Path

from .git_ops import CommandError, redact_sensitive_text, run


def run_validation(repo: Path, timeout: int) -> str:
    if (repo / "package.json").exists():
        installed_deps = False
        if not (repo / "node_modules").exists():
            installed_deps = True
            install = "npm ci" if (repo / "package-lock.json").exists() else "npm install --no-package-lock"
            import shutil

            shutil.rmtree(repo / "node_modules", ignore_errors=True)
            try:
                run(install.split(), cwd=repo, timeout=timeout)
            except CommandError as exc:
                shutil.rmtree(repo / "node_modules", ignore_errors=True)
                raise RuntimeError(f"npm install failed\n{redact_sensitive_text(exc.output[-4000:])}") from exc
        try:
            output = run(["npm", "test"], cwd=repo, timeout=timeout)
            return f"npm test: passed\n{output[-2000:]}"
        except CommandError as exc:
            raise RuntimeError(f"npm test failed\n{redact_sensitive_text(exc.output[-4000:])}") from exc
        finally:
            if installed_deps:
                shutil.rmtree(repo / "node_modules", ignore_errors=True)

    candidates = [
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
