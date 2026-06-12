"""Stage 7 — load_candidate_themes. Promotes candidate_themes → canonical themes +
theme_occurrences. Themes match by name; occurrences resolve a local extraction
entity id (e.g. 'p1','e1') to canonical via the build_*_id_map helpers, except
'chapter' ids which pass through (they are already document ids like 'hlm:1')."""

from __future__ import annotations

import json as _json
import sqlite3

from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.helpers import _slugify
from pipeline.stage7_load.id_maps import (
    build_event_id_map,
    build_group_id_map,
    build_person_id_map,
    build_place_id_map,
)


def load_candidate_themes(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_themes for this run into canonical themes + theme_occurrences.

    Returns the number of candidate themes processed. Idempotent on theme name and on
    (theme_id, entity_kind, entity_id) occurrence keys.
    """
    maps = {
        "person": build_person_id_map(conn, pipeline_run_id),
        "event": build_event_id_map(conn, pipeline_run_id),
        "group": build_group_id_map(conn, pipeline_run_id),
        "place": build_place_id_map(conn, pipeline_run_id),
    }
    cands = conn.execute(
        "SELECT id, name, description, occurrences_json, chunk_id, confidence "
        "FROM candidate_themes WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ).fetchall()

    n = 0
    for _cand_id, name, description, occurrences_json, chunk_id, confidence in cands:
        existing = conn.execute("SELECT id FROM themes WHERE name = ?", (name,)).fetchone()
        if existing is None:
            theme_id = f"thm:{_slugify(name)}"
            conn.execute(
                "INSERT INTO themes "
                "(id, name, description, provenance, confidence, pipeline_run_id) "
                "VALUES (?, ?, ?, 'auto', ?, ?)",
                (theme_id, name, description, confidence, pipeline_run_id),
            )
        else:
            theme_id = existing[0]
            if description:
                conn.execute(
                    "UPDATE themes SET description = COALESCE(description, ?), "
                    "updated_at = datetime('now') WHERE id = ?",
                    (description, theme_id),
                )
        record_citation(conn, "theme", theme_id, chunk_id)

        for occ in _json.loads(occurrences_json or "[]"):
            kind = occ.get("entity_kind")
            local = occ.get("entity_id")
            if not kind or not local:
                continue
            entity_id = local if kind == "chapter" else maps.get(kind, {}).get(local)
            if entity_id is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO theme_occurrences "
                "(theme_id, entity_kind, entity_id, provenance, confidence) "
                "VALUES (?, ?, ?, 'auto', ?)",
                (theme_id, kind, entity_id, confidence),
            )
        n += 1
    conn.commit()
    return n
