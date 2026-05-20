"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_db_dir(tmp_path: Path) -> Path:
    """Empty directory for ad-hoc sqlite databases."""
    (tmp_path / "data").mkdir()
    return tmp_path
