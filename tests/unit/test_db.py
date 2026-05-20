from pathlib import Path

import pytest

from pipeline.db import apply_schema, connect

SCHEMA_SQL = """
CREATE TABLE widgets (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES widgets(id)
);
"""


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with connect(db) as conn:
        cur = conn.execute("PRAGMA foreign_keys;")
        assert cur.fetchone()[0] == 1


def test_apply_schema_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with connect(db) as conn:
        apply_schema(conn, SCHEMA_SQL)
        apply_schema(conn, SCHEMA_SQL)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        names = {row[0] for row in cur}
        assert "widgets" in names


def test_foreign_key_violation_raises(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with connect(db) as conn:
        apply_schema(conn, SCHEMA_SQL)
        with pytest.raises(Exception):
            conn.execute("INSERT INTO widgets (id, parent_id) VALUES ('a', 'missing');")
            conn.commit()
