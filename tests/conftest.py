from __future__ import annotations

import uuid
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Path:
    root = Path(tempfile.gettempdir()) / "gitlab-agent-orchestrator-tests"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    return path
