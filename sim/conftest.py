from __future__ import annotations

import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def simulator_name() -> str:
    return os.environ.get("SIM", "icarus")
