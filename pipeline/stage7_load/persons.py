from __future__ import annotations

import hashlib
import json as _json
import logging
import sqlite3
import uuid

from pipeline.stage7_load.audit import _audit
from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.helpers import (
    _PERSON_SCALAR_FIELDS,
    _SIMILAR_CONFIDENCE_DELTA,
    _slugify,
)

log = logging.getLogger(__name__)


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


def _scalars_equal(field: str, old_val: object, new_val: object) -> bool:
    """Return True if old_val and new_val are semantically equal for this field.

    For *_json fields, deserializes both values and compares as Python objects so
    that two JSON strings with the same content but different key orderings are
    treated as equal, preventing spurious Conflicts.
    """
    if old_val is None and new_val is None:
        return True
    if old_val is None or new_val is None:
        return False
    if field.endswith("_json"):
        try:
            return bool(_json.loads(str(old_val)) == _json.loads(str(new_val)))
        except (_json.JSONDecodeError, TypeError):
            pass  # fall through to string comparison
    return old_val == new_val


def _last_field_confidence(
    conn: sqlite3.Connection, entity_kind: str, entity_id: str, field: str
) -> float | None:
    """Return the confidence recorded in the most recent set-event for this field, or None.

    Looks up the audit_log for the most recent 'set' change for the given field.
    Returns None if no prior set-event exists (field was never updated since creation).
    """
    row = conn.execute(
        "SELECT json_extract(after_json, '$.confidence') AS c "
        "FROM audit_log WHERE entity_kind = ? AND entity_id = ? AND field = ? "
        "ORDER BY at DESC, id DESC LIMIT 1;",
        (entity_kind, entity_id, field),
    ).fetchone()
    if row is None or row["c"] is None:
        return None
    return float(row["c"])


def _merge_scalar_fields(
    conn: sqlite3.Connection,
    person_id: str,
    c: sqlite3.Row,
    pipeline_run_id: str,
) -> None:
    fields_sql = ", ".join(_PERSON_SCALAR_FIELDS)
    existing = conn.execute(
        f"SELECT provenance, {fields_sql}, confidence FROM persons WHERE id = ?;",
        (person_id,),
    ).fetchone()
    for field in _PERSON_SCALAR_FIELDS:
        new_val = c[field]
        if new_val is None:
            continue
        old_val = existing[field]
        if _scalars_equal(field, old_val, new_val):
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
        # Both auto: use per-field confidence from audit_log (most recent set-event),
        # falling back to the row-level confidence only if no prior set-event exists.
        prior_confidence = (
            _last_field_confidence(conn, "person", person_id, field) or existing["confidence"]
        )
        if c["confidence"] > prior_confidence + _SIMILAR_CONFIDENCE_DELTA:
            _set_scalar(conn, person_id, field, new_val, c["confidence"], pipeline_run_id)
        else:
            _emit_conflict(
                conn,
                "person",
                person_id,
                field,
                old_val,
                prior_confidence,
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


def _write_variants(
    conn: sqlite3.Connection,
    person_id: str,
    variants_json: str | None,
) -> None:
    """Write person_variants rows from a JSON-encoded variants list.

    Each entry in the list is ``{"variant": str, "kind": str}``.
    Uses INSERT OR IGNORE so duplicate (person_id, variant, kind) tuples are silently
    dropped — idempotent across re-extract runs. The surrogate id is derived as a
    6-char SHA-256 hex digest of ``person_id + variant + kind`` to avoid slug collisions.
    """
    if not variants_json:
        return
    import json as _json_local

    try:
        entries = _json_local.loads(variants_json)
    except (_json_local.JSONDecodeError, TypeError):
        return
    for entry in entries:
        variant = entry.get("variant", "")
        kind = entry.get("kind", "别名")
        if not variant:
            continue
        h = hashlib.sha256(f"{person_id}:{variant}:{kind}".encode()).hexdigest()[:8]
        variant_id = f"pv:{h}"
        conn.execute(
            "INSERT OR IGNORE INTO person_variants (id, person_id, variant, kind) "
            "VALUES (?, ?, ?, ?);",
            (variant_id, person_id, variant, kind),
        )


def _resolve_canonical_for_candidate_id(
    conn: sqlite3.Connection,
    target_ref: str,
    local_canonical_map: dict[str, str],
) -> str | None:
    """Resolve match_target_id to a canonical Person id.

    target_ref may be:
      - A canonical id like 'per:zhou-xuan-wang' → return it if it exists in persons.
      - A same-run candidate id like 'cand:per:run:1:p1' → look up in
        local_canonical_map (already-processed-in-this-load-pass siblings).

    Returns None if the target doesn't resolve.
    """
    if target_ref.startswith("cand:"):
        return local_canonical_map.get(target_ref)
    row = conn.execute("SELECT id FROM persons WHERE id = ?;", (target_ref,)).fetchone()
    if row is None:
        return None
    return str(row["id"])


def load_candidate_persons(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_persons rows into canonical persons with field-level merge.

    Matches candidates against existing Persons by canonical_name first, then
    by person_variants.variant. Creates a new Person if no match found.
    Variants from the extraction (variants_json) are written to person_variants
    idempotently so that successive runs accumulate without duplicating.
    """
    cur = conn.execute(
        "SELECT id, canonical_name, gender, birth_date_json, death_date_json, notes, "
        "state_id, clan_name, confidence, chunk_id, quote, variants_json, match_target_id "
        "FROM candidate_persons WHERE pipeline_run_id = ?;",
        (pipeline_run_id,),
    )
    candidates = cur.fetchall()
    affected = 0
    local_canonical_map: dict[str, str] = {}
    for c in candidates:
        # Phase 3: honor match_target_id if Stage 5 set it.
        target_id_raw = c["match_target_id"]
        existing_id: str | None = None
        if target_id_raw is not None:
            existing_id = _resolve_canonical_for_candidate_id(
                conn, target_id_raw, local_canonical_map
            )
            if existing_id is None:
                log.warning(
                    "candidate %s has match_target_id=%s but resolution returned no canonical; "
                    "falling through to canonical_name match",
                    c["id"],
                    target_id_raw,
                )

        # Fall back to canonical_name match if match_target_id didn't resolve.
        if existing_id is None:
            existing_id = _find_existing_person(conn, c["canonical_name"])

        if existing_id is None:
            person_id = f"per:{_slugify(c['canonical_name'])}"
            # Guard against slug collisions: if a different Person already holds this id,
            # append a 6-char SHA-256 hex suffix derived from the canonical_name.
            existing_id_row = conn.execute(
                "SELECT 1 FROM persons WHERE id = ?;", (person_id,)
            ).fetchone()
            if existing_id_row is not None:
                h = hashlib.sha256(c["canonical_name"].encode("utf-8")).hexdigest()[:6]
                person_id = f"{person_id}-{h}"
            _create_person(conn, person_id, c, pipeline_run_id)
        else:
            person_id = existing_id
            _merge_scalar_fields(conn, person_id, c, pipeline_run_id)

        # Record in map for cross-run chain resolution by later siblings in this pass.
        local_canonical_map[c["id"]] = person_id

        _write_variants(conn, person_id, c["variants_json"])
        record_citation(conn, "person", person_id, c["chunk_id"])
        affected += 1
    return affected
