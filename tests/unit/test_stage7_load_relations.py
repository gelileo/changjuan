"""load_candidate_relations — six relation kinds, tuple-key dedup, citation accumulation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage7_load import load_candidate_relations


@pytest.fixture
def canonical(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


# ---------------------------------------------------------------------------
# Shared seed helpers
# ---------------------------------------------------------------------------


def _seed_entities(conn: sqlite3.Connection) -> None:
    """Insert minimal canonical persons/events/places/states so FK constraints pass."""
    conn.execute(
        "INSERT INTO persons (id, canonical_name, provenance, confidence, pipeline_run_id)"
        " VALUES ('per:a', 'A', 'auto', 0.9, 'run:setup')"
    )
    conn.execute(
        "INSERT INTO persons (id, canonical_name, provenance, confidence, pipeline_run_id)"
        " VALUES ('per:b', 'B', 'auto', 0.9, 'run:setup')"
    )
    conn.execute(
        "INSERT INTO events (id, type, provenance, confidence, pipeline_run_id)"
        " VALUES ('evt:1', '战', 'auto', 0.9, 'run:setup')"
    )
    conn.execute(
        "INSERT INTO events (id, type, provenance, confidence, pipeline_run_id)"
        " VALUES ('evt:2', '盟', 'auto', 0.9, 'run:setup')"
    )
    conn.execute(
        "INSERT INTO places (id, name, provenance, confidence, pipeline_run_id)"
        " VALUES ('pla:1', 'P1', 'auto', 0.9, 'run:setup')"
    )
    conn.execute(
        "INSERT INTO states (id, name, provenance, confidence, pipeline_run_id)"
        " VALUES ('sta:1', 'S1', 'auto', 0.9, 'run:setup')"
    )
    conn.commit()


def _seed_event_participant(
    conn: sqlite3.Connection,
    run_id: str,
    event_id: str = "evt:1",
    person_id: str = "per:a",
    role: str = "主将",
) -> None:
    # INSERT OR REPLACE so that re-seeding with a new run_id updates the row.
    conn.execute(
        "INSERT OR REPLACE INTO candidate_event_participants"
        " (candidate_event_id, candidate_person_id, role, pipeline_run_id)"
        " VALUES (?, ?, ?, ?)",
        (event_id, person_id, role, run_id),
    )
    conn.commit()


def _seed_event_place(
    conn: sqlite3.Connection,
    run_id: str,
    event_id: str = "evt:1",
    place_id: str = "pla:1",
    role: str = "战场",
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO candidate_event_places"
        " (candidate_event_id, candidate_place_id, role, pipeline_run_id)"
        " VALUES (?, ?, ?, ?)",
        (event_id, place_id, role, run_id),
    )
    conn.commit()


def _seed_event_relation(
    conn: sqlite3.Connection,
    run_id: str,
    from_id: str = "evt:1",
    to_id: str = "evt:2",
    kind: str = "precedes",
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO candidate_event_relations"
        " (from_candidate_event_id, to_candidate_event_id, kind, pipeline_run_id)"
        " VALUES (?, ?, ?, ?)",
        (from_id, to_id, kind, run_id),
    )
    conn.commit()


def _seed_person_relation(
    conn: sqlite3.Connection,
    run_id: str,
    from_id: str = "per:a",
    to_id: str = "per:b",
    kind: str = "ally",
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO candidate_person_relations"
        " (from_candidate_person_id, to_candidate_person_id, kind, pipeline_run_id)"
        " VALUES (?, ?, ?, ?)",
        (from_id, to_id, kind, run_id),
    )
    conn.commit()


def _seed_person_state(
    conn: sqlite3.Connection,
    run_id: str,
    person_id: str = "per:a",
    state_id: str = "sta:1",
    role: str = "ruler",
) -> None:
    # candidate_person_states PK is (candidate_person_id, candidate_state_id, role)
    # Use INSERT OR REPLACE to allow multiple runs with same key
    conn.execute(
        "INSERT OR REPLACE INTO candidate_person_states"
        " (candidate_person_id, candidate_state_id, role, pipeline_run_id)"
        " VALUES (?, ?, ?, ?)",
        (person_id, state_id, role, run_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# event_participants
# ---------------------------------------------------------------------------


def test_event_participant_first_load_creates_row(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_event_participant(canonical, "run:1")
    n = load_candidate_relations(canonical, "run:1")
    assert n == 1
    rows = canonical.execute("SELECT event_id, person_id, role FROM event_participants").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "evt:1"
    assert rows[0][1] == "per:a"
    assert rows[0][2] == "主将"


def test_event_participant_idempotence_accumulates_citations(
    canonical: sqlite3.Connection,
) -> None:
    _seed_entities(canonical)
    _seed_event_participant(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    _seed_event_participant(canonical, "run:2")
    load_candidate_relations(canonical, "run:2")

    rows = canonical.execute("SELECT event_id FROM event_participants").fetchall()
    assert len(rows) == 1  # dedup: same tuple key → one canonical row

    cites = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind = 'event_participant'"
    ).fetchall()
    assert len(cites) == 2  # accumulated


# ---------------------------------------------------------------------------
# event_places
# ---------------------------------------------------------------------------


def test_event_place_first_load_creates_row(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_event_place(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    rows = canonical.execute("SELECT event_id, place_id, role FROM event_places").fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "战场"


def test_event_place_idempotence_accumulates_citations(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_event_place(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    _seed_event_place(canonical, "run:2")
    load_candidate_relations(canonical, "run:2")

    rows = canonical.execute("SELECT event_id FROM event_places").fetchall()
    assert len(rows) == 1

    cites = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind = 'event_place'"
    ).fetchall()
    assert len(cites) == 2


# ---------------------------------------------------------------------------
# event_relations
# ---------------------------------------------------------------------------


def test_event_relation_first_load_creates_row(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_event_relation(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    rows = canonical.execute(
        "SELECT from_event_id, to_event_id, kind FROM event_relations"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "precedes"


def test_event_relation_idempotence_accumulates_citations(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_event_relation(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    _seed_event_relation(canonical, "run:2")
    load_candidate_relations(canonical, "run:2")

    rows = canonical.execute("SELECT from_event_id FROM event_relations").fetchall()
    assert len(rows) == 1

    cites = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind = 'event_relation'"
    ).fetchall()
    assert len(cites) == 2


# ---------------------------------------------------------------------------
# person_relations
# ---------------------------------------------------------------------------


def test_person_relation_first_load_creates_row(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_person_relation(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    rows = canonical.execute(
        "SELECT from_person_id, to_person_id, kind FROM person_relations"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "ally"


def test_person_relation_idempotence_accumulates_citations(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_person_relation(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    _seed_person_relation(canonical, "run:2")
    load_candidate_relations(canonical, "run:2")

    rows = canonical.execute("SELECT from_person_id FROM person_relations").fetchall()
    assert len(rows) == 1

    cites = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind = 'person_relation'"
    ).fetchall()
    assert len(cites) == 2


def test_person_relation_contradictory_directionality_emits_conflict(
    canonical: sqlite3.Connection,
) -> None:
    """(A→B, killed_by) then (B→A, killed_by) flags a contradiction conflict."""
    _seed_entities(canonical)
    # First: A killed_by B
    _seed_person_relation(canonical, "run:1", from_id="per:a", to_id="per:b", kind="killed_by")
    load_candidate_relations(canonical, "run:1")

    # Second: B killed_by A — inverse of same directional kind
    _seed_person_relation(canonical, "run:2", from_id="per:b", to_id="per:a", kind="killed_by")
    load_candidate_relations(canonical, "run:2")

    # Both rows are inserted (the loader doesn't suppress the incoming row)
    person_relation_rows = canonical.execute("SELECT * FROM person_relations").fetchall()
    assert len(person_relation_rows) == 2

    # A conflict is emitted for the directionality contradiction
    conflicts = canonical.execute(
        "SELECT subject_kind, field FROM conflicts WHERE subject_kind = 'person_relation'"
    ).fetchall()
    assert len(conflicts) == 1
    assert conflicts[0][1] == "directionality"


# ---------------------------------------------------------------------------
# person_states
# ---------------------------------------------------------------------------


def test_person_state_first_load_creates_row(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_person_state(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    rows = canonical.execute("SELECT person_id, state_id, role FROM person_states").fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "ruler"


def test_person_state_idempotence_accumulates_citations(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    _seed_person_state(canonical, "run:1")
    load_candidate_relations(canonical, "run:1")
    _seed_person_state(canonical, "run:2")
    load_candidate_relations(canonical, "run:2")

    rows = canonical.execute("SELECT person_id FROM person_states").fetchall()
    assert len(rows) == 1

    cites = canonical.execute(
        "SELECT citation_id FROM entity_citations WHERE entity_kind = 'person_state'"
    ).fetchall()
    assert len(cites) == 2


# ---------------------------------------------------------------------------
# state_capitals (stub — no candidate table, always 0)
# ---------------------------------------------------------------------------


def test_state_capitals_stub_returns_zero(canonical: sqlite3.Connection) -> None:
    _seed_entities(canonical)
    n = load_candidate_relations(canonical, "run:1")
    assert n == 0
    rows = canonical.execute("SELECT * FROM state_capitals").fetchall()
    assert len(rows) == 0
