"""Unit tests for pipeline.stage5_link.merge.

Each test seeds a fresh tmp_path DB via tests.fixtures.curation.seed_merge_db,
then exercises one branch of one merge action.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.db import connect
from pipeline.stage5_link.merge import (
    MergeResult,
    StaleMergeCandidateError,
    accept_merge,
    defer_merge,
    reject_merge,
)
from tests.fixtures.curation.seed_merge_db import (
    add_entity_citations_duplicate,
    add_event_participants_collision,
    add_person_relations_self_loop,
    add_person_states_collision,
    seed,
)


@pytest.fixture
def seeded_db(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "merge_test.sqlite"
    mc_id = seed(db_path)
    return db_path, mc_id


def test_accept_merge_happy_path_returns_result(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert isinstance(result, MergeResult)
    assert result.canonical_id == "per:test:canonical"
    assert result.variants_added == 1  # 周宣王 fold; 宣王 already on canonical
    assert result.relations_retargeted == 1  # event_participants row
    assert result.fields_edited == 0
    assert result.collisions_resolved == 0


def test_accept_merge_writes_audit_log_row(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT change_kind, entity_kind, entity_id, before_json, after_json "
            "FROM audit_log WHERE entity_id = 'per:test:canonical' "
            "AND change_kind = 'merge'"
        ).fetchone()
    assert row is not None
    assert row["entity_kind"] == "person"
    before = json.loads(row["before_json"])
    after = json.loads(row["after_json"])
    assert before["id"] == "per:test:candidate"  # candidate snapshot
    assert after["id"] == "per:test:canonical"  # post-merge canonical


def test_accept_merge_flips_status_and_resolved_at(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, resolved_at FROM merge_candidates WHERE id = ?", (mc_id,)
        ).fetchone()
    assert row["status"] == "merged"
    assert row["resolved_at"] is not None


def test_accept_merge_retargets_event_participants(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id FROM event_participants WHERE event_id = 'evt:test:1'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["person_id"] == "per:test:canonical"


def test_accept_merge_deletes_candidate_row(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        row = conn.execute("SELECT id FROM persons WHERE id = 'per:test:candidate'").fetchone()
    assert row is None


def test_accept_merge_folds_variants_dedup(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT variant, kind FROM person_variants WHERE person_id = 'per:test:canonical' "
            "ORDER BY variant"
        ).fetchall()
    variants = {(r["variant"], r["kind"]) for r in rows}
    # canonical had 宣王 (谥号); candidate brought 周宣王 (谥号)
    assert variants == {("宣王", "谥号"), ("周宣王", "谥号")}


def test_accept_merge_stale_raises(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        conn.execute("UPDATE merge_candidates SET status = 'merged' WHERE id = ?", (mc_id,))
    with connect(db_path) as conn:
        with pytest.raises(StaleMergeCandidateError):
            accept_merge(conn, mc_id)


def test_accept_merge_event_participants_collision_keeps_higher_confidence(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_event_participants_collision(db_path)  # canonical row, confidence 0.95
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id, confidence FROM event_participants "
            "WHERE event_id = 'evt:test:1' AND role = 'victor'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["person_id"] == "per:test:canonical"
    assert rows[0]["confidence"] == 0.95  # higher-confidence row survived


def test_accept_merge_person_relations_self_loop_deletes(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_person_relations_self_loop(db_path)
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM person_relations WHERE kind = 'spouse'").fetchone()
    assert row is None  # self-loop was deleted, not folded


def test_accept_merge_person_states_collision_keeps_higher_confidence(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_person_states_collision(db_path)
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id, confidence FROM person_states "
            "WHERE state_id = 'sta:周' AND role = 'ruler'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["confidence"] == 0.95


def test_accept_merge_entity_citations_duplicate_drops_candidate(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_entity_citations_duplicate(db_path)
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT entity_id FROM entity_citations "
            "WHERE entity_kind = 'person' AND citation_id = 'cite:test:1'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "per:test:canonical"


def test_accept_merge_collision_writes_audit_log(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    add_event_participants_collision(db_path)
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT entity_kind, change_kind FROM audit_log "
            "WHERE change_kind = 'merge_collision_resolved'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_kind"] == "event_participant"


def test_accept_merge_with_edits_applies_field_change(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id, edits={"clan_name": "姬"})
    assert result.fields_edited == 1
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT clan_name FROM persons WHERE id = 'per:test:canonical'"
        ).fetchone()
    assert row["clan_name"] == "姬"


def test_accept_merge_with_edits_writes_field_level_audit(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id, edits={"notes": "edited by curator"})
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT field, before_json, after_json FROM audit_log "
            "WHERE entity_id = 'per:test:canonical' AND field = 'notes'"
        ).fetchone()
    assert row is not None
    assert row["field"] == "notes"
    after = json.loads(row["after_json"])
    assert after["value"] == "edited by curator"
    # before_json should match the §5 shape: {value, confidence, source_excerpt}
    before = json.loads(row["before_json"])
    assert "value" in before and "confidence" in before


def test_accept_merge_event_participants_collision_tie_keeps_canonical(
    seeded_db: tuple[Path, str],
) -> None:
    """On equal confidence, canonical wins (candidate is the loser)."""
    db_path, mc_id = seeded_db
    # Set both rows to confidence 0.9 (the seeded candidate's value).
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO event_participants "
            "(event_id, person_id, role, confidence, provenance) "
            "VALUES ('evt:test:1', 'per:test:canonical', 'victor', 0.9, 'auto')",
        )
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id, confidence FROM event_participants "
            "WHERE event_id = 'evt:test:1' AND role = 'victor'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["person_id"] == "per:test:canonical"
    assert rows[0]["confidence"] == 0.9


def test_reject_merge_flips_status(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = reject_merge(conn, mc_id, note="different people")
    assert result.mc_id == mc_id
    assert result.note == "different people"
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, resolved_at FROM merge_candidates WHERE id = ?",
            (mc_id,),
        ).fetchone()
    assert row["status"] == "rejected"
    assert row["resolved_at"] is not None
    # Note: merge_candidates has no curator_note column. The note lives on
    # the audit_log row (asserted in test_reject_merge_writes_audit_log below).


def test_reject_merge_writes_audit_log(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        reject_merge(conn, mc_id, note="different people")
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT change_kind, before_json, after_json FROM audit_log "
            "WHERE change_kind = 'merge_rejected'"
        ).fetchone()
    assert row is not None
    after = json.loads(row["after_json"])
    assert after["note"] == "different people"


def test_reject_merge_stale_raises(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        conn.execute("UPDATE merge_candidates SET status='rejected' WHERE id = ?", (mc_id,))
    with connect(db_path) as conn:
        with pytest.raises(StaleMergeCandidateError):
            reject_merge(conn, mc_id)


def test_defer_merge_is_noop(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    # Snapshot the full DB before/after; assert equality.
    before = _dump(db_path)
    with connect(db_path) as conn:
        defer_merge(conn, mc_id)
    after = _dump(db_path)
    assert before == after


def _dump(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Full-DB snapshot for atomicity assertions. Returns table -> rows."""
    out: dict[str, list[tuple[Any, ...]]] = {}
    with connect(db_path) as conn:
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' " "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            out[table] = [tuple(r) for r in rows]
    return out
