"""Stage 7 — load_candidate_events.

Match key: composite (type, year_bce, primary_place_id).
- year_bce is extracted from the candidate's date_json via json_extract.
- Two candidates at the same place in the same year with the same type collapse
  to one canonical event.

Scalar fields merged: type, outcome, summary, primary_place_id, date_json.
- date_json is merged via merge_date_field (more-precise-date-wins per spec §7.2).
- Other scalars use higher-confidence-wins semantics; disagreements at similar
  confidence emit Conflict rows (same pattern as persons.py).

ID format: evt:<slug>-<year>bce  (or  evt:<slug>  when no year in date_json).
Slug collision guard: append 6-char SHA-256 suffix if needed.
"""

from __future__ import annotations

import json as _json
import sqlite3
import uuid
from typing import Any

from pipeline.stage7_load.audit import _audit
from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.helpers import (
    _SIMILAR_CONFIDENCE_DELTA,
    _slugify,
    merge_date_field,
)
from pipeline.stage7_load.id_maps import build_place_id_map

# Scalar fields that go through the standard merge loop (non-date scalars).
# Positional order must match the SELECT in _merge_event_fields.
_EVENT_SCALAR_FIELDS = ("type", "outcome", "summary", "primary_place_id")

# Column index map for candidate_events SELECT results (positional access).
# SELECT id, type, date_json, outcome, summary, primary_place_id, confidence, chunk_id
_CI_ID = 0
_CI_TYPE = 1
_CI_DATE_JSON = 2
_CI_OUTCOME = 3
_CI_SUMMARY = 4
_CI_PRIMARY_PLACE_ID = 5
_CI_CONFIDENCE = 6
_CI_CHUNK_ID = 7

# Column index map for canonical events SELECT in _merge_event_fields.
# SELECT provenance, type, outcome, summary, primary_place_id, date_json, confidence
_EI_PROVENANCE = 0
_EI_TYPE = 1
_EI_OUTCOME = 2
_EI_SUMMARY = 3
_EI_PRIMARY_PLACE_ID = 4
_EI_DATE_JSON = 5
_EI_CONFIDENCE = 6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _json_scalar(v: object) -> str:
    return _json.dumps(v, ensure_ascii=False)


def _scalars_equal(field: str, old_val: object, new_val: object) -> bool:
    """Return True if old_val and new_val are semantically equal for this field."""
    if old_val is None and new_val is None:
        return True
    if old_val is None or new_val is None:
        return False
    if field.endswith("_json"):
        try:
            return bool(_json.loads(str(old_val)) == _json.loads(str(new_val)))
        except (_json.JSONDecodeError, TypeError):
            pass
    return old_val == new_val


def _last_field_confidence(
    conn: sqlite3.Connection, entity_kind: str, entity_id: str, field: str
) -> float | None:
    """Return the confidence in the most-recent set-event for this field, or None."""
    row = conn.execute(
        "SELECT json_extract(after_json, '$.confidence') AS c "
        "FROM audit_log WHERE entity_kind = ? AND entity_id = ? AND field = ? "
        "ORDER BY at DESC, id DESC LIMIT 1;",
        (entity_kind, entity_id, field),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])


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


def _set_field(
    conn: sqlite3.Connection,
    event_id: str,
    field: str,
    value: object,
    confidence: float,
    pipeline_run_id: str,
    before_val: object = None,
    before_conf: float | None = None,
) -> None:
    conn.execute(
        f"UPDATE events SET {field} = ?, updated_at = datetime('now') WHERE id = ?;",
        (value, event_id),
    )
    before_json: str | None = None
    if before_val is not None and before_conf is not None:
        before_json = _json_scalar({"value": before_val, "confidence": before_conf})
    _audit(
        conn,
        "event",
        event_id,
        "set",
        after_json=_json_scalar({"value": value, "confidence": confidence}),
        before_json=before_json,
        actor="load@v1",
        pipeline_run_id=pipeline_run_id,
        field=field,
    )


# ---------------------------------------------------------------------------
# Match-key extraction
# ---------------------------------------------------------------------------


def _year_bce_from_date_json(date_json: str | None) -> int | None:
    """Extract year_bce from a date_json string, or return None."""
    if date_json is None:
        return None
    try:
        d: Any = _json.loads(date_json)
        val = d.get("year_bce")
        return int(val) if val is not None else None
    except (_json.JSONDecodeError, TypeError, ValueError):
        return None


