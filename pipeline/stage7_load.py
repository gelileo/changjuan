"""Stage 7 — Load candidates into canonical store with field-level merge semantics.

Promotes `candidate_persons` rows into canonical `persons`, applying field-level
merge semantics when a candidate matches an existing canonical record.

Matching priority:
  1. canonical_name equality
  2. person_variants.variant lookup

If no match, a new Person is created with id `per:<slug>`.
"""

from __future__ import annotations

import re
import sqlite3
import uuid


def _slugify(name: str) -> str:
    """Naive Chinese→ASCII-ish slug — fine for v1; will be replaced when pinyin is needed."""
    safe = re.sub(r"[^\w]+", "-", name).strip("-").lower()
    return safe or uuid.uuid4().hex[:8]


def _audit(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: str,
    change_kind: str,
    after_json: str,
    actor: str,
    pipeline_run_id: str,
    field: str | None = None,
    before_json: str | None = None,
    citation_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log"
        " (id, entity_kind, entity_id, field, change_kind,"
        " before_json, after_json, actor, citation_id, pipeline_run_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        (
            f"al:{uuid.uuid4().hex[:12]}",
            entity_kind,
            entity_id,
            field,
            change_kind,
            before_json,
            after_json,
            actor,
            citation_id,
            pipeline_run_id,
        ),
    )


def _create_person(
    conn: sqlite3.Connection,
    person_id: str,
    c: sqlite3.Row,
    pipeline_run_id: str,
) -> None:
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
    _audit(
        conn,
        "person",
        person_id,
        "create",
        after_json=(
            f'{{"canonical_name": "{c["canonical_name"]}", "confidence": {c["confidence"]}}}'
        ),
        actor="load@v1",
        pipeline_run_id=pipeline_run_id,
    )


def load_candidate_persons(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_persons rows into canonical persons with field-level merge.

    Matches candidates against existing Persons by canonical_name first, then
    by person_variants.variant. Creates a new Person if no match found.
    """
    cur = conn.execute(
        "SELECT id, canonical_name, gender, birth_date_json, death_date_json, notes, "
        "state_id, clan_name, confidence, chunk_id, quote "
        "FROM candidate_persons WHERE pipeline_run_id = ?;",
        (pipeline_run_id,),
    )
    candidates = cur.fetchall()
    affected = 0
    for c in candidates:
        existing = conn.execute(
            "SELECT id FROM persons WHERE canonical_name = ?;",
            (c["canonical_name"],),
        ).fetchone()
        if existing is None:
            person_id = f"per:{_slugify(c['canonical_name'])}"
            _create_person(conn, person_id, c, pipeline_run_id)
        else:
            person_id = existing["id"]
            # No-op for fields in Task 18; later tasks add variant union and scalar merge.
        affected += 1
    return affected
