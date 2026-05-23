"""Stage 5 merge actions — the load-bearing module behind the curator UI.

Each public function takes a sqlite Connection and performs its DB writes
in a single BEGIN ... COMMIT transaction. On any error the transaction
is rolled back; in particular, the audit_log row is atomic with the data
change. This atomicity is what makes the field_history view (founding
spec §5) correct.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pipeline.stage5_link.fingerprint import candidate_fingerprint

# Tables that _row_snapshot is permitted to read.
_SNAPSHOTTABLE_TABLES: frozenset[str] = frozenset({"persons", "events", "places", "states"})

# Fields that curator is permitted to edit via accept_merge edits=.
_ALLOWED_EDIT_FIELDS: frozenset[str] = frozenset(
    {
        "gender",
        "birth_date_json",
        "death_date_json",
        "notes",
        "state_id",
        "clan_name",
        "canonical_name",
    }
)

# Local-extraction state_id pattern: 's' followed by one or more digits.
# IDs in this format (e.g. 's1', 's12') reference per-chunk extraction slots,
# not canonical states rows. They must not be folded into canonical persons.
_LOCAL_STATE_ID_RE: re.Pattern[str] = re.compile(r"^s\d+$")


class MergeError(Exception):
    """Base class for merge-action errors."""


class StaleMergeCandidateError(MergeError):
    """The merge_candidates row is no longer open (resolved in another tab/session)."""


class MergeConflictError(MergeError):
    """Candidate and canonical have non-NULL disagreement on a field.

    These should be routed to the conflicts queue during linking; raising here
    is defense-in-depth. The caller should surface the field name to the curator
    so they can either Edit & accept or Reject.
    """

    def __init__(self, field_name: str, candidate_value: Any, canonical_value: Any) -> None:
        super().__init__(
            f"field disagreement: {field_name}={candidate_value!r} vs {canonical_value!r}"
        )
        self.field_name = field_name
        self.candidate_value = candidate_value
        self.canonical_value = canonical_value


class SplitValidationError(MergeError):
    """split_person was asked to peel off variants that don't all exist on the source row."""


@dataclass
class MergeResult:
    canonical_id: str
    variants_added: int
    relations_retargeted: int
    fields_edited: int
    collisions_resolved: int = 0


@dataclass
class RejectResult:
    mc_id: str
    note: str | None


@dataclass
class SplitResult:
    source_person_id: str
    new_person_id: str
    variants_moved: list[str] = field(default_factory=list)


def _resolve_collisions_event_participants(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """Detect (event_id, role) PK collisions between candidate's and canonical's rows.

    Keeps the higher-confidence row; deletes the other. Returns the number
    of collisions resolved. Writes audit_log rows for each deletion.
    """
    cur = conn.execute(
        "SELECT cand.event_id, cand.role, cand.confidence AS cand_conf, "
        "       can.confidence AS can_conf "
        "FROM event_participants cand "
        "JOIN event_participants can "
        "  ON cand.event_id = can.event_id AND cand.role = can.role "
        "WHERE cand.person_id = ? AND can.person_id = ?",
        (candidate_id, canonical_id),
    )
    collisions = list(cur)
    for c in collisions:
        loser_person = candidate_id if c["cand_conf"] <= c["can_conf"] else canonical_id
        loser_row = conn.execute(
            "SELECT * FROM event_participants " "WHERE event_id = ? AND person_id = ? AND role = ?",
            (c["event_id"], loser_person, c["role"]),
        ).fetchone()
        conn.execute(
            "DELETE FROM event_participants " "WHERE event_id = ? AND person_id = ? AND role = ?",
            (c["event_id"], loser_person, c["role"]),
        )
        conn.execute(
            "INSERT INTO audit_log "
            "(id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'event_participant', ?, NULL, "
            "'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"{c['event_id']}:{loser_person}:{c['role']}",
                json.dumps(dict(loser_row), ensure_ascii=False),
                _now_iso(),
            ),
        )
    return len(collisions)


