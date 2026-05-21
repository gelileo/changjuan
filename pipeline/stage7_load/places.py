"""Stage 7 — load_candidate_places. Mirrors persons.py for places.

Scalar merge fields: name, type, lat, lon, coord_confidence, modern_equiv.
Match key: name.
No variants table — places are matched by name only.
"""

from __future__ import annotations

import hashlib
import json as _json
import sqlite3

from pipeline.stage7_load.audit import _audit
from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.helpers import _SIMILAR_CONFIDENCE_DELTA, _slugify

_PLACE_SCALAR_FIELDS = ("type", "lat", "lon", "coord_confidence", "modern_equiv")


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


def load_candidate_places(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_places rows tagged with pipeline_run_id into canonical places.

    Matches candidates against existing Places by name. Creates a new Place if no
    match found. Merges scalar fields with higher-confidence-wins semantics.
    Returns the number of candidates processed.
    """
    cands = conn.execute(
        "SELECT id, name, type, lat, lon, coord_confidence, modern_equiv, "
        "chunk_id, confidence "
        "FROM candidate_places WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ).fetchall()

    n = 0
    for cand in cands:
        (
            cand_id,
            name,
            ptype,
            lat,
            lon,
            coord_conf,
            modern_equiv,
            chunk_id,
            confidence,
        ) = cand

        existing = conn.execute("SELECT id FROM places WHERE name = ?", (name,)).fetchone()

        if existing is None:
            # Build slug-based id; guard against slug collisions.
            place_id = f"pla:{_slugify(name)}"
            if (
                conn.execute("SELECT 1 FROM places WHERE id = ?", (place_id,)).fetchone()
                is not None
            ):
                h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
                place_id = f"{place_id}-{h}"

            conn.execute(
                "INSERT INTO places "
                "(id, name, type, lat, lon, coord_confidence, modern_equiv, "
                "provenance, confidence, pipeline_run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'auto', ?, ?)",
                (
                    place_id,
                    name,
                    ptype,
                    lat,
                    lon,
                    coord_conf,
                    modern_equiv,
                    confidence,
                    pipeline_run_id,
                ),
            )
            _audit(
                conn,
                "place",
                place_id,
                "create",
                after_json=_json.dumps(
                    {"value": name, "confidence": confidence}, ensure_ascii=False
                ),
                actor="load@v1",
                pipeline_run_id=pipeline_run_id,
            )
            record_citation(conn, "place", place_id, chunk_id)
        else:
            place_id = existing[0]
            current = conn.execute(
                "SELECT type, lat, lon, coord_confidence, modern_equiv, confidence "
                "FROM places WHERE id = ?",
                (place_id,),
            ).fetchone()
            cur_conf = float(current[5] or 0.0)
            cand_values = (ptype, lat, lon, coord_conf, modern_equiv)

            for idx, field in enumerate(_PLACE_SCALAR_FIELDS):
                cand_val = cand_values[idx]
                if cand_val is None:
                    continue
                cur_val = current[idx]
                if cand_val == cur_val:
                    continue
                if cur_val is None:
                    conn.execute(
                        f"UPDATE places SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
                        (cand_val, place_id),
                    )
                    _audit(
                        conn,
                        "place",
                        place_id,
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
                prior_conf = _last_field_confidence(conn, "place", place_id, field) or cur_conf
                if confidence > prior_conf + _SIMILAR_CONFIDENCE_DELTA:
                    conn.execute(
                        f"UPDATE places SET {field} = ?, confidence = ?, "
                        "updated_at = datetime('now') WHERE id = ?",
                        (cand_val, confidence, place_id),
                    )
                    _audit(
                        conn,
                        "place",
                        place_id,
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
            record_citation(conn, "place", place_id, chunk_id)
        n += 1
    conn.commit()
    return n
