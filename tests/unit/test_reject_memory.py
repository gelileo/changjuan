"""Unit tests for reject_merge's Phase 6 rejected_merges side effect.

Covers:
  - When candidate A is in candidate_persons (the typical Phase 5.1 case),
    reject_merge writes a rejected_merges row with the correct fingerprint
    and audit_log_id linkage inside a single transaction.
  - Second rejection of the same (canonical_id, fingerprint) is idempotent
    (INSERT OR IGNORE).
  - When candidate A is in persons (escape-hatch case from Phase 5.1),
    variants come from person_variants and the row still writes.
"""

from __future__ import annotations

import json
import sqlite3

from pipeline.db import apply_schema
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage5_link.fingerprint import candidate_fingerprint
from pipeline.stage5_link.merge import reject_merge


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn, CANONICAL_SCHEMA)
    return conn


def _seed_canonical_b(conn: sqlite3.Connection, person_id: str = "p:survivor") -> str:
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES (?, '宣王', 0.95, 'auto')",
        (person_id,),
    )
    return person_id


def _seed_candidate_a_in_candidate_persons(
    conn: sqlite3.Connection,
    cand_id: str = "cp:申侯-run1",
    name: str = "申侯",
    variants: list[str] | None = None,
) -> str:
    if variants is None:
        variants = ["申侯", "申伯"]
    conn.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, variants_json, confidence, pipeline_run_id, "
        " chunk_id, quote) "
        "VALUES (?, ?, ?, 0.7, 'run:test', 'chk:test', '...')",
        (cand_id, name, json.dumps([{"variant": v} for v in variants])),
    )
    return cand_id


def _seed_open_mc(
    conn: sqlite3.Connection,
    *,
    mc_id: str = "mc:test1",
    cand_a: str,
    cand_b: str,
) -> str:
    conn.execute(
        "INSERT INTO merge_candidates "
        "(id, kind, candidate_a_id, candidate_b_id, score, status) "
        "VALUES (?, 'person', ?, ?, 0.6, 'open')",
        (mc_id, cand_a, cand_b),
    )
    return mc_id


def test_reject_writes_rejected_merges_row() -> None:
    conn = _fresh_db()
    canonical_id = _seed_canonical_b(conn)
    cand_id = _seed_candidate_a_in_candidate_persons(conn)
    mc_id = _seed_open_mc(conn, cand_a=cand_id, cand_b=canonical_id)
    conn.commit()

    reject_merge(conn, mc_id, note="not the same person")

    rows = conn.execute(
        "SELECT canonical_id, candidate_fingerprint, audit_log_id " "FROM rejected_merges"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["canonical_id"] == canonical_id
    expected_fp = candidate_fingerprint("申侯", ["申侯", "申伯"])
    assert row["candidate_fingerprint"] == expected_fp
    assert row["audit_log_id"] is not None
    # audit_log_id must reference a real audit row
    audit = conn.execute(
        "SELECT change_kind FROM audit_log WHERE id = ?", (row["audit_log_id"],)
    ).fetchone()
    assert audit is not None
    assert audit["change_kind"] == "merge_rejected"


def test_reject_is_idempotent_on_duplicate() -> None:
    conn = _fresh_db()
    canonical_id = _seed_canonical_b(conn)
    cand_id = _seed_candidate_a_in_candidate_persons(conn)
    mc_id1 = _seed_open_mc(conn, mc_id="mc:1", cand_a=cand_id, cand_b=canonical_id)
    mc_id2 = _seed_open_mc(conn, mc_id="mc:2", cand_a=cand_id, cand_b=canonical_id)
    conn.commit()

    reject_merge(conn, mc_id1)
    reject_merge(conn, mc_id2)

    count = conn.execute("SELECT COUNT(*) FROM rejected_merges").fetchone()[0]
    assert count == 1  # second insert hit INSERT OR IGNORE


def test_reject_from_persons_side_candidate_a() -> None:
    """Phase 5.1 escape-hatch case: candidate A lives in persons."""
    conn = _fresh_db()
    # A and B both in persons (the rare case)
    canonical_id = _seed_canonical_b(conn, person_id="p:B")
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES ('p:A', '申侯', 0.85, 'auto')"
    )
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) "
        "VALUES ('pv:1', 'p:A', '申侯', '本名'), ('pv:2', 'p:A', '申伯', '别名')"
    )
    mc_id = _seed_open_mc(conn, cand_a="p:A", cand_b=canonical_id)
    conn.commit()

    reject_merge(conn, mc_id)

    row = conn.execute("SELECT canonical_id, candidate_fingerprint FROM rejected_merges").fetchone()
    assert row is not None
    # In the persons-side case, the spec (§3.3 step 3) says "treat A's id as
    # the canonical_id" — the rejected pair is "don't merge B into A".
    assert row["canonical_id"] == "p:A"
    expected_fp = candidate_fingerprint("申侯", ["申侯", "申伯"])
    assert row["candidate_fingerprint"] == expected_fp
