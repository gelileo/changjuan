"""SQLite helpers: connection with sensible defaults + idempotent schema application."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with foreign keys + WAL enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def apply_schema(conn: sqlite3.Connection, sql: str) -> None:
    """Apply a SQL DDL script. Idempotent: re-running on an existing schema is a no-op."""
    # executescript issues an implicit COMMIT; wrap in try/except so that
    # repeated calls with the same DDL (without IF NOT EXISTS) are safe.
    try:
        conn.executescript(sql)
    except sqlite3.OperationalError as exc:
        if "already exists" not in str(exc):
            raise
    conn.commit()
