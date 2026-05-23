"""Seed a tiny sqlite DB for stage5_link.merge unit tests.

Builds a DB with two persons (one canonical, one candidate), a merge_candidates
row joining them, and a minimal set of relations on each so FK-retarget
behavior is exercisable.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA


def seed(db_path: Path) -> str:
    """Build a fresh test DB at db_path. Return the merge_candidates id."""
    with connect(db_path) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        _seed_persons(conn)
        _seed_relations(conn)
        return _seed_merge_candidate(conn)


def _seed_persons(conn: sqlite3.Connection) -> None:
    # canonical: per:周宣王 (the survivor)
    conn.execute(
        "INSERT INTO persons (id, canonical_name, gender, clan_name, confidence, provenance)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("per:test:canonical", "周宣王", "M", "姬", 0.9, "auto"),
    )
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) VALUES (?, ?, ?, ?)",
        ("pv:test:c:1", "per:test:canonical", "宣王", "谥号"),
    )
    # candidate: a candidate_persons row that looks like the same person
    conn.execute(
        "INSERT INTO persons (id, canonical_name, gender, clan_name, confidence, provenance)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("per:test:candidate", "周宣王", "M", None, 0.7, "auto"),
    )
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) VALUES (?, ?, ?, ?)",
        ("pv:test:cand:1", "per:test:candidate", "周宣王", "谥号"),
    )


def _seed_relations(conn: sqlite3.Connection) -> None:
    # a minimal event + participants so accept_merge has FKs to retarget
    conn.execute(
        "INSERT INTO events (id, type, outcome, summary, confidence, provenance)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("evt:test:1", "battle", "outcome text", "summary text", 0.9, "auto"),
    )
    conn.execute(
        "INSERT INTO event_participants"
        " (event_id, person_id, role, confidence, provenance) VALUES (?, ?, ?, ?, ?)",
        ("evt:test:1", "per:test:candidate", "victor", 0.9, "auto"),
    )


def _seed_merge_candidate(conn: sqlite3.Connection) -> str:
    mc_id = "mc:test:1"
    conn.execute(
        "INSERT INTO merge_candidates "
        "(id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'open')",
        (
            mc_id,
            "person",
            "per:test:candidate",  # A is the candidate (will be folded away)
            "per:test:canonical",  # B is the canonical (survivor)
            0.7,
            json.dumps({"features": {"variant_overlap": "strong"}, "score": 0.7}),
        ),
    )
    return mc_id
