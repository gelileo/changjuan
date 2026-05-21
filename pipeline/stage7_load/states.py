"""Stage 7 — load_candidate_states. Mirrors places.py for states.

Scalar merge fields: name, type, ruling_clan, founded_date_json, ended_date_json.
Match key: name.
No variants table — states are matched by name only.
state_capitals (a relation table) is handled separately in Task 19.
"""

from __future__ import annotations

import hashlib
import json as _json
import sqlite3

from pipeline.stage7_load.audit import _audit
from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.helpers import _SIMILAR_CONFIDENCE_DELTA, _slugify

_STATE_SCALAR_FIELDS = ("type", "ruling_clan", "founded_date_json", "ended_date_json")


def _last_field_confidence(
    conn: sqlite3.Connection, entity_kind: str, entity_id: str, field: str
) -> float | None:
    """Return the confidence recorded in the most recent set-event for this field, or None."""
    row = conn.execute(
        "SELECT json_extract(after_json, '$.confidence') AS c "
        "FROM audit_log WHERE entity_kind = ? AND entity_id = ? AND field = ? "
        "ORDER BY at DESC, id DESC LIMIT 1;",
        (entity_kind, entity_id, field),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])


def load_candidate_states(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_states rows tagged with pipeline_run_id into canonical states.

    Matches candidates against existing States by name. Creates a new State if no
    match found. Merges scalar fields with higher-confidence-wins semantics.
    Returns the number of candidates processed.
    """
    cands = conn.execute(
        "SELECT id, name, type, ruling_clan, founded_date_json, ended_date_json, "
        "chunk_id, confidence "
        "FROM candidate_states WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ).fetchall()

    n = 0
    for cand in cands:
        (
            cand_id,
            name,
            stype,
            ruling_clan,
            founded_date_json,
            ended_date_json,
            chunk_id,
            confidence,
        ) = cand

        existing = conn.execute("SELECT id FROM states WHERE name = ?", (name,)).fetchone()

        if existing is None:
            # Build slug-based id; guard against slug collisions.
            state_id = f"sta:{_slugify(name)}"
            if (
                conn.execute("SELECT 1 FROM states WHERE id = ?", (state_id,)).fetchone()
                is not None
            ):
                h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
                state_id = f"{state_id}-{h}"

            conn.execute(
                "INSERT INTO states "
                "(id, name, type, ruling_clan, founded_date_json, ended_date_json, "
                "provenance, confidence, pipeline_run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, ?)",
                (
                    state_id,
                    name,
                    stype,
                    ruling_clan,
                    founded_date_json,
                    ended_date_json,
                    confidence,
                    pipeline_run_id,
                ),
            )
            _audit(
                conn,
                "state",
                state_id,
                "create",
                after_json=_json.dumps(
                    {"value": name, "confidence": confidence}, ensure_ascii=False
                ),
                actor="load@v1",
                pipeline_run_id=pipeline_run_id,
            )
            record_citation(conn, "state", state_id, chunk_id)
        else:
            state_id = existing[0]
            current = conn.execute(
                "SELECT type, ruling_clan, founded_date_json, ended_date_json, confidence "
                "FROM states WHERE id = ?",
                (state_id,),
            ).fetchone()
            cur_conf = float(current[4] or 0.0)
            cand_values = (stype, ruling_clan, founded_date_json, ended_date_json)

            for idx, field in enumerate(_STATE_SCALAR_FIELDS):
                cand_val = cand_values[idx]
                if cand_val is None:
                    continue
                cur_val = current[idx]
                if cand_val == cur_val:
                    continue
                if cur_val is None:
                    conn.execute(
                        f"UPDATE states SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
                        (cand_val, state_id),
                    )
                    _audit(
                        conn,
                        "state",
                        state_id,
                        "set",
                        after_json=_json.dumps(
                            {"value": cand_val, "confidence": confidence},
                            ensure_ascii=False,
                        ),
                        actor="load@v1",
                        pipeline_run_id=pipeline_run_id,
                        field=field,
                    )
                    continue
                # Both non-null: use per-field confidence from audit_log, fall back to row-level.
                prior_conf = _last_field_confidence(conn, "state", state_id, field) or cur_conf
                if confidence > prior_conf + _SIMILAR_CONFIDENCE_DELTA:
                    conn.execute(
                        f"UPDATE states SET {field} = ?, confidence = ?, "
                        "updated_at = datetime('now') WHERE id = ?",
                        (cand_val, confidence, state_id),
                    )
                    _audit(
                        conn,
                        "state",
                        state_id,
                        "set",
                        after_json=_json.dumps(
                            {"value": cand_val, "confidence": confidence},
                            ensure_ascii=False,
                        ),
                        before_json=_json.dumps(
                            {"value": cur_val, "confidence": prior_conf},
                            ensure_ascii=False,
                        ),
                        actor="load@v1",
                        pipeline_run_id=pipeline_run_id,
                        field=field,
                    )
            record_citation(conn, "state", state_id, chunk_id)
        n += 1
    conn.commit()
    return n
