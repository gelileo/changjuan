"""Stage 7 — Load candidates into canonical store with field-level merge semantics.

Promotes `candidate_persons` rows into canonical `persons`, applying field-level
merge semantics when a candidate matches an existing canonical record.

Matching priority:
  1. canonical_name equality
  2. person_variants.variant lookup

If no match, a new Person is created with id `per:<slug>`.
"""

from __future__ import annotations

import json as _json
import re
import sqlite3
import uuid

# Confidence delta below which two values count as "similar" — disagreement triggers Conflict.
_SIMILAR_CONFIDENCE_DELTA = 0.1

_SCALAR_FIELDS = ("gender", "birth_date_json", "death_date_json", "notes", "state_id", "clan_name")


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


def _json_scalar(v: object) -> str:
    return _json.dumps(v, ensure_ascii=False)


def _set_scalar(
    conn: sqlite3.Connection,
    person_id: str,
    field: str,
    value: object,
    confidence: float,
    pipeline_run_id: str,
) -> None:
    conn.execute(
        f"UPDATE persons SET {field} = ?, updated_at = datetime('now') WHERE id = ?;",
        (value, person_id),
    )
    _audit(
        conn,
        "person",
        person_id,
        "set",
        after_json=f'{{"value": {_json_scalar(value)}, "confidence": {confidence}}}',
        actor="load@v1",
        pipeline_run_id=pipeline_run_id,
        field=field,
    )


def _emit_conflict(
    conn: sqlite3.Connection,
    subject_kind: str,
    subject_id: str,
    field: str,
    old_val: object,
    old_conf: float,
    new_val: object,
    new_conf: float,
    pipeline_run_id: str,
) -> None:
    variants = [
        {"value": old_val, "confidence": old_conf, "source": "existing"},
        {"value": new_val, "confidence": new_conf, "source": f"run:{pipeline_run_id}"},
    ]
    best_idx = 0 if old_conf >= new_conf else 1
    conn.execute(
        "INSERT INTO conflicts"
        " (id, subject_kind, subject_id, field, variants_json,"
        " current_best_variant_idx, resolution_rule, status)"
        " VALUES (?, ?, ?, ?, ?, ?, 'highest_confidence', 'open');",
        (
            f"cfl:{uuid.uuid4().hex[:12]}",
            subject_kind,
            subject_id,
            field,
            _json.dumps(variants, ensure_ascii=False),
            best_idx,
        ),
    )


def _merge_scalar_fields(
    conn: sqlite3.Connection,
    person_id: str,
    c: sqlite3.Row,
    pipeline_run_id: str,
) -> None:
    fields_sql = ", ".join(_SCALAR_FIELDS)
    existing = conn.execute(
        f"SELECT provenance, {fields_sql}, confidence FROM persons WHERE id = ?;",
        (person_id,),
    ).fetchone()
    for field in _SCALAR_FIELDS:
        new_val = c[field]
        if new_val is None:
            continue
        old_val = existing[field]
        if old_val == new_val:
            continue
        if old_val is None:
            _set_scalar(conn, person_id, field, new_val, c["confidence"], pipeline_run_id)
            continue
        if existing["provenance"] == "curated":
            _emit_conflict(
                conn,
                "person",
                person_id,
                field,
                old_val,
                existing["confidence"],
                new_val,
                c["confidence"],
                pipeline_run_id,
            )
            continue
        # Both auto: update if new confidence beats old by a meaningful margin.
        if c["confidence"] > existing["confidence"] + _SIMILAR_CONFIDENCE_DELTA:
            _set_scalar(conn, person_id, field, new_val, c["confidence"], pipeline_run_id)
        else:
            _emit_conflict(
                conn,
                "person",
                person_id,
                field,
                old_val,
                existing["confidence"],
                new_val,
                c["confidence"],
                pipeline_run_id,
            )


def _find_existing_person(conn: sqlite3.Connection, name: str) -> str | None:
    """Return the id of an existing Person matching name, or None.

    Checks canonical_name first, then person_variants.variant.
    """
    row = conn.execute("SELECT id FROM persons WHERE canonical_name = ?;", (name,)).fetchone()
    if row is not None:
        return str(row["id"])
    row = conn.execute(
        "SELECT person_id FROM person_variants WHERE variant = ?;", (name,)
    ).fetchone()
    if row is None:
        return None
    return str(row["person_id"])


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
        existing_id = _find_existing_person(conn, c["canonical_name"])
        if existing_id is None:
            person_id = f"per:{_slugify(c['canonical_name'])}"
            _create_person(conn, person_id, c, pipeline_run_id)
        else:
            person_id = existing_id
            _merge_scalar_fields(conn, person_id, c, pipeline_run_id)
        affected += 1
    return affected
