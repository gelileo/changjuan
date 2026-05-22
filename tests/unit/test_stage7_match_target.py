"""Stage 7 honors candidate_persons.match_target_id when set."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
import structlog

from pipeline.db import open_canonical_db
from pipeline.stage7_load.persons import load_candidate_persons


@pytest.fixture(autouse=True)
def _structlog_to_stdlib() -> None:
    """Route structlog through stdlib logging so pytest's caplog can capture it."""
    structlog.configure(
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_canonical(c: sqlite3.Connection, *, person_id: str, name: str) -> None:
    c.execute(
        "INSERT INTO persons (id, canonical_name, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, 'auto', 0.9, 'run:setup')",
        (person_id, name),
    )
    c.commit()


def _seed_candidate(
    c: sqlite3.Connection,
    *,
    run_id: str,
    cand_id: str,
    name: str,
    match_target_id: str | None = None,
) -> None:
    c.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, match_target_id, chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'chk:t', '', 0.9, ?)",
        (cand_id, name, match_target_id, run_id),
    )
    c.commit()


def test_match_target_id_honored_when_set_to_canonical(conn: sqlite3.Connection) -> None:
    """When match_target_id points at an existing canonical, merge into it (not create new)."""
    _seed_canonical(conn, person_id="per:jin-wen-gong", name="晋文公")
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",  # DIFFERENT canonical_name from target
        match_target_id="per:jin-wen-gong",
    )
    load_candidate_persons(conn, "run:1")

    # Should NOT create a new canonical Person named 重耳; should merge into 晋文公.
    persons = conn.execute("SELECT id, canonical_name FROM persons").fetchall()
    assert len(persons) == 1
    assert persons[0][0] == "per:jin-wen-gong"


def test_match_target_id_null_falls_back_to_name_match(conn: sqlite3.Connection) -> None:
    """When match_target_id is null, existing canonical_name-match logic runs."""
    _seed_canonical(conn, person_id="per:zhong-er", name="重耳")
    _seed_candidate(
        conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳", match_target_id=None
    )
    load_candidate_persons(conn, "run:1")

    persons = conn.execute("SELECT id FROM persons").fetchall()
    assert len(persons) == 1


def test_match_target_id_missing_target_falls_through_with_warning(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    """When match_target_id points at a non-existent canonical, log warning + fall through."""
    _seed_canonical(conn, person_id="per:zhong-er", name="重耳")
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",
        match_target_id="per:NONEXISTENT",
    )
    with caplog.at_level(logging.WARNING):
        load_candidate_persons(conn, "run:1")
    persons = conn.execute("SELECT id FROM persons").fetchall()
    assert len(persons) == 1
    assert persons[0][0] == "per:zhong-er"
    # Verify a warning was logged
    assert any("match_target_id" in record.message for record in caplog.records)


def test_cross_run_chain_when_target_id_lex_greater_than_source(conn: sqlite3.Connection) -> None:
    """Reproduce the ordering bug: source candidate id sorts BEFORE target candidate id.

    The fix is a 2-pass load: process match_target_id=NULL candidates first
    (so the target's canonical_id is populated in local_canonical_map BEFORE
    the source's match_target_id is resolved)."""
    # p1 < p2 lexicographically; p1.match_target_id points at p2.
    # p2 has NO match_target_id (would be set by linker only if p2's own best
    # target were elsewhere; here it isn't).
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",
        match_target_id="cand:per:run:1:p2",
    )  # forward reference!
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p2",
        name="重耳",  # same name (intentional)
        match_target_id=None,
    )
    load_candidate_persons(conn, "run:1")
    # 1 canonical should result; both candidates merged into p2's canonical.
    n = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    assert n == 1, (
        f"Expected 1 canonical from the cross-run chain (p1 → p2 forward reference); "
        f"got {n}. The 2-pass load order should have processed p2 first (no match_target_id), "
        f"populated local_canonical_map, then resolved p1's match_target_id."
    )


def test_cross_run_chain_resolves_via_local_map(conn: sqlite3.Connection) -> None:
    """A candidate's match_target_id pointing at a sibling candidate gets resolved
    to the canonical that sibling becomes (in the same load pass)."""
    _seed_candidate(
        conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳"
    )  # no match_target → creates new canonical
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p2",
        name="公子重耳",
        match_target_id="cand:per:run:1:p1",
    )
    load_candidate_persons(conn, "run:1")

    persons = conn.execute("SELECT canonical_name FROM persons").fetchall()
    assert len(persons) == 1
    assert persons[0][0] == "重耳"
