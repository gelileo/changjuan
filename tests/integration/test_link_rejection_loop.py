"""Integration test: linker honors rejected_merges on subsequent runs.

Seeds a candidate that scores into the queue threshold, runs the linker
(yields a merge_candidates row), rejects it (writes rejected_merges),
runs the linker again (must NOT re-emit the rejected pair). Also
exercises the --ignore-rejections override.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator

import pytest

from pipeline.db import apply_schema
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage5_link import link_run
from pipeline.stage5_link.merge import reject_merge


def _seed_minimal_world(conn: sqlite3.Connection) -> tuple[str, str]:
    """Return (canonical_persons_id, candidate_persons_id) plumbed to score into queue range."""
    canonical_id = "p:canonical-A"
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES (?, '申侯', 0.95, 'auto')",
        (canonical_id,),
    )
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) "
        "VALUES ('pv:1', ?, '申侯', '别名'), ('pv:2', ?, '申伯', '别名')",
        (canonical_id, canonical_id),
    )
    cand_id = "cp:申侯-runX"
    run_id = "run:test-link-rejection"
    conn.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, variants_json, confidence, pipeline_run_id, "
        " chunk_id, quote) "
        "VALUES (?, '申侯', ?, 0.7, ?, 'chk:test', '...')",
        (cand_id, json.dumps([{"variant": "申侯"}, {"variant": "申伯"}]), run_id),
    )
    conn.commit()
    return canonical_id, run_id


def _open_mc_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM merge_candidates WHERE status = 'open'").fetchone()
    return int(row[0])


@pytest.fixture
def conn() -> Generator[sqlite3.Connection, None, None]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c, CANONICAL_SCHEMA)
    yield c
    c.close()


def test_link_then_reject_then_link_does_not_reflag(conn: sqlite3.Connection) -> None:
    canonical_id, run_id = _seed_minimal_world(conn)

    stats1 = link_run(conn, run_id)
    assert stats1["queued"] == 1
    assert _open_mc_count(conn) == 1

    mc_id = conn.execute("SELECT id FROM merge_candidates WHERE status = 'open'").fetchone()["id"]
    reject_merge(conn, mc_id, note="test rejection")
    conn.commit()

    # Re-link the same run. The linker should now skip the previously-rejected pair.
    stats2 = link_run(conn, run_id)
    assert stats2["queued"] == 0, "linker re-flagged a rejected pair"
    assert stats2.get("rejected_filter_skipped", 0) >= 1


def test_ignore_rejections_bypasses_filter(conn: sqlite3.Connection) -> None:
    canonical_id, run_id = _seed_minimal_world(conn)

    link_run(conn, run_id)
    mc_id = conn.execute("SELECT id FROM merge_candidates WHERE status = 'open'").fetchone()["id"]
    reject_merge(conn, mc_id)
    conn.commit()

    # With ignore_rejections=True the filter is bypassed and the pair is re-emitted.
    stats = link_run(conn, run_id, ignore_rejections=True)
    assert stats["queued"] == 1
