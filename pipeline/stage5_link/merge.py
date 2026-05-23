"""Stage 5 merge actions — the load-bearing module behind the curator UI.

Each public function takes a sqlite Connection and performs its DB writes
in a single BEGIN ... COMMIT transaction. On any error the transaction
is rolled back; in particular, the audit_log row is atomic with the data
change. This atomicity is what makes the field_history view (founding
spec §5) correct.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Tables that _row_snapshot is permitted to read.
_SNAPSHOTTABLE_TABLES: frozenset[str] = frozenset({"persons", "events", "places", "states"})


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


def accept_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    edits: dict[str, Any] | None = None,
) -> MergeResult:
    """Fuse candidate (A) into canonical (B). Survivor = canonical.

    See spec §3 for the full algorithm. All work happens in one transaction.
    """
    # Edits are processed in Task 4. For Task 2, edits must be None or empty.
    if edits:
        raise NotImplementedError("edits handled in Task 4")

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

    # Snapshots for audit_log.
    candidate_snapshot = _row_snapshot(conn, "persons", candidate_id)
    if candidate_snapshot is None:
        raise MergeError(f"candidate person {candidate_id!r} not found")
    canonical_snapshot_before = _row_snapshot(conn, "persons", canonical_id)
    if canonical_snapshot_before is None:
        raise MergeError(f"canonical person {canonical_id!r} not found")

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

    # 4. Variant fold (UNIQUE(person_id, variant, kind) makes this collision-safe).
    existing = {
        (r["variant"], r["kind"])
        for r in conn.execute(
            "SELECT variant, kind FROM person_variants WHERE person_id = ?", (canonical_id,)
        )
    }
    variants_added = 0
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

    # 5. FK retarget across the 5 person-FK columns. Task 3 adds collision handling;
    #    for Task 2 the seeded fixture has no collisions, so naive UPDATE suffices.
    relations_retargeted = 0
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

    # 6. Delete candidate row. person_variants with person_id=candidate_id are gone
    #    (all either moved or deleted in step 4).
    conn.execute("DELETE FROM persons WHERE id = ?", (candidate_id,))

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
        fields_edited=0,
    )


def reject_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    note: str | None = None,
) -> RejectResult:
    """Mark a merge_candidates row as rejected with an optional curator note."""
    raise NotImplementedError  # implemented in Task 5


def defer_merge(conn: sqlite3.Connection, mc_id: str) -> None:
    """No-op from the DB's perspective. Curator advances the cursor in-memory."""
    raise NotImplementedError  # implemented in Task 5


def split_person(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    variants_to_extract: list[str],
    note: str | None = None,
) -> SplitResult:
    """Peel listed variants into a new person row. Source-row relations stay put."""
    raise NotImplementedError  # implemented in Task 6


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
