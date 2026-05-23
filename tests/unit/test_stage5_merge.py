"""Unit tests for pipeline.stage5_link.merge.

Each test seeds a fresh tmp_path DB via tests.fixtures.curation.seed_merge_db,
then exercises one branch of one merge action.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.db import connect
from pipeline.stage5_link.merge import (
    MergeResult,
    accept_merge,
)
from tests.fixtures.curation.seed_merge_db import seed


@pytest.fixture
def seeded_db(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "merge_test.sqlite"
    mc_id = seed(db_path)
    return db_path, mc_id


def test_accept_merge_happy_path_returns_result(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert isinstance(result, MergeResult)
    assert result.canonical_id == "per:test:canonical"
    assert result.relations_retargeted >= 1  # the seeded event_participants row
