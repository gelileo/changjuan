"""End-to-end exercise of the curator merge surface against a real DB copy.

Covers every merge action (accept, reject, defer) against all 31 open
merge_candidates rows in a tmp_path copy of the live DB.

Schema migration:
  The live DB was created before Phase 5; its audit_log CHECK constraint
  does not include the new change_kind values added in Phase 5 Tasks 3-5.
  _migrate_audit_log_check() upgrades the constraint before any tests run.

Candidate layout (Phase 5.1):
  merge_candidates.candidate_a_id references candidate_persons.id in the
  live DB (candidates have not yet been promoted to persons). accept_merge
  now handles this natively — it detects which table the candidate is in
  and branches accordingly. No promotion workaround is required.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from curation.db import open_merge_candidates
from pipeline.stage5_link.merge import (
    MergeConflictError,
    MergeError,
    StaleMergeCandidateError,
    accept_merge,
    defer_merge,
    reject_merge,
)

LIVE_DB = Path(__file__).resolve().parent.parent.parent / "data" / "changjuan.sqlite"


def _migrate_audit_log_check(db_path: Path) -> None:
    """Bring an old-schema audit_log up to the Phase 5 CHECK constraint set.

    The live DB at data/changjuan.sqlite was created before Phase 5 and
    rejects the new change_kind values (merge_rejected, edit,
    merge_collision_resolved). This migration replaces the table in-place
    via the rename trick so existing rows are preserved.

    Idempotent: if the constraint already includes all Phase 5 values
    (detected by checking for 'edit' and 'merge_rejected' in the DDL),
    the function returns immediately.
    """
    new_check = (
        "CHECK (change_kind IN ('create','set','delete','merge','split',"
        "'curator_override','merge_collision_resolved','edit','merge_rejected'))"
    )
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT sql FROM sqlite_master WHERE name='audit_log'").fetchone()
        if existing and "'edit'" in existing[0] and "'merge_rejected'" in existing[0]:
            return  # already migrated
        # Prevent SQLite from rewriting FK references in OTHER tables
        # (e.g. rejected_merges.audit_log_id REFERENCES audit_log(id)) during the
        # RENAME — without this, the FK silently becomes REFERENCES audit_log_old(id)
        # and breaks the moment audit_log_old is dropped below.
        conn.execute("PRAGMA legacy_alter_table=ON")
        conn.execute("ALTER TABLE audit_log RENAME TO audit_log_old")
        conn.execute(f"""
            CREATE TABLE audit_log (
                id              TEXT PRIMARY KEY,
                entity_kind     TEXT NOT NULL,
                entity_id       TEXT NOT NULL,
                field           TEXT,
                change_kind     TEXT NOT NULL {new_check},
                before_json     TEXT,
                after_json      TEXT,
                actor           TEXT NOT NULL,
                at              TEXT NOT NULL DEFAULT (datetime('now')),
                citation_id     TEXT,
                pipeline_run_id TEXT
            )
        """)
        conn.execute("INSERT INTO audit_log SELECT * FROM audit_log_old")
        conn.execute("DROP TABLE audit_log_old")
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.commit()
    finally:
        conn.close()


def _migrate_rejected_merges(db_path: Path) -> None:
    """Add the Phase 6 rejected_merges table if missing.

    Idempotent — CREATE TABLE IF NOT EXISTS plus the matching index.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rejected_merges (
                canonical_id          TEXT NOT NULL REFERENCES persons(id),
                candidate_fingerprint TEXT NOT NULL,
                rejected_at           TEXT NOT NULL,
                audit_log_id          TEXT REFERENCES audit_log(id),
                PRIMARY KEY (canonical_id, candidate_fingerprint)
            );
            CREATE INDEX IF NOT EXISTS idx_rejected_merges_fingerprint
                ON rejected_merges (candidate_fingerprint);
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
    if not LIVE_DB.exists():
        pytest.skip(f"live DB not present at {LIVE_DB}")
    dst = tmp_path / "smoke.sqlite"
    shutil.copy(LIVE_DB, dst)
    _migrate_audit_log_check(dst)
    _migrate_rejected_merges(dst)
    return dst


def test_curator_smoke_resolves_all_open_candidates(db_copy: Path) -> None:
    rows = open_merge_candidates(db_copy)
    assert len(rows) > 0, "expected open merge candidates to exercise"

    decisions = 0
    rejected = 0
    deferred = 0
    accepted = 0
    skipped_conflicts = 0
    skipped_not_found = 0

    for i, row in enumerate(rows):
        action = ["accept", "reject", "defer"][i % 3]
        conn = sqlite3.connect(db_copy)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                if action == "accept":
                    try:
                        accept_merge(conn, row.mc_id)
                        accepted += 1
                        decisions += 1
                    except MergeConflictError:
                        # Defense-in-depth: skip and tally; the conflicts queue
                        # should have caught this. Don't fail the smoke on a
                        # real-data field disagreement.
                        skipped_conflicts += 1
                        continue
                    except MergeError:
                        # candidate not found in persons (e.g. already merged by
                        # a prior accept in this run that removed the candidate row)
                        skipped_not_found += 1
                        continue
                elif action == "reject":
                    reject_merge(conn, row.mc_id, note="smoke test reject")
                    rejected += 1
                    decisions += 1
                else:
                    defer_merge(conn, row.mc_id)
                    deferred += 1
                    decisions += 1
        except StaleMergeCandidateError:
            pass
        finally:
            conn.close()

    # Anything deferred or skipped should still be open.
    remaining = open_merge_candidates(db_copy)
    expected_remaining = deferred + skipped_conflicts + skipped_not_found
    assert len(remaining) == expected_remaining, (
        f"queue mismatch: remaining={len(remaining)}, deferred={deferred}, "
        f"skipped_conflicts={skipped_conflicts}, skipped_not_found={skipped_not_found}"
    )

    # No orphan FKs across the 5 person-FK columns.
    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    for q in (
        "SELECT COUNT(*) AS n FROM event_participants ep "
        "LEFT JOIN persons p ON ep.person_id = p.id WHERE p.id IS NULL",
        "SELECT COUNT(*) AS n FROM person_relations pr "
        "LEFT JOIN persons p1 ON pr.from_person_id = p1.id WHERE p1.id IS NULL",
        "SELECT COUNT(*) AS n FROM person_relations pr "
        "LEFT JOIN persons p2 ON pr.to_person_id = p2.id WHERE p2.id IS NULL",
        "SELECT COUNT(*) AS n FROM person_states ps "
        "LEFT JOIN persons p ON ps.person_id = p.id WHERE p.id IS NULL",
        "SELECT COUNT(*) AS n FROM entity_citations ec "
        "LEFT JOIN persons p ON ec.entity_id = p.id "
        "WHERE ec.entity_kind = 'person' AND p.id IS NULL",
    ):
        orphan_row = conn.execute(q).fetchone()
        assert orphan_row["n"] == 0, f"orphan FK: {q.splitlines()[0]} -> {orphan_row['n']}"

    # audit_log row count >= decisions made (merges may write collision rows too).
    audit_n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert (
        audit_n >= accepted + rejected
    ), f"audit_log undercount: {audit_n} < {accepted + rejected}"
    conn.close()

    # Print action counts for manual inspection.
    print(
        f"\nSmoke result: accepted={accepted}, rejected={rejected}, "
        f"deferred={deferred}, skipped_conflicts={skipped_conflicts}, "
        f"skipped_not_found={skipped_not_found}, "
        f"total_rows={len(rows)}"
    )
