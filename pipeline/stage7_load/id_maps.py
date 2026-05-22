"""Local extraction id → canonical id maps for FK resolution in stage 7 loaders.

candidate_persons.id format: cand:per:{run_id}:{local_id}
candidate_events.id format:  cand:evt:{run_id}:{local_id}
candidate_places.id format:  cand:pla:{run_id}:{local_id}
candidate_states.id format:  cand:sta:{run_id}:{local_id}

These maps are used by relation loaders to resolve the local extraction ids
stored in candidate_* FK columns (e.g. 'p1', 'e1', 'pl1', 's1') to the
canonical ids in the corresponding canonical tables (e.g. 'per:zhou-xuan-wang',
'evt:崩-783bce', 'pla:qishan', 'sta:zhou').

All build_* functions require the corresponding canonical table to have already
been populated for the run (i.e. load_candidate_{entities} must have run first).
"""

from __future__ import annotations

import json
import sqlite3


def _extract_local(cand_id: str, prefix: str) -> str | None:
    """Extract the local_id suffix from a candidate id, or None if prefix doesn't match."""
    return cand_id[len(prefix) :] if cand_id.startswith(prefix) else None


def build_person_id_map(conn: sqlite3.Connection, run_id: str) -> dict[str, str]:
    """Return {local_id → canonical_person_id} for all candidate_persons in this run.

    Joins candidate_persons against persons on canonical_name.
    """
    prefix = f"cand:per:{run_id}:"
    rows = conn.execute(
        "SELECT cp.id, p.id FROM candidate_persons cp "
        "JOIN persons p ON p.canonical_name = cp.canonical_name "
        "WHERE cp.pipeline_run_id = ?",
        (run_id,),
    ).fetchall()
    result: dict[str, str] = {}
    for cand_id, canonical_id in rows:
        local = _extract_local(cand_id, prefix)
        if local:
            result[local] = canonical_id
    return result


def build_state_id_map(conn: sqlite3.Connection, run_id: str) -> dict[str, str]:
    """Return {local_id → canonical_state_id} for all candidate_states in this run.

    Joins candidate_states against states on name.
    """
    prefix = f"cand:sta:{run_id}:"
    rows = conn.execute(
        "SELECT cs.id, s.id FROM candidate_states cs "
        "JOIN states s ON s.name = cs.name "
        "WHERE cs.pipeline_run_id = ?",
        (run_id,),
    ).fetchall()
    result: dict[str, str] = {}
    for cand_id, canonical_id in rows:
        local = _extract_local(cand_id, prefix)
        if local:
            result[local] = canonical_id
    return result


def build_place_id_map(conn: sqlite3.Connection, run_id: str) -> dict[str, str]:
    """Return {local_id → canonical_place_id} for all candidate_places in this run.

    Joins candidate_places against places on name.
    """
    prefix = f"cand:pla:{run_id}:"
    rows = conn.execute(
        "SELECT cp.id, p.id FROM candidate_places cp "
        "JOIN places p ON p.name = cp.name "
        "WHERE cp.pipeline_run_id = ?",
        (run_id,),
    ).fetchall()
    result: dict[str, str] = {}
    for cand_id, canonical_id in rows:
        local = _extract_local(cand_id, prefix)
        if local:
            result[local] = canonical_id
    return result


def build_event_id_map(conn: sqlite3.Connection, run_id: str) -> dict[str, str]:
    """Return {local_id → canonical_event_id} for all candidate_events in this run.

    Events lack a single name column, so we match via the composite key
    (type, year_bce from date_json, pipeline_run_id). This relies on
    load_candidate_events having already promoted the candidates for this run.
    """
    prefix = f"cand:evt:{run_id}:"
    cand_rows = conn.execute(
        "SELECT id, type, date_json FROM candidate_events " "WHERE pipeline_run_id = ?",
        (run_id,),
    ).fetchall()
    result: dict[str, str] = {}
    for cand_id, ev_type, date_json in cand_rows:
        local = _extract_local(cand_id, prefix)
        if not local:
            continue
        # Extract year_bce from date_json.
        year_bce = None
        if date_json:
            try:
                d = json.loads(date_json)
                year_bce = d.get("year_bce")
            except (json.JSONDecodeError, TypeError):
                pass
        # Find the canonical event by (type, year_bce, pipeline_run_id).
        # Using pipeline_run_id as an additional discriminator makes the lookup
        # specific to events promoted from this run, avoiding cross-run collisions
        # when multiple runs extracted the same event type in the same year.
        if year_bce is not None:
            row = conn.execute(
                "SELECT id FROM events "
                "WHERE type = ? "
                "AND CAST(json_extract(date_json, '$.year_bce') AS INTEGER) = ? "
                "AND pipeline_run_id = ? "
                "LIMIT 1",
                (ev_type, int(year_bce), run_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM events "
                "WHERE type = ? "
                "AND json_extract(date_json, '$.year_bce') IS NULL "
                "AND pipeline_run_id = ? "
                "LIMIT 1",
                (ev_type, run_id),
            ).fetchone()
        if row is not None:
            result[local] = row[0]
    return result
