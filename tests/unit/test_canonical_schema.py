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
