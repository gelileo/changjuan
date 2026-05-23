from __future__ import annotations

import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA

CORE_TABLES = {
    "persons",
    "person_variants",
    "states",
    "state_capitals",
    "places",
    "events",
    "event_participants",
    "event_places",
    "event_relations",
    "person_relations",
    "person_states",
    "entity_citations",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}


def test_canonical_schema_creates_core_tables(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        names = _table_names(conn)
    missing = CORE_TABLES - names
    assert not missing, f"missing tables: {missing}"


def test_person_relations_includes_clan_member_kind(tmp_path: Path) -> None:
    """clan_member is the kind used until Family is promoted to a first-class entity."""
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:a', 'a', 0.9, 'auto');"
        )
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:b', 'b', 0.9, 'auto');"
        )
        conn.execute(
            "INSERT INTO person_relations"
            " (from_person_id, to_person_id, kind, confidence, provenance)"
            " VALUES ('per:a', 'per:b', 'clan_member', 0.9, 'auto');"
        )


EXTRA_TABLES = {
    "candidate_persons",
    "candidate_events",
    "candidate_places",
    "candidate_states",
    "candidate_event_participants",
    "candidate_event_places",
    "candidate_event_relations",
    "candidate_person_relations",
    "candidate_person_states",
    "candidate_facts",
    "conflicts",
    "audit_log",
    "pipeline_runs",
    "llm_cache",
    "merge_candidates",
    "qa_samples",
}


def test_canonical_schema_creates_candidate_and_bookkeeping_tables(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        names = _table_names(conn)
    missing = EXTRA_TABLES - names
    assert not missing, f"missing: {missing}"


def test_field_history_view_exists(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        views = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='view';")
        }
    assert "field_history" in views


def test_audit_log_field_history_query(tmp_path: Path) -> None:
    """Sanity-check the view: insert a field-level audit row, read it back via field_history."""
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO audit_log"
            " (id, entity_kind, entity_id, field, change_kind,"
            " before_json, after_json, actor)"
            " VALUES ('al:1', 'person', 'per:a', 'birth_year', 'set',"
            " NULL, '{\"value\": 697, \"confidence\": 0.6}', 'extract@v1');"
        )
        rows = list(
            conn.execute(
                "SELECT entity_id, field, value_json, confidence, source" " FROM field_history;"
            )
        )
    assert rows[0]["entity_id"] == "per:a"
    assert rows[0]["field"] == "birth_year"
    assert rows[0]["confidence"] == 0.6
    assert rows[0]["source"] == "extract@v1"


def test_rejected_merges_table_exists() -> None:
    """Phase 6: rejected_merges is part of the canonical schema."""
    import sqlite3

    from pipeline.db import apply_schema
    from pipeline.schemas import CANONICAL_SCHEMA

    conn = sqlite3.connect(":memory:")
    apply_schema(conn, CANONICAL_SCHEMA)
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='rejected_merges'"
    ).fetchone()
    assert row is not None, "rejected_merges table missing from schema"
    ddl = row[0]
    assert "canonical_id" in ddl
    assert "candidate_fingerprint" in ddl
    assert "PRIMARY KEY" in ddl

    idx = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND name='idx_rejected_merges_fingerprint'"
    ).fetchone()
    assert idx is not None, "fingerprint index missing"