def _resolve_self_loops_person_relations(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """A relation FROM candidate TO canonical (or vice versa) becomes a self-loop after merge.

    Delete those outright. Returns the count.
    """
    rows = conn.execute(
        "SELECT * FROM person_relations "
        "WHERE (from_person_id = ? AND to_person_id = ?) "
        "   OR (from_person_id = ? AND to_person_id = ?)",
        (candidate_id, canonical_id, canonical_id, candidate_id),
    ).fetchall()
    for r in rows:
        loser_snapshot = dict(r)
        conn.execute(
            "DELETE FROM person_relations "
            "WHERE from_person_id = ? AND to_person_id = ? AND kind = ?",
            (r["from_person_id"], r["to_person_id"], r["kind"]),
        )
        conn.execute(
            "INSERT INTO audit_log "
            "(id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'person_relation', ?, NULL, "
            "'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"{r['from_person_id']}:{r['to_person_id']}:{r['kind']}",
                json.dumps(loser_snapshot, ensure_ascii=False),
                _now_iso(),
            ),
        )
    return len(rows)


def _resolve_collisions_person_states(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """PK is (person_id, state_id, role, from_date_json). Higher-confidence wins."""
    cur = conn.execute(
        "SELECT cand.state_id, cand.role, cand.from_date_json, "
        "       cand.confidence AS cand_conf, can.confidence AS can_conf "
        "FROM person_states cand "
        "JOIN person_states can "
        "  ON cand.state_id = can.state_id "
        " AND cand.role = can.role "
        " AND COALESCE(cand.from_date_json, '') = COALESCE(can.from_date_json, '') "
        "WHERE cand.person_id = ? AND can.person_id = ?",
        (candidate_id, canonical_id),
    )
    collisions = list(cur)
    for c in collisions:
        loser_person = candidate_id if c["cand_conf"] <= c["can_conf"] else canonical_id
        loser_row = conn.execute(
            "SELECT * FROM person_states "
            "WHERE person_id = ? AND state_id = ? AND role = ? "
            "  AND COALESCE(from_date_json, '') = COALESCE(?, '')",
            (loser_person, c["state_id"], c["role"], c["from_date_json"]),
        ).fetchone()
        conn.execute(
            "DELETE FROM person_states "
            "WHERE person_id = ? AND state_id = ? AND role = ? "
            "  AND COALESCE(from_date_json, '') = COALESCE(?, '')",
            (loser_person, c["state_id"], c["role"], c["from_date_json"]),
        )
        conn.execute(
            "INSERT INTO audit_log "
            "(id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'person_state', ?, NULL, "
            "'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"{loser_person}:{c['state_id']}:{c['role']}",
                json.dumps(dict(loser_row), ensure_ascii=False),
                _now_iso(),
            ),
        )
    return len(collisions)


def _resolve_collisions_entity_citations(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """PK is (entity_kind, entity_id, citation_id). Idempotent — drop candidate's row."""
    cur = conn.execute(
        "SELECT cand.citation_id FROM entity_citations cand "
        "JOIN entity_citations can "
        "  ON cand.entity_kind = can.entity_kind AND cand.citation_id = can.citation_id "
        "WHERE cand.entity_kind = 'person' AND cand.entity_id = ? AND can.entity_id = ?",
        (candidate_id, canonical_id),
    )
    collisions = list(cur)
    for c in collisions:
        conn.execute(
            "DELETE FROM entity_citations "
            "WHERE entity_kind = 'person' AND entity_id = ? AND citation_id = ?",
            (candidate_id, c["citation_id"]),
        )
        conn.execute(
            "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'entity_citation', ?, NULL, "
            "'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"person:{candidate_id}:{c['citation_id']}",
                json.dumps(
                    {"duplicate": True, "entity_id": candidate_id, "citation_id": c["citation_id"]},
                    ensure_ascii=False,
                ),
                _now_iso(),
            ),
        )
    return len(collisions)