def _build_event_id(conn: sqlite3.Connection, event_type: str, year_bce: int | None) -> str:
    """Build a slug-based event id, appending an incrementing counter on collision.

    The base form is ``evt:{slug}`` (or ``evt:{slug}-{year_bce}bce`` when dated);
    if that id already exists, we try ``-2``, ``-3``, ... until we find a free
    one. A deterministic SHA256 suffix was used previously but collided when
    multiple new events shared the same base id within one pipeline run (e.g.
    several 战 events at different places) — every candidate hashed to the same
    suffix, breaking the second INSERT. See `concepts/pipeline/load-and-merge.md`.
    """
    slug = _slugify(event_type)
    if year_bce is not None:
        base = f"evt:{slug}-{year_bce}bce"
    else:
        base = f"evt:{slug}"
    event_id = base
    n = 2
    while conn.execute("SELECT 1 FROM events WHERE id = ?;", (event_id,)).fetchone() is not None:
        event_id = f"{base}-{n}"
        n += 1
    return event_id


def _find_existing_event(
    conn: sqlite3.Connection,
    event_type: str,
    year_bce: int | None,
    primary_place_id: str | None,
) -> str | None:
    """Return the id of an existing Event matching the composite key, or None."""
    if year_bce is None and primary_place_id is None:
        row = conn.execute(
            "SELECT id FROM events WHERE type = ? "
            "AND json_extract(date_json, '$.year_bce') IS NULL "
            "AND primary_place_id IS NULL;",
            (event_type,),
        ).fetchone()
    elif year_bce is None:
        row = conn.execute(
            "SELECT id FROM events WHERE type = ? "
            "AND json_extract(date_json, '$.year_bce') IS NULL "
            "AND primary_place_id = ?;",
            (event_type, primary_place_id),
        ).fetchone()
    elif primary_place_id is None:
        row = conn.execute(
            "SELECT id FROM events WHERE type = ? "
            "AND CAST(json_extract(date_json, '$.year_bce') AS INTEGER) = ? "
            "AND primary_place_id IS NULL;",
            (event_type, year_bce),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM events WHERE type = ? "
            "AND CAST(json_extract(date_json, '$.year_bce') AS INTEGER) = ? "
            "AND primary_place_id = ?;",
            (event_type, year_bce, primary_place_id),
        ).fetchone()
    return str(row[0]) if row is not None else None


# ---------------------------------------------------------------------------
# Create / merge
# ---------------------------------------------------------------------------


def _create_event(
    conn: sqlite3.Connection,
    event_id: str,
    c: tuple[Any, ...],
    pipeline_run_id: str,
    resolved_primary_place_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO events "
        "(id, type, date_json, outcome, summary, primary_place_id, "
        "confidence, provenance, pipeline_run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'auto', ?);",
        (
            event_id,
            c[_CI_TYPE],
            c[_CI_DATE_JSON],
            c[_CI_OUTCOME],
            c[_CI_SUMMARY],
            resolved_primary_place_id
            if resolved_primary_place_id is not None
            else c[_CI_PRIMARY_PLACE_ID],
            c[_CI_CONFIDENCE],
            pipeline_run_id,
        ),
    )
    _audit(
        conn,
        "event",
        event_id,
        "create",
        after_json=_json_scalar({"type": c[_CI_TYPE], "confidence": c[_CI_CONFIDENCE]}),
        actor="load@v1",
        pipeline_run_id=pipeline_run_id,
    )


