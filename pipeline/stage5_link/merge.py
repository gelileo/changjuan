"""Stage 5 merge actions — the load-bearing module behind the curator UI.

Each public function takes a sqlite Connection and performs its DB writes
in a single BEGIN ... COMMIT transaction. On any error the transaction
is rolled back; in particular, the audit_log row is atomic with the data
change. This atomicity is what makes the field_history view (founding
spec §5) correct.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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
    raise NotImplementedError  # implemented in Task 2


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
    cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cur.fetchone()
    return dict(row) if row else None