def accept_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    edits: dict[str, Any] | None = None,
) -> MergeResult:
    """Fuse candidate (A) into canonical (B). Survivor = canonical.

    See spec §3 for the full algorithm. All work happens in one transaction.

    candidate_a_id may point at either ``persons`` (legacy spec assumption) or
    ``candidate_persons`` (actual live-data layout). Detection is automatic:
    the persons table is checked first; if the row is absent the function falls
    back to candidate_persons.
    """
    cur = conn.execute(
        "SELECT id, candidate_a_id, candidate_b_id, status " "FROM merge_candidates WHERE id = ?",
        (mc_id,),
    )
    mc_row = cur.fetchone()
    if mc_row is None:
        raise MergeError(f"no merge_candidates row with id={mc_id!r}")
    if mc_row["status"] != "open":
        raise StaleMergeCandidateError(f"merge_candidates {mc_id!r} status is {mc_row['status']!r}")

    candidate_id = mc_row["candidate_a_id"]
    canonical_id = mc_row["candidate_b_id"]

    # Detect whether candidate is in persons (legacy spec assumption) or
    # candidate_persons (actual live-data layout).
    candidate_snapshot = _row_snapshot(conn, "persons", candidate_id)
    candidate_from_table = "persons"
    if candidate_snapshot is None:
        candidate_snapshot = _candidate_persons_snapshot(conn, candidate_id)
        if candidate_snapshot is None:
            raise MergeError(
                f"candidate {candidate_id!r} not found in persons or candidate_persons"
            )
        candidate_from_table = "candidate_persons"

    canonical_snapshot_before = _row_snapshot(conn, "persons", canonical_id)
    if canonical_snapshot_before is None:
        raise MergeError(f"canonical person {canonical_id!r} not found")

    # Validate all requested edit fields before any writes (fail-fast).
    if edits:
        for field_name in edits:
            if field_name not in _ALLOWED_EDIT_FIELDS:
                raise MergeError(f"field {field_name!r} not editable via accept_merge")

    # Apply curator edits to canonical FIRST (before NULL-fold) so the field
    # value the fold sees is the edited one. Field-level audit_log rows per §5.
    fields_edited = 0
    if edits:
        for field_name, new_value in edits.items():
            before_value = canonical_snapshot_before.get(field_name)
            conn.execute(
                f"UPDATE persons SET {field_name} = ? WHERE id = ?",
                (new_value, canonical_id),
            )
            conn.execute(
                "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
                "before_json, after_json, actor, at) "
                "VALUES (?, 'person', ?, ?, 'edit', ?, ?, 'curator', ?)",
                (
                    _new_audit_id(),
                    canonical_id,
                    field_name,
                    json.dumps(
                        {"value": before_value, "confidence": 1.0, "source_excerpt": None},
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {"value": new_value, "confidence": 1.0, "source_excerpt": None},
                        ensure_ascii=False,
                    ),
                    _now_iso(),
                ),
            )
            fields_edited += 1
        # Refresh the in-memory snapshot so subsequent fold logic sees edited values.
        canonical_snapshot_before = (
            _row_snapshot(conn, "persons", canonical_id) or canonical_snapshot_before
        )

    # 3. Field-level fold: NULL canonical slots filled from candidate.
    nullable_fields = (
        "gender",
        "birth_date_json",
        "death_date_json",
        "notes",
        "state_id",
        "clan_name",
    )
    field_updates: dict[str, Any] = {}
    for field_name in nullable_fields:
        cand_val = candidate_snapshot.get(field_name)
        can_val = canonical_snapshot_before.get(field_name)
        if cand_val is None or cand_val == can_val:
            continue
        if can_val is None:
            field_updates[field_name] = cand_val
        else:
            raise MergeConflictError(field_name, cand_val, can_val)
    if field_updates:
        set_clause = ", ".join(f"{f} = ?" for f in field_updates)
        conn.execute(
            f"UPDATE persons SET {set_clause} WHERE id = ?",
            (*field_updates.values(), canonical_id),
        )

    # 4. Variant fold — source depends on which table the candidate came from.
    existing = {
        (r["variant"], r["kind"])
        for r in conn.execute(
            "SELECT variant, kind FROM person_variants WHERE person_id = ?", (canonical_id,)
        )
    }
    variants_added = 0

    if candidate_from_table == "persons":
        # Existing path: person_variants rows with person_id=candidate_id.
        candidate_variants = conn.execute(
            "SELECT id, variant, kind FROM person_variants WHERE person_id = ?", (candidate_id,)
        ).fetchall()
        for v in candidate_variants:
            if (v["variant"], v["kind"]) in existing:
                conn.execute("DELETE FROM person_variants WHERE id = ?", (v["id"],))
                continue
            conn.execute(
                "UPDATE person_variants SET person_id = ? WHERE id = ?", (canonical_id, v["id"])
            )
            variants_added += 1
    else:
        # candidate_persons path: variants live in variants_json JSON blob.
        vj_row = conn.execute(
            "SELECT variants_json FROM candidate_persons WHERE id = ?", (candidate_id,)
        ).fetchone()
        if vj_row is not None and vj_row["variants_json"] is not None:
            raw_variants: list[dict[str, str]] = json.loads(vj_row["variants_json"])
            for entry in raw_variants:
                variant = entry.get("variant", "")
                kind = entry.get("kind", "")
                if not variant:
                    continue
                if (variant, kind) in existing:
                    continue
                pv_id = f"pv:{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT OR IGNORE INTO person_variants (id, person_id, variant, kind) "
                    "VALUES (?, ?, ?, ?)",
                    (pv_id, canonical_id, variant, kind),
                )
                existing.add((variant, kind))
                variants_added += 1

    # 5. PK-collision resolution + FK retarget — persons path only.
    #    For candidate_persons path, no persons-FK columns point at a
    #    candidate_persons id, so all collision helpers and retargets are no-ops.
    collisions_resolved = 0
    relations_retargeted = 0

    if candidate_from_table == "persons":
        collisions_resolved += _resolve_collisions_event_participants(
            conn, candidate_id, canonical_id
        )
        collisions_resolved += _resolve_self_loops_person_relations(
            conn, candidate_id, canonical_id
        )
        collisions_resolved += _resolve_collisions_person_states(conn, candidate_id, canonical_id)
        collisions_resolved += _resolve_collisions_entity_citations(
            conn, candidate_id, canonical_id
        )

        relations_retargeted += conn.execute(
            "UPDATE event_participants SET person_id = ? WHERE person_id = ?",
            (canonical_id, candidate_id),
        ).rowcount
        relations_retargeted += conn.execute(
            "UPDATE person_relations SET from_person_id = ? WHERE from_person_id = ?",
            (canonical_id, candidate_id),
        ).rowcount
        relations_retargeted += conn.execute(
            "UPDATE person_relations SET to_person_id = ? WHERE to_person_id = ?",
            (canonical_id, candidate_id),
        ).rowcount
        relations_retargeted += conn.execute(
            "UPDATE person_states SET person_id = ? WHERE person_id = ?",
            (canonical_id, candidate_id),
        ).rowcount
        relations_retargeted += conn.execute(
            "UPDATE entity_citations SET entity_id = ? "
            "WHERE entity_kind = 'person' AND entity_id = ?",
            (canonical_id, candidate_id),
        ).rowcount

        # Delete candidate row. person_variants with person_id=candidate_id are gone
        # (all either moved or deleted in step 4).
        conn.execute("DELETE FROM persons WHERE id = ?", (candidate_id,))
    else:
        # candidate_persons path: mark the historical extraction record as merged.
        # Do NOT delete it — it is the pipeline's source record.
        conn.execute(
            "UPDATE candidate_persons SET match_target_id = ? WHERE id = ?",
            (canonical_id, candidate_id),
        )

    # 7. Flip merge_candidates status.
    conn.execute(
        "UPDATE merge_candidates SET status = 'merged', resolved_at = ? WHERE id = ?",
        (_now_iso(), mc_id),
    )

    # 8. Audit log — record-level row only in Task 2; field-level rows for edits in Task 4.
    canonical_snapshot_after = _row_snapshot(conn, "persons", canonical_id)
    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) VALUES (?, 'person', ?, NULL, 'merge', ?, ?, ?, ?)",
        (
            _new_audit_id(),
            canonical_id,
            json.dumps(candidate_snapshot, ensure_ascii=False),
            json.dumps(canonical_snapshot_after, ensure_ascii=False),
            "curator",
            _now_iso(),
        ),
    )

    return MergeResult(
        canonical_id=canonical_id,
        variants_added=variants_added,
        relations_retargeted=relations_retargeted,
        fields_edited=fields_edited,
        collisions_resolved=collisions_resolved,
    )


