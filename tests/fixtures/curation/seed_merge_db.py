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


def add_event_participants_collision(db_path: Path) -> None:
    """Both candidate AND canonical play 'victor' in evt:test:1.

    After the seeder, event_participants has the candidate row only. This
    helper adds a canonical row with the same (event_id, role), forcing a
    PK collision on retarget. Confidence of the canonical row is higher
    so it should be the survivor.
    """
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO event_participants "
            "(event_id, person_id, role, confidence, provenance) "
            "VALUES ('evt:test:1', 'per:test:canonical', 'victor', 0.95, 'auto')",
        )


def add_person_relations_self_loop(db_path: Path) -> None:
    """Candidate has a 'spouse' relation TO the canonical.

    After merge, this would become (canonical, canonical, 'spouse') — a self-loop.
    The merge function should delete the relation outright.
    """
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO person_relations "
            "(from_person_id, to_person_id, kind, confidence, provenance) "
            "VALUES ('per:test:candidate', 'per:test:canonical', 'spouse', 0.9, 'auto')",
        )


def add_person_states_collision(db_path: Path) -> None:
    """Both rows are 'ruler' of sta:周 with the same from_date_json (NULL).

    The canonical row has higher confidence and wins.
    """
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO states (id, name, type, confidence, provenance) "
            "VALUES ('sta:周', '周', 'state', 0.9, 'auto')"
        )
        conn.execute(
            "INSERT INTO person_states "
            "(person_id, state_id, role, confidence, provenance) "
            "VALUES ('per:test:candidate', 'sta:周', 'ruler', 0.8, 'auto')"
        )
        conn.execute(
            "INSERT INTO person_states "
            "(person_id, state_id, role, confidence, provenance) "
            "VALUES ('per:test:canonical', 'sta:周', 'ruler', 0.95, 'auto')"
        )


def add_entity_citations_duplicate(db_path: Path) -> None:
    """Both rows reference the same citation. Candidate's row should drop silently."""
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
            "VALUES ('person', 'per:test:candidate', 'cite:test:1')"
        )
        conn.execute(
            "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
            "VALUES ('person', 'per:test:canonical', 'cite:test:1')"
        )


def seed_with_candidate_in_candidate_persons(db_path: Path) -> str:
    """Variant of seed() where candidate_a_id points at candidate_persons.

    This is the layout that the live DB actually uses. Returns the
    merge_candidates id.
    """
    import json as _json

    with connect(db_path) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Canonical only (B side).
        conn.execute(
            "INSERT INTO persons (id, canonical_name, gender, clan_name, confidence, provenance) "
            "VALUES ('per:test:canonical', '周宣王', 'M', '姬', 0.9, 'curated')",
        )
        conn.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind) "
            "VALUES ('pv:test:c:1', 'per:test:canonical', '宣王', '谥号')",
        )
        # A side: candidate_persons row.
        conn.execute(
            "INSERT INTO candidate_persons "
            "(id, canonical_name, gender, state_id, confidence, "
            "pipeline_run_id, chunk_id, quote, variants_json) "
            "VALUES ('cand:per:test:p1', '周宣王', 'M', 's1', 0.85, "
            "'run:test', 'chunk:1', 'quote text', ?)",
            (
                _json.dumps(
                    [{"variant": "宣王", "kind": "谥号"}, {"variant": "靖", "kind": "本名"}]
                ),
            ),
        )
        mc_id = "mc:test:cand:1"
        conn.execute(
            "INSERT INTO merge_candidates "
            "(id, kind, candidate_a_id, candidate_b_id, score, status) "
            "VALUES (?, 'person', 'cand:per:test:p1', 'per:test:canonical', 0.7, 'open')",
            (mc_id,),
        )
        return mc_id
