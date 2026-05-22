"""candidate_pool — relevance pre-filter for the Stage 5 linker."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage5_link.candidate_pool import candidate_pool


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_candidate(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    cand_id: str,
    name: str,
    state_id: str | None = None,
    variants: list[str] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, state_id, chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'chk:t', '', 0.9, ?)",
        (cand_id, name, state_id, run_id),
    )
    for v in variants or []:
        conn.execute(
            "INSERT INTO candidate_person_variants (id, candidate_person_id, variant, kind) "
            "VALUES (?, ?, ?, ?)",
            (f"{cand_id}-v-{v}", cand_id, v, "别名"),
        )
    conn.commit()


def _seed_canonical(
    conn: sqlite3.Connection, *, person_id: str, name: str, state_id: str | None = None
) -> None:
    if state_id is not None:
        conn.execute(
            "INSERT OR IGNORE INTO states (id, name, provenance, confidence, pipeline_run_id) "
            "VALUES (?, ?, 'auto', 0.9, 'run:test')",
            (state_id, state_id),
        )
    conn.execute(
        "INSERT INTO persons "
        "(id, canonical_name, state_id, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'auto', 0.9, 'run:test')",
        (person_id, name, state_id),
    )
    conn.commit()


def test_pool_includes_canonical_with_shared_canonical_name(conn: sqlite3.Connection) -> None:
    _seed_canonical(conn, person_id="per:zhong-er", name="重耳", state_id="sta:jin")
    _seed_candidate(
        conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳", state_id="sta:jin"
    )
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert any(p["canonical_name"] == "重耳" for p in pool)
    assert any(p["target_kind"] == "canonical" for p in pool)


def test_pool_includes_same_run_sibling_with_overlap(conn: sqlite3.Connection) -> None:
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p2", name="重耳")  # sibling
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert any(p["target_kind"] == "candidate" for p in pool)


def test_pool_excludes_self(conn: sqlite3.Connection) -> None:
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert all(p.get("target_id") != "cand:per:run:1:p1" for p in pool)


def test_pool_excludes_other_run_candidates(conn: sqlite3.Connection) -> None:
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    _seed_candidate(conn, run_id="run:OTHER", cand_id="cand:per:run:OTHER:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert all(p["target_id"] != "cand:per:run:OTHER:p1" for p in pool)


def test_pool_excludes_no_overlap_canonical(conn: sqlite3.Connection) -> None:
    _seed_canonical(conn, person_id="per:zhong-shan-fu", name="仲山甫")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert all(p["canonical_name"] != "仲山甫" for p in pool)


def test_pool_includes_variant_match(conn: sqlite3.Connection) -> None:
    _seed_canonical(conn, person_id="per:jin-wen-gong", name="晋文公")
    # Seed a person_variants row linking 晋文公 to variant "重耳"
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) "
        "VALUES ('pv:1', 'per:jin-wen-gong', '重耳', '本名')"
    )
    conn.commit()
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert any(p["canonical_name"] == "晋文公" for p in pool)


def test_pool_handles_malformed_date_json(conn: sqlite3.Connection) -> None:
    """A candidate with malformed date_json should appear in pool with date=None,
    not crash the linker."""
    _seed_candidate(
        conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳", state_id="sta:jin"
    )
    # Write a malformed JSON blob directly
    conn.execute(
        "UPDATE candidate_persons SET birth_date_json='{not json' WHERE id='cand:per:run:1:p1'"
    )
    _seed_candidate(
        conn, run_id="run:1", cand_id="cand:per:run:1:p2", name="重耳", state_id="sta:jin"
    )
    conn.commit()
    pool = candidate_pool(conn, "cand:per:run:1:p2", "run:1")
    # Should include p1 in pool with birth_date=None (no crash).
    p1_entry = next((p for p in pool if p["target_id"] == "cand:per:run:1:p1"), None)
    assert p1_entry is not None
    assert p1_entry["birth_date"] is None
