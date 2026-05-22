"""Relevance pre-filter for the Stage 5 linker.

Avoids O(N²) by filtering plausible match targets via SQL name-overlap queries
before any scoring happens. Names that share no characters won't appear; the
scorer never sees them.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _load_candidate(conn: sqlite3.Connection, candidate_id: str) -> dict[str, Any] | None:
    """Load the candidate Person + its variants."""
    row = conn.execute(
        "SELECT id, canonical_name, state_id, social_category, clan_name, "
        "       birth_date_json, death_date_json "
        "FROM candidate_persons WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    variants = [
        {"variant": vr[0], "kind": vr[1]}
        for vr in conn.execute(
            "SELECT variant, kind FROM candidate_person_variants WHERE candidate_person_id = ?",
            (candidate_id,),
        )
    ]
    return _row_to_dict(row, variants, target_kind="self")


def _safe_json_load(raw: str | None) -> dict[str, Any] | None:
    """Parse a JSON-encoded date dict, returning None on missing or malformed input.

    LLM-driven extraction occasionally writes malformed JSON; rather than crashing the
    entire link pass, drop the date and let the scorer treat it as 'unknown'.
    """
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _row_to_dict(row: Any, variants: list[dict[str, Any]], target_kind: str) -> dict[str, Any]:
    return {
        "target_id": row[0],
        "target_kind": target_kind,
        "canonical_name": row[1],
        "state_id": row[2],
        "social_category": row[3],
        "clan_name": row[4],
        "birth_date": _safe_json_load(row[5]),
        "death_date": _safe_json_load(row[6]),
        "variants": variants,
    }


def candidate_pool(
    conn: sqlite3.Connection,
    candidate_id: str,
    pipeline_run_id: str,
) -> list[dict[str, Any]]:
    """Return plausible match targets for the given candidate id.

    Filters: name-overlap on canonical_name or any variant. Excludes self,
    excludes candidates from other pipeline_run_ids.
    """
    me = _load_candidate(conn, candidate_id)
    if me is None:
        return []

    my_names: set[str] = set()
    if me.get("canonical_name"):
        my_names.add(me["canonical_name"])
    for v in me.get("variants", []):
        if v.get("variant"):
            my_names.add(v["variant"])

    if not my_names:
        return []

    placeholders = ",".join("?" * len(my_names))
    names_tuple = tuple(my_names)
    pool: list[dict[str, Any]] = []

    # Canonical persons sharing a name string with the candidate
    canonical_rows = conn.execute(
        f"""
        SELECT DISTINCT p.id, p.canonical_name, p.state_id, p.social_category, p.clan_name,
                        p.birth_date_json, p.death_date_json
        FROM persons p
        LEFT JOIN person_variants pv ON pv.person_id = p.id
        WHERE p.canonical_name IN ({placeholders})
           OR pv.variant IN ({placeholders})
        """,
        names_tuple + names_tuple,
    ).fetchall()
    for row in canonical_rows:
        variants = [
            {"variant": vr[0], "kind": vr[1]}
            for vr in conn.execute(
                "SELECT variant, kind FROM person_variants WHERE person_id = ?",
                (row[0],),
            )
        ]
        pool.append(_row_to_dict(row, variants, target_kind="canonical"))

    # Same-run candidates sharing a name string
    candidate_rows = conn.execute(
        f"""
        SELECT DISTINCT c.id, c.canonical_name, c.state_id, c.social_category, c.clan_name,
                        c.birth_date_json, c.death_date_json
        FROM candidate_persons c
        LEFT JOIN candidate_person_variants cv ON cv.candidate_person_id = c.id
        WHERE c.pipeline_run_id = ?
          AND c.id != ?
          AND (c.canonical_name IN ({placeholders}) OR cv.variant IN ({placeholders}))
        """,
        (pipeline_run_id, candidate_id, *names_tuple, *names_tuple),
    ).fetchall()
    for row in candidate_rows:
        variants = [
            {"variant": vr[0], "kind": vr[1]}
            for vr in conn.execute(
                "SELECT variant, kind FROM candidate_person_variants "
                "WHERE candidate_person_id = ?",
                (row[0],),
            )
        ]
        pool.append(_row_to_dict(row, variants, target_kind="candidate"))

    return pool
