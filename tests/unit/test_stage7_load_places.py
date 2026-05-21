"""load_candidate_places — field-level merge, citation accumulation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage7_load import load_candidate_places


@pytest.fixture
def canonical(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_candidate_place(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    chunk_id: str,
    name: str = "镐京",
    lat: float | None = None,
    lon: float | None = None,
    place_type: str | None = None,
    confidence: float = 0.9,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO candidate_places "
        "(id, name, type, lat, lon, coord_confidence, modern_equiv, "
        "confidence, pipeline_run_id, chunk_id, quote) "
        "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)",
        (f"cand:pla:{chunk_id}", name, place_type, lat, lon, confidence, run_id, chunk_id, name),
    )
    conn.commit()


def test_creates_canonical_place_on_first_load(canonical: sqlite3.Connection) -> None:
    _seed_candidate_place(canonical, run_id="run:1", chunk_id="chk:t1")
    load_candidate_places(canonical, "run:1")
    rows = canonical.execute("SELECT id, name FROM places").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "镐京"


def test_second_load_with_same_name_merges_not_creates(canonical: sqlite3.Connection) -> None:
    _seed_candidate_place(canonical, run_id="run:1", chunk_id="chk:t1")
    load_candidate_places(canonical, "run:1")
    _seed_candidate_place(canonical, run_id="run:2", chunk_id="chk:t2", lat=34.5)
    load_candidate_places(canonical, "run:2")

    rows = canonical.execute("SELECT id, name, lat FROM places").fetchall()
    assert len(rows) == 1
    assert rows[0][2] == 34.5  # lat updated from null → 34.5

    citations = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind='place'"
    ).fetchall()
    assert sorted(c[0] for c in citations) == ["chk:t1", "chk:t2"]


def test_higher_confidence_lat_overrides_lower(canonical: sqlite3.Connection) -> None:
    _seed_candidate_place(canonical, run_id="run:1", chunk_id="chk:t1", lat=34.0, confidence=0.7)
    load_candidate_places(canonical, "run:1")
    _seed_candidate_place(canonical, run_id="run:2", chunk_id="chk:t2", lat=34.5, confidence=0.9)
    load_candidate_places(canonical, "run:2")

    row = canonical.execute("SELECT lat FROM places").fetchone()
    assert row[0] == 34.5