def reject_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    note: str | None = None,
) -> RejectResult:
    """Mark a merge_candidates row as rejected and persist a rejected_merges row.

    Phase 6: the rejected_merges row is the linker's filter against re-flagging.
    Candidate A may live in either candidate_persons (typical) or persons
    (escape-hatch case from Phase 5.1) — both paths are handled here.
    """
    mc_row = conn.execute(
        "SELECT status, candidate_a_id, candidate_b_id FROM merge_candidates WHERE id = ?",
        (mc_id,),
    ).fetchone()
    if mc_row is None:
        raise MergeError(f"no merge_candidates row with id={mc_id!r}")
    if mc_row["status"] != "open":
        raise StaleMergeCandidateError(f"merge_candidates {mc_id!r} status is {mc_row['status']!r}")

    cand_a_id = mc_row["candidate_a_id"]
    cand_b_id = mc_row["candidate_b_id"]

    # Phase 5.1 dual-table detection: candidate A can be in either table.
    name, variants, canonical_id = _load_reject_payload(conn, cand_a_id, cand_b_id)
    fingerprint = candidate_fingerprint(name, variants)

    audit_id = _new_audit_id()
    now = _now_iso()

    conn.execute(
        "UPDATE merge_candidates SET status = 'rejected', resolved_at = ? WHERE id = ?",
        (now, mc_id),
    )
    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) "
        "VALUES (?, 'merge_candidate', ?, NULL, 'merge_rejected', '{}', ?, 'curator', ?)",
        (
            audit_id,
            mc_id,
            json.dumps({"note": note, "fingerprint": fingerprint}, ensure_ascii=False),
            now,
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO rejected_merges "
        "(canonical_id, candidate_fingerprint, rejected_at, audit_log_id) "
        "VALUES (?, ?, ?, ?)",
        (canonical_id, fingerprint, now, audit_id),
    )
    return RejectResult(mc_id=mc_id, note=note)


