"""One-time, idempotent migration of an existing canonical.sqlite from the
states-named schema to the groups-named schema. Sets group_type='state' on every
migrated row. Brings dzl's canonical.sqlite to schema_version 7 WITHOUT
re-extraction (preserves all data exactly)."""

from __future__ import annotations

import sqlite3


def run(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    names = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "groups" in names and "states" not in names:
        return  # already migrated (idempotent)

    cur.execute("PRAGMA foreign_keys = OFF;")

    # 1. groups <- states (+ group_type='state')
    cur.execute(
        "CREATE TABLE groups (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "founded_date_json TEXT, ended_date_json TEXT, ruling_clan TEXT, "
        "group_type TEXT, confidence REAL NOT NULL, provenance TEXT NOT NULL, "
        "pipeline_run_id TEXT, created_at TEXT, updated_at TEXT);"
    )
    cur.execute(
        "INSERT INTO groups (id,name,founded_date_json,ended_date_json,ruling_clan,"
        "group_type,confidence,provenance,pipeline_run_id,created_at,updated_at) "
        "SELECT id,name,founded_date_json,ended_date_json,ruling_clan,"
        "'state',confidence,provenance,pipeline_run_id,created_at,updated_at FROM states;"
    )
    cur.execute("DROP TABLE states;")

    # 2. persons.state_id -> persons.group_id
    cur.execute("ALTER TABLE persons RENAME COLUMN state_id TO group_id;")

    # 3. person_states -> person_groups
    cur.execute("ALTER TABLE person_states RENAME TO person_groups;")
    cur.execute("ALTER TABLE person_groups RENAME COLUMN state_id TO group_id;")

    # 4. state_capitals -> group_seats (if present)
    names = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "state_capitals" in names:
        cur.execute("ALTER TABLE state_capitals RENAME TO group_seats;")
        cur.execute("ALTER TABLE group_seats RENAME COLUMN state_id TO group_id;")

    # 5. entity_citations value rename
    cur.execute("UPDATE entity_citations SET entity_kind='group' WHERE entity_kind='state';")
    cur.execute(
        "UPDATE entity_citations SET entity_kind='group_seat' WHERE entity_kind='state_capital';"
    )

    conn.commit()
