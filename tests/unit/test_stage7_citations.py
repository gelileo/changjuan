"""Citation accumulation in stage 7 — every create/update writes an entity_citations row;
re-loading the same candidate accumulates citations rather than overwriting.

NOTE: candidate_persons uses chunk_id (not citation_id); entity_citations.citation_id
is populated from the candidate's chunk_id.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage7_load import load_candidate_persons


@pytest.fixture
def canonical(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "changjuan.sqlite").__enter__()
    apply_schema(conn, CANONICAL_SCHEMA)
    return conn


def _seed_candidate_person(
    canonical: sqlite3.Connection,
    *,
    run_id: str,
    candidate_id: str,
    chunk_id: str,
    canonical_name: str = "重耳",
) -> None:
    canonical.execute(
        """INSERT INTO candidate_persons
               (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)
           VALUES (?, ?, 0.9, ?, ?, '重耳')""",
        (candidate_id, canonical_name, run_id, chunk_id),
    )
    canonical.commit()


def test_first_load_writes_one_entity_citations_row(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        _seed_candidate_person(conn, run_id="run:1", candidate_id="cand:1", chunk_id="chk:t1")
        load_candidate_persons(conn, "run:1")

        rows = conn.execute(
            "SELECT entity_kind, entity_id, citation_id FROM entity_citations"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_kind"] == "person"
    assert rows[0]["citation_id"] == "chk:t1"


def test_reload_accumulates_citations(tmp_path: Path) -> None:
    """Same canonical_name, different chunk_id → one canonical Person, two entity_citations rows."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        _seed_candidate_person(conn, run_id="run:1", candidate_id="cand:1", chunk_id="chk:t1")
        load_candidate_persons(conn, "run:1")

        _seed_candidate_person(conn, run_id="run:2", candidate_id="cand:2", chunk_id="chk:t2")
        load_candidate_persons(conn, "run:2")

        persons = conn.execute("SELECT id FROM persons").fetchall()
        assert len(persons) == 1, "same canonical_name → one Person"

        citations = conn.execute(
            "SELECT citation_id FROM entity_citations WHERE entity_kind='person'"
        ).fetchall()
        assert sorted(c["citation_id"] for c in citations) == ["chk:t1", "chk:t2"]


def test_same_citation_twice_is_idempotent(tmp_path: Path) -> None:
    """Loading the same candidate row twice → still one entity_citations row (idempotent)."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        _seed_candidate_person(conn, run_id="run:1", candidate_id="cand:1", chunk_id="chk:t1")
        load_candidate_persons(conn, "run:1")
        load_candidate_persons(conn, "run:1")  # idempotent re-run

        citations = conn.execute(
            "SELECT citation_id FROM entity_citations WHERE entity_kind='person'"
        ).fetchall()
    assert len(citations) == 1