def _load_reject_payload(
    conn: sqlite3.Connection, cand_a_id: str, cand_b_id: str
) -> tuple[str, list[str], str]:
    """Return (name, variants, canonical_id_for_rejected_merges) for reject_merge.

    Phase 5.1 dual-table reality:
      - Typical: A in candidate_persons; B in persons.
        → name from candidate_persons.canonical_name
        → variants from candidate_persons.variants_json
        → canonical_id = B (persons.id)
      - Escape-hatch: A in persons; B in persons.
        → name from persons.canonical_name
        → variants from person_variants
        → canonical_id = A (the rejected pair means "don't merge B into A")
    """
    cp = conn.execute(
        "SELECT canonical_name, variants_json FROM candidate_persons WHERE id = ?",
        (cand_a_id,),
    ).fetchone()
    if cp is not None:
        raw = cp["variants_json"]
        variants: list[str] = []
        if raw:
            parsed = json.loads(raw)
            variants = [v["variant"] for v in parsed if isinstance(v, dict) and "variant" in v]
        return cp["canonical_name"], variants, cand_b_id

    p = conn.execute("SELECT canonical_name FROM persons WHERE id = ?", (cand_a_id,)).fetchone()
    if p is None:
        raise MergeError(f"candidate_a_id {cand_a_id!r} not found in candidate_persons or persons")
    variant_rows = conn.execute(
        "SELECT variant FROM person_variants WHERE person_id = ?", (cand_a_id,)
    ).fetchall()
    return p["canonical_name"], [r["variant"] for r in variant_rows], cand_a_id


