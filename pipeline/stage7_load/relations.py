"""Stage 7 — load_candidate_relations. Six relation kinds, tuple-key dedup,
citation accumulation, person_relation contradiction → Conflict emission.

All six canonical relation tables use composite PKs (no surrogate id column).
The entity_citations.entity_id for relation rows is a synthetic key composed from
the unique-tuple elements joined by ':' — e.g. 'evt:1:per:a:主将' for an
event_participant row. This key is used only for citation tracking and audit; it
is never stored in the relation table itself.

Relation tables do not have a provenance column in candidate_* tables; all
promoted rows receive provenance='auto'. Confidence and pipeline_run_id are
propagated from the candidate row where present; otherwise reasonable defaults
are used (confidence=0.9 for event/person/state relations that lack a separate
confidence column in the candidate table).

Note: candidate_state_capitals does not exist in the current schema — state
capitals are expressed via the canonical state_capitals table and seeded only
by load_candidate_states or by curator override. load_candidate_state_capitals
is therefore a no-op stub that returns 0.
"""

from __future__ import annotations

import json as _json
import sqlite3
import uuid

from pipeline.stage7_load.audit import _audit
from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.id_maps import (
    build_event_id_map,
    build_person_id_map,
    build_place_id_map,
    build_state_id_map,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_EVENT_RELATION_KINDS = frozenset({"causes", "precedes", "related"})
_VALID_PERSON_RELATION_KINDS = frozenset(
    {
        "parent",
        "child",
        "spouse",
        "sibling",
        "mentor",
        "ruler",
        "minister",
        "ally",
        "rival",
        "killed_by",
        "clan_member",
    }
)
_VALID_PERSON_STATE_ROLES = frozenset(
    {"ruler", "minister", "exile", "defector", "citizen", "other"}
)


def _resolve_fk(raw_id: str | None, id_map: dict[str, str]) -> str | None:
    """Resolve a raw FK value to a canonical id via id_map.

    Four cases:
    1. None → returns None.
    2. Full candidate id like 'cand:per:run:...:p1' → extract the local suffix
       (the last ':'-delimited segment) and look up in id_map.
    3. Short local id like 'p1' (no ':') → look up in id_map directly.
    4. Already-canonical id like 'per:zhou-xuan-wang' (contains ':' but not
       starting with 'cand:') → pass through unchanged.

    Returns None if resolution fails; callers should skip such rows.
    """
    if raw_id is None:
        return None
    if raw_id.startswith("cand:"):
        # Full candidate id: 'cand:{kind}:{run_id}:{local_id}'.
        # The local_id is always the last ':'-delimited segment.
        local = raw_id.rsplit(":", 1)[-1]
        return id_map.get(local)
    if ":" in raw_id:
        # Already canonical (e.g. 'per:zhou-xuan-wang', 'evt:崩-783bce').
        return raw_id
    # Short local id (e.g. 'p1', 'e1', 'pl1', 's1').
    return id_map.get(raw_id)


# Directional person_relation kinds: a conflict is raised when the inverse
# (B, A, same kind) already exists in the canonical table.
_DIRECTIONAL_PERSON_RELATION_KINDS = frozenset(
    {"parent", "child", "killed_by", "ruler", "minister", "mentor"}
)


def _emit_conflict(
    conn: sqlite3.Connection,
    subject_kind: str,
    subject_id: str,
    field: str,
    old_val: object,
    new_val: object,
    pipeline_run_id: str,
) -> None:
    variants = [
        {"value": old_val, "source": "existing"},
        {"value": new_val, "source": f"run:{pipeline_run_id}"},
    ]
    conn.execute(
        "INSERT INTO conflicts"
        " (id, subject_kind, subject_id, field, variants_json,"
        " current_best_variant_idx, resolution_rule, status)"
        " VALUES (?, ?, ?, ?, ?, ?, 'manual_review', 'open');",
        (
            f"cfl:{uuid.uuid4().hex[:12]}",
            subject_kind,
            subject_id,
            field,
            _json.dumps(variants, ensure_ascii=False),
            0,  # keep existing as best guess; human must resolve
        ),
    )


# ---------------------------------------------------------------------------
# event_participants
# ---------------------------------------------------------------------------


def load_candidate_event_participants(conn: sqlite3.Connection, run_id: str) -> int:
    """Promote candidate_event_participants rows for run_id.

    Unique key: (event_id, person_id, role).
    Resolves candidate_event_id / candidate_person_id local extraction ids
    (e.g. 'e1', 'p1') to canonical ids via build_event_id_map / build_person_id_map.
    Rows whose event_id or person_id cannot be resolved are skipped to avoid FK
    constraint violations.
    """
    event_map = build_event_id_map(conn, run_id)
    person_map = build_person_id_map(conn, run_id)

    rows = conn.execute(
        "SELECT candidate_event_id, candidate_person_id, role, role_detail, pipeline_run_id "
        "FROM candidate_event_participants WHERE pipeline_run_id = ?;",
        (run_id,),
    ).fetchall()
    n = 0
    for row in rows:
        raw_event_id: str = row[0]
        raw_person_id: str = row[1]
        role: str = row[2]
        role_detail: str | None = row[3]

        event_id = _resolve_fk(raw_event_id, event_map)
        person_id = _resolve_fk(raw_person_id, person_map)

        # Both FKs are NOT NULL in the canonical schema; skip if either unresolved.
        if event_id is None or person_id is None:
            continue

        existing = conn.execute(
            "SELECT 1 FROM event_participants WHERE event_id = ? AND person_id = ? AND role = ?;",
            (event_id, person_id, role),
        ).fetchone()

        relation_id = f"{event_id}:{person_id}:{role}"

        if existing is None:
            conn.execute(
                "INSERT INTO event_participants"
                " (event_id, person_id, role, role_detail, confidence, provenance)"
                " VALUES (?, ?, ?, ?, 0.9, 'auto');",
                (event_id, person_id, role, role_detail),
            )
            _audit(
                conn,
                "event_participant",
                relation_id,
                "create",
                after_json=_json.dumps(
                    {"event_id": event_id, "person_id": person_id, "role": role},
                    ensure_ascii=False,
                ),
                actor="load@v1",
                pipeline_run_id=run_id,
            )

        record_citation(conn, "event_participant", relation_id, run_id)
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# event_places
# ---------------------------------------------------------------------------


def load_candidate_event_places(conn: sqlite3.Connection, run_id: str) -> int:
    """Promote candidate_event_places rows for run_id.

    Unique key: (event_id, place_id, role).
    Resolves candidate_event_id / candidate_place_id local extraction ids
    (e.g. 'e1', 'pl1') to canonical ids. Rows that cannot be resolved are skipped.
    """
    event_map = build_event_id_map(conn, run_id)
    place_map = build_place_id_map(conn, run_id)

    rows = conn.execute(
        "SELECT candidate_event_id, candidate_place_id, role, pipeline_run_id "
        "FROM candidate_event_places WHERE pipeline_run_id = ?;",
        (run_id,),
    ).fetchall()
    n = 0
    for row in rows:
        raw_event_id: str = row[0]
        raw_place_id: str = row[1]
        role: str = row[2]

        event_id = _resolve_fk(raw_event_id, event_map)
        place_id = _resolve_fk(raw_place_id, place_map)

        # Both FKs are NOT NULL in the canonical schema; skip if either unresolved.
        if event_id is None or place_id is None:
            continue

        existing = conn.execute(
            "SELECT 1 FROM event_places WHERE event_id = ? AND place_id = ? AND role = ?;",
            (event_id, place_id, role),
        ).fetchone()

        relation_id = f"{event_id}:{place_id}:{role}"

        if existing is None:
            conn.execute(
                "INSERT INTO event_places"
                " (event_id, place_id, role, confidence, provenance)"
                " VALUES (?, ?, ?, 0.9, 'auto');",
                (event_id, place_id, role),
            )
            _audit(
                conn,
                "event_place",
                relation_id,
                "create",
                after_json=_json.dumps(
                    {"event_id": event_id, "place_id": place_id, "role": role},
                    ensure_ascii=False,
                ),
                actor="load@v1",
                pipeline_run_id=run_id,
            )

        record_citation(conn, "event_place", relation_id, run_id)
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# event_relations
# ---------------------------------------------------------------------------


def load_candidate_event_relations(conn: sqlite3.Connection, run_id: str) -> int:
    """Promote candidate_event_relations rows for run_id.

    Unique key: (from_event_id, to_event_id, kind).
    kind must be one of 'causes','precedes','related' per canonical schema CHECK.
    Resolves from_candidate_event_id / to_candidate_event_id local extraction ids
    (e.g. 'e1', 'e2') to canonical ids. Rows that cannot be resolved are skipped.
    """
    event_map = build_event_id_map(conn, run_id)

    rows = conn.execute(
        "SELECT from_candidate_event_id, to_candidate_event_id, kind, pipeline_run_id "
        "FROM candidate_event_relations WHERE pipeline_run_id = ?;",
        (run_id,),
    ).fetchall()
    n = 0
    for row in rows:
        raw_from_id: str = row[0]
        raw_to_id: str = row[1]
        kind: str = row[2]

        from_id = _resolve_fk(raw_from_id, event_map)
        to_id = _resolve_fk(raw_to_id, event_map)

        # Both FKs are NOT NULL and kind must satisfy the CHECK constraint; skip if invalid.
        if from_id is None or to_id is None or kind not in _VALID_EVENT_RELATION_KINDS:
            continue

        existing = conn.execute(
            "SELECT 1 FROM event_relations"
            " WHERE from_event_id = ? AND to_event_id = ? AND kind = ?;",
            (from_id, to_id, kind),
        ).fetchone()

        relation_id = f"{from_id}:{to_id}:{kind}"

        if existing is None:
            conn.execute(
                "INSERT INTO event_relations"
                " (from_event_id, to_event_id, kind, confidence, provenance)"
                " VALUES (?, ?, ?, 0.9, 'auto');",
                (from_id, to_id, kind),
            )
            _audit(
                conn,
                "event_relation",
                relation_id,
                "create",
                after_json=_json.dumps(
                    {"from_event_id": from_id, "to_event_id": to_id, "kind": kind},
                    ensure_ascii=False,
                ),
                actor="load@v1",
                pipeline_run_id=run_id,
            )

        record_citation(conn, "event_relation", relation_id, run_id)
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# person_relations
# ---------------------------------------------------------------------------


def load_candidate_person_relations(conn: sqlite3.Connection, run_id: str) -> int:
    """Promote candidate_person_relations rows for run_id.

    Unique key: (from_person_id, to_person_id, kind).
    Contradiction detection: for directional kinds (parent, child, killed_by,
    ruler, minister, mentor), if the inverse (to_person_id, from_person_id, kind)
    already exists in the canonical table, emit a Conflict row.
    Resolves from_candidate_person_id / to_candidate_person_id local extraction ids
    (e.g. 'p1', 'p2') to canonical ids. Rows that cannot be resolved are skipped.
    """
    person_map = build_person_id_map(conn, run_id)

    rows = conn.execute(
        "SELECT from_candidate_person_id, to_candidate_person_id, kind, date_json,"
        " pipeline_run_id "
        "FROM candidate_person_relations WHERE pipeline_run_id = ?;",
        (run_id,),
    ).fetchall()
    n = 0
    for row in rows:
        raw_from_id: str = row[0]
        raw_to_id: str = row[1]
        kind: str = row[2]
        date_json: str | None = row[3]

        from_id = _resolve_fk(raw_from_id, person_map)
        to_id = _resolve_fk(raw_to_id, person_map)

        # Both FKs are NOT NULL and kind must satisfy the CHECK constraint; skip if invalid.
        if from_id is None or to_id is None or kind not in _VALID_PERSON_RELATION_KINDS:
            continue

        existing = conn.execute(
            "SELECT 1 FROM person_relations"
            " WHERE from_person_id = ? AND to_person_id = ? AND kind = ?;",
            (from_id, to_id, kind),
        ).fetchone()

        relation_id = f"{from_id}:{to_id}:{kind}"

        if existing is None:
            # Contradiction check: directional inverse already present?
            if kind in _DIRECTIONAL_PERSON_RELATION_KINDS:
                inverse = conn.execute(
                    "SELECT 1 FROM person_relations"
                    " WHERE from_person_id = ? AND to_person_id = ? AND kind = ?;",
                    (to_id, from_id, kind),
                ).fetchone()
                if inverse is not None:
                    inverse_id = f"{to_id}:{from_id}:{kind}"
                    _emit_conflict(
                        conn,
                        "person_relation",
                        inverse_id,
                        "directionality",
                        f"{to_id}→{from_id}",
                        f"{from_id}→{to_id}",
                        run_id,
                    )

            conn.execute(
                "INSERT INTO person_relations"
                " (from_person_id, to_person_id, kind, date_json, confidence, provenance)"
                " VALUES (?, ?, ?, ?, 0.9, 'auto');",
                (from_id, to_id, kind, date_json),
            )
            _audit(
                conn,
                "person_relation",
                relation_id,
                "create",
                after_json=_json.dumps(
                    {"from_person_id": from_id, "to_person_id": to_id, "kind": kind},
                    ensure_ascii=False,
                ),
                actor="load@v1",
                pipeline_run_id=run_id,
            )

        record_citation(conn, "person_relation", relation_id, run_id)
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# person_states
# ---------------------------------------------------------------------------


def load_candidate_person_states(conn: sqlite3.Connection, run_id: str) -> int:
    """Promote candidate_person_states rows for run_id.

    Unique key: (person_id, state_id, role, from_date_json) — matching the
    canonical person_states PRIMARY KEY. The candidate table omits from_date_json
    from its PK, so when from_date_json is None in the candidate row the canonical
    key is (person_id, state_id, role, NULL).
    Resolves candidate_person_id / candidate_state_id local extraction ids
    (e.g. 'p1', 's1') to canonical ids. Rows that cannot be resolved are skipped.
    """
    person_map = build_person_id_map(conn, run_id)
    state_map = build_state_id_map(conn, run_id)

    rows = conn.execute(
        "SELECT candidate_person_id, candidate_state_id, role, from_date_json,"
        " to_date_json, pipeline_run_id "
        "FROM candidate_person_states WHERE pipeline_run_id = ?;",
        (run_id,),
    ).fetchall()
    n = 0
    for row in rows:
        raw_person_id: str = row[0]
        raw_state_id: str = row[1]
        role: str = row[2]
        from_date_json: str | None = row[3]
        to_date_json: str | None = row[4]

        person_id = _resolve_fk(raw_person_id, person_map)
        state_id = _resolve_fk(raw_state_id, state_map)

        # Both FKs are NOT NULL and role must satisfy the CHECK constraint; skip if invalid.
        if person_id is None or state_id is None or role not in _VALID_PERSON_STATE_ROLES:
            continue

        if from_date_json is None:
            existing = conn.execute(
                "SELECT 1 FROM person_states"
                " WHERE person_id = ? AND state_id = ? AND role = ? AND from_date_json IS NULL;",
                (person_id, state_id, role),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT 1 FROM person_states"
                " WHERE person_id = ? AND state_id = ? AND role = ? AND from_date_json = ?;",
                (person_id, state_id, role, from_date_json),
            ).fetchone()

        # Synthetic relation_id for citation tracking
        date_part = from_date_json or "null"
        relation_id = f"{person_id}:{state_id}:{role}:{date_part}"

        if existing is None:
            conn.execute(
                "INSERT INTO person_states"
                " (person_id, state_id, role, from_date_json, to_date_json, confidence, provenance)"
                " VALUES (?, ?, ?, ?, ?, 0.9, 'auto');",
                (person_id, state_id, role, from_date_json, to_date_json),
            )
            _audit(
                conn,
                "person_state",
                relation_id,
                "create",
                after_json=_json.dumps(
                    {"person_id": person_id, "state_id": state_id, "role": role},
                    ensure_ascii=False,
                ),
                actor="load@v1",
                pipeline_run_id=run_id,
            )

        record_citation(conn, "person_state", relation_id, run_id)
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# state_capitals  (stub — no candidate_state_capitals staging table)
# ---------------------------------------------------------------------------


def load_candidate_state_capitals(conn: sqlite3.Connection, run_id: str) -> int:
    """No-op stub: candidate_state_capitals does not exist in the current schema.

    State capital relations are seeded by load_candidate_states or by curator
    override directly into the canonical state_capitals table. Returns 0.
    """
    return 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_candidate_relations(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Call all six relation loaders in order.

    Returns total count of candidate relation rows processed across all six kinds.
    """
    total = 0
    total += load_candidate_event_participants(conn, pipeline_run_id)
    total += load_candidate_event_places(conn, pipeline_run_id)
    total += load_candidate_event_relations(conn, pipeline_run_id)
    total += load_candidate_person_relations(conn, pipeline_run_id)
    total += load_candidate_person_states(conn, pipeline_run_id)
    total += load_candidate_state_capitals(conn, pipeline_run_id)
    return total