def _merge_event_fields(
    conn: sqlite3.Connection,
    event_id: str,
    c: tuple[Any, ...],
    pipeline_run_id: str,
    resolved_primary_place_id: str | None = None,
) -> None:
    """Merge candidate fields into an existing canonical event.

    `resolved_primary_place_id` is the canonical place id resolved from the
    candidate's local extraction id (e.g. 'pl1' → 'pla:qishan'); used in place
    of c[_CI_PRIMARY_PLACE_ID] for FK safety. Other scalars unchanged.
    """
    # SELECT provenance, type, outcome, summary, primary_place_id, date_json, confidence
    existing = conn.execute(
        "SELECT provenance, type, outcome, summary, primary_place_id, date_json, confidence "
        "FROM events WHERE id = ?;",
        (event_id,),
    ).fetchone()
    assert existing is not None

    cur_conf = float(existing[_EI_CONFIDENCE] or 0.0)
    cand_conf = float(c[_CI_CONFIDENCE])

    # --- date_json merge (semantic: more-precise-wins via merge_date_field) ---
    new_date_json_str: str | None = c[_CI_DATE_JSON]
    old_date_json_str: str | None = existing[_EI_DATE_JSON]
    if new_date_json_str is not None:
        old_date_entry: dict[str, Any] | None = None
        new_date_entry: dict[str, Any] | None = None
        try:
            old_parsed: Any = _json.loads(str(old_date_json_str)) if old_date_json_str else None
            old_date_entry = {"value": old_parsed, "confidence": cur_conf} if old_parsed else None
        except (_json.JSONDecodeError, TypeError):
            pass
        try:
            new_parsed: Any = _json.loads(str(new_date_json_str))
            new_date_entry = {"value": new_parsed, "confidence": cand_conf}
        except (_json.JSONDecodeError, TypeError):
            pass

        if new_date_entry is not None:
            winner = merge_date_field(old_date_entry, new_date_entry)
            if winner is new_date_entry and not _scalars_equal(
                "date_json", old_date_json_str, new_date_json_str
            ):
                _set_field(
                    conn,
                    event_id,
                    "date_json",
                    new_date_json_str,
                    cand_conf,
                    pipeline_run_id,
                    before_val=old_date_json_str,
                    before_conf=cur_conf,
                )

    # --- standard scalar fields: type, outcome, summary, primary_place_id ---
    # Existing positional indices for these fields:
    existing_scalar_vals = (
        existing[_EI_TYPE],
        existing[_EI_OUTCOME],
        existing[_EI_SUMMARY],
        existing[_EI_PRIMARY_PLACE_ID],
    )
    cand_scalar_vals = (
        c[_CI_TYPE],
        c[_CI_OUTCOME],
        c[_CI_SUMMARY],
        resolved_primary_place_id
        if resolved_primary_place_id is not None
        else c[_CI_PRIMARY_PLACE_ID],
    )

    for idx, field in enumerate(_EVENT_SCALAR_FIELDS):
        new_val = cand_scalar_vals[idx]
        if new_val is None:
            continue
        old_val = existing_scalar_vals[idx]
        if _scalars_equal(field, old_val, new_val):
            continue
        if old_val is None:
            _set_field(conn, event_id, field, new_val, cand_conf, pipeline_run_id)
            continue
        if existing[_EI_PROVENANCE] == "curated":
            _emit_conflict(
                conn,
                "event",
                event_id,
                field,
                old_val,
                cur_conf,
                new_val,
                cand_conf,
                pipeline_run_id,
            )
            continue
        # Both auto: per-field confidence from audit_log, fallback to row-level.
        prior_conf = _last_field_confidence(conn, "event", event_id, field) or cur_conf
        if cand_conf > prior_conf + _SIMILAR_CONFIDENCE_DELTA:
            _set_field(
                conn,
                event_id,
                field,
                new_val,
                cand_conf,
                pipeline_run_id,
                before_val=old_val,
                before_conf=prior_conf,
            )
        else:
            _emit_conflict(
                conn,
                "event",
                event_id,
                field,
                old_val,
                prior_conf,
                new_val,
                cand_conf,
                pipeline_run_id,
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_candidate_events(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_events rows tagged with pipeline_run_id into canonical events.

    Matches candidates against existing Events by composite key
    (type, year_bce from date_json, primary_place_id). Creates a new Event if no
    match found. Merges scalar fields with conflict-emission semantics.
    Returns the number of candidates processed.

    Requires load_candidate_places to have already run so that the FK
    `events.primary_place_id REFERENCES places(id)` is satisfiable. The local
    extraction place id (e.g. 'pl1') stored in candidate_events.primary_place_id
    is resolved to the canonical place id (e.g. 'pla:qishan') via the
    candidate_places→places join on name.
    """
    place_id_map = build_place_id_map(conn, pipeline_run_id)

    cands = conn.execute(
        "SELECT id, type, date_json, outcome, summary, primary_place_id, "
        "confidence, chunk_id "
        "FROM candidate_events WHERE pipeline_run_id = ?;",
        (pipeline_run_id,),
    ).fetchall()

    n = 0
    for c in cands:
        year_bce = _year_bce_from_date_json(c[_CI_DATE_JSON])
        raw_place_id = c[_CI_PRIMARY_PLACE_ID]
        # Resolve local extraction id (e.g. 'pl1') → canonical id (e.g. 'pla:qishan').
        # Already-canonical values (containing ':') pass through unchanged.
        if raw_place_id is not None and ":" not in raw_place_id:
            resolved_place_id = place_id_map.get(raw_place_id)
            if resolved_place_id is None:
                # Local id not in map — likely a missing candidate_places row or
                # name mismatch. Fall through with None to avoid FK violation.
                resolved_place_id = None
        else:
            resolved_place_id = raw_place_id

        existing_id = _find_existing_event(conn, c[_CI_TYPE], year_bce, resolved_place_id)

        if existing_id is None:
            event_id = _build_event_id(conn, c[_CI_TYPE], year_bce)
            _create_event(conn, event_id, c, pipeline_run_id, resolved_place_id)
        else:
            event_id = existing_id
            _merge_event_fields(conn, event_id, c, pipeline_run_id, resolved_place_id)

        record_citation(conn, "event", event_id, c[_CI_CHUNK_ID])
        n += 1

    conn.commit()
    return n