def defer_merge(conn: sqlite3.Connection, mc_id: str) -> None:
    """No DB writes — curator's cursor advances in Streamlit memory only.

    Kept as a function so the UI layer has a uniform shape for all five actions.
    """
    return None


def split_person(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    variants_to_extract: list[str],
    note: str | None = None,
) -> SplitResult:
    """Peel listed variants off the source row into a new person row.

    Relations on the source row stay put — the new row starts relation-less.
    The curator can fix relations via the conflicts queue or future undo flow.
    """
    source = _row_snapshot(conn, "persons", person_id)
    if source is None:
        raise MergeError(f"no person row with id={person_id!r}")
    existing_variants = {
        r["variant"]
        for r in conn.execute(
            "SELECT variant FROM person_variants WHERE person_id = ?", (person_id,)
        )
    }
    missing = [v for v in variants_to_extract if v not in existing_variants]
    if missing:
        raise SplitValidationError(f"variants not on source row: {missing!r}")

    new_id = f"per:split:{uuid.uuid4().hex[:12]}"
    # New row inherits canonical_name = first peeled variant; curator can edit later.
    # confidence=1.0 and provenance='curated' are the sensible defaults for a
    # curator-initiated split: the curator is asserting this is a distinct person.
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) VALUES (?, ?, ?, ?)",
        (new_id, variants_to_extract[0], 1.0, "curated"),
    )
    for v in variants_to_extract:
        conn.execute(
            "UPDATE person_variants SET person_id = ? " "WHERE person_id = ? AND variant = ?",
            (new_id, person_id, v),
        )

    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) "
        "VALUES (?, 'person', ?, NULL, 'split', ?, ?, 'curator', ?)",
        (
            _new_audit_id(),
            new_id,
            json.dumps(source, ensure_ascii=False),
            json.dumps(
                {
                    "id": new_id,
                    "source_person_id": person_id,
                    "variants": variants_to_extract,
                    "note": note,
                },
                ensure_ascii=False,
            ),
            _now_iso(),
        ),
    )
    return SplitResult(
        source_person_id=person_id,
        new_person_id=new_id,
        variants_moved=list(variants_to_extract),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _new_audit_id() -> str:
    return f"aud:{uuid.uuid4().hex[:12]}"


def _row_snapshot(conn: sqlite3.Connection, table: str, row_id: str) -> dict[str, Any] | None:
    if table not in _SNAPSHOTTABLE_TABLES:
        raise MergeError(f"refusing to snapshot from {table!r}")
    cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def _candidate_persons_snapshot(
    conn: sqlite3.Connection, candidate_id: str
) -> dict[str, Any] | None:
    """Return a persons-compatible snapshot dict from candidate_persons.

    Drops candidate_persons-only columns (social_category, pipeline_run_id,
    chunk_id, quote, variants_json, match_target_id) and filters out local
    state_id values (e.g. 's1') that cannot be safely folded into canonical rows.

    Returns None if the row does not exist.
    """
    row = conn.execute(
        "SELECT id, canonical_name, gender, birth_date_json, death_date_json, "
        "notes, state_id, clan_name, confidence "
        "FROM candidate_persons WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None

    snapshot: dict[str, Any] = dict(row)

    # Filter out local-extraction state_id values so they are never folded
    # into the canonical row.  If detection is ambiguous, treat as NULL.
    raw_state = snapshot.get("state_id")
    if raw_state is not None:
        is_local = bool(_LOCAL_STATE_ID_RE.match(str(raw_state)))
        if is_local:
            snapshot["state_id"] = None
        else:
            # Also verify the state_id exists in the states table; if not, treat as NULL.
            exists = conn.execute("SELECT 1 FROM states WHERE id = ?", (raw_state,)).fetchone()
            if exists is None:
                snapshot["state_id"] = None

    return snapshot
