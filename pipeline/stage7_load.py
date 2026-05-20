"""Stage 7 — Load candidates into canonical store with field-level merge semantics.

This task implements only the simple case: a candidate Person that does not match
any existing canonical Person becomes a new canonical Person. Subsequent tasks
add: name-variant union, scalar field merging, Conflict emission, and respect for
curator overrides.
"""

from __future__ import annotations

import re
import sqlite3
import uuid


def _slugify(name: str) -> str:
    """Naive Chinese→ASCII-ish slug — fine for v1; will be replaced when pinyin is needed."""
    safe = re.sub(r"[^\w]+", "-", name).strip("-").lower()
    return safe or uuid.uuid4().hex[:8]


def load_candidate_persons(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote unmatched candidate_persons rows into canonical persons.

    Naive matcher for Task 17: no linking yet. Every candidate becomes a new
    canonical Person whose id is `per:<slug>` or `per:_<hash>` for fallback.
    Task 18+ add variant union, scalar merge, conflict emission.
    """
    cur = conn.execute(
        "SELECT id, canonical_name, gender, birth_date_json, death_date_json, notes, "
        "state_id, clan_name, confidence, chunk_id, quote "
        "FROM candidate_persons WHERE pipeline_run_id = ?;",
        (pipeline_run_id,),
    )
    candidates = cur.fetchall()
    inserted = 0
    for c in candidates:
        person_id = f"per:{_slugify(c['canonical_name'])}"
        # If id collision, append a hash suffix
        existing = conn.execute("SELECT 1 FROM persons WHERE id = ?;", (person_id,)).fetchone()
        if existing is not None:
            person_id = f"{person_id}-{uuid.uuid4().hex[:6]}"
        conn.execute(
            """
            INSERT INTO persons
                (id, canonical_name, gender, birth_date_json, death_date_json, notes,
                 state_id, clan_name, confidence, provenance, pipeline_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'auto', ?);
            """,
            (
                person_id,
                c["canonical_name"],
                c["gender"],
                c["birth_date_json"],
                c["death_date_json"],
                c["notes"],
                c["state_id"],
                c["clan_name"],
                c["confidence"],
                pipeline_run_id,
            ),
        )
        audit_id = f"al:{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO audit_log
                (id, entity_kind, entity_id, change_kind,
                 before_json, after_json, actor, pipeline_run_id)
            VALUES (?, 'person', ?, 'create', NULL, ?, ?, ?);
            """,
            (
                audit_id,
                person_id,
                f'{{"canonical_name": "{c["canonical_name"]}", "confidence": {c["confidence"]}}}',
                "load@v1",
                pipeline_run_id,
            ),
        )
        inserted += 1
    return inserted
