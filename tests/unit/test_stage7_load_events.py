"""load_candidate_events — composite match key, date merge, conflict emission."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage7_load import load_candidate_events


@pytest.fixture
def canonical(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_candidate_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    chunk_id: str = "chk:t1",
    event_type: str = "战",
    year_bce: int | None = 632,
    primary_place_id: str | None = None,
    outcome: str | None = None,
    summary: str | None = None,
    confidence: float = 0.9,
    uncertainty: str = "point",
) -> None:
    date_json = json.dumps(
        {
            "year_bce": year_bce,
            "uncertainty": uncertainty,
            "inference_kind": "explicit_reign_lu",
            "original": "",
        }
    )
    cand_id = f"cand:evt:{chunk_id}:{uuid.uuid4().hex[:6]}"
    conn.execute(
        "INSERT INTO candidate_events "
        "(id, type, date_json, outcome, summary, primary_place_id, "
        "confidence, pipeline_run_id, chunk_id, quote) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            cand_id,
            event_type,
            date_json,
            outcome,
            summary,
            primary_place_id,
            confidence,
            run_id,
            chunk_id,
            event_type,
        ),
    )
    conn.commit()


def test_creates_canonical_event_on_first_load(canonical: sqlite3.Connection) -> None:
    _seed_candidate_event(canonical, run_id="run:1")
    n = load_candidate_events(canonical, "run:1")
    assert n == 1
    rows = canonical.execute("SELECT id, type FROM events").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "战"


def test_same_match_key_collapses(canonical: sqlite3.Connection) -> None:
    """Same (type, year_bce, primary_place_id) → one canonical event."""
    _seed_candidate_event(canonical, run_id="run:1", chunk_id="chk:t1")
    load_candidate_events(canonical, "run:1")
    _seed_candidate_event(canonical, run_id="run:2", chunk_id="chk:t2", outcome="晋胜")
    load_candidate_events(canonical, "run:2")

    rows = canonical.execute("SELECT id, outcome FROM events").fetchall()
    assert len(rows) == 1
    # outcome filled in via merge (null → "晋胜")
    assert rows[0][1] == "晋胜"


def test_date_merge_point_beats_range(canonical: sqlite3.Connection) -> None:
    """A more-precise date wins over a less-precise one even at slightly lower confidence."""
    _seed_candidate_event(canonical, run_id="run:1", uncertainty="range", confidence=0.9)
    load_candidate_events(canonical, "run:1")
    _seed_candidate_event(canonical, run_id="run:2", uncertainty="point", confidence=0.85)
    load_candidate_events(canonical, "run:2")

    row = canonical.execute("SELECT date_json FROM events").fetchone()
    assert row is not None
    date = json.loads(row[0])
    assert date["uncertainty"] == "point"


def test_conflict_emitted_on_scalar_disagreement(canonical: sqlite3.Connection) -> None:
    """Disagreement on outcome at similar confidence → conflict row."""
    _seed_candidate_event(canonical, run_id="run:1", outcome="晋胜", confidence=0.9)
    load_candidate_events(canonical, "run:1")
    _seed_candidate_event(canonical, run_id="run:2", outcome="楚胜", confidence=0.88)
    load_candidate_events(canonical, "run:2")

    conflicts = canonical.execute(
        "SELECT field, variants_json FROM conflicts WHERE subject_kind='event'"
    ).fetchall()
    assert len(conflicts) >= 1
    fields_with_conflict = [c[0] for c in conflicts]
    assert "outcome" in fields_with_conflict
