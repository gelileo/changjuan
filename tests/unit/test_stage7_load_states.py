"""load_candidate_states — field-level merge, citation accumulation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage7_load import load_candidate_states


@pytest.fixture
def canonical(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_candidate_state(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    chunk_id: str = "chk:t1",
    name: str = "周",
    state_type: str | None = None,
    ruling_clan: str | None = None,
    confidence: float = 0.9,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO candidate_states "
        "(id, name, type, ruling_clan, founded_date_json, ended_date_json, "
        "confidence, pipeline_run_id, chunk_id, quote) "
        "VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)",
        (
            f"cand:sta:{chunk_id}",
            name,
            state_type,
            ruling_clan,
            confidence,
            run_id,
            chunk_id,
            name,
        ),
    )
    conn.commit()


def test_creates_canonical_state_on_first_load(canonical: sqlite3.Connection) -> None:
    _seed_candidate_state(canonical, run_id="run:1")
    load_candidate_states(canonical, "run:1")
    rows = canonical.execute("SELECT id, name FROM states").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "周"


def test_second_load_with_same_name_merges_not_creates(canonical: sqlite3.Connection) -> None:
    _seed_candidate_state(canonical, run_id="run:1", chunk_id="chk:t1")
    load_candidate_states(canonical, "run:1")
    _seed_candidate_state(canonical, run_id="run:2", chunk_id="chk:t2", ruling_clan="姬")
    load_candidate_states(canonical, "run:2")

    rows = canonical.execute("SELECT id, name, ruling_clan FROM states").fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "姬"  # ruling_clan updated from null → 姬

    citations = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind='state'"
    ).fetchall()
    assert len(citations) == 2


def test_higher_confidence_field_overrides_lower(canonical: sqlite3.Connection) -> None:
    _seed_candidate_state(
        canonical, run_id="run:1", chunk_id="chk:t1", ruling_clan="姒", confidence=0.7
    )
    load_candidate_states(canonical, "run:1")
    _seed_candidate_state(
        canonical, run_id="run:2", chunk_id="chk:t2", ruling_clan="姬", confidence=0.9
    )
    load_candidate_states(canonical, "run:2")

    row = canonical.execute("SELECT ruling_clan FROM states").fetchone()
    assert row[0] == "姬"
