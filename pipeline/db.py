"""SQLite helpers: connection with sensible defaults + idempotent schema application."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA


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
    """Apply a SQL DDL script. Idempotent if the script uses IF NOT EXISTS."""
    conn.executescript(sql)
    conn.commit()


def open_canonical_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the canonical changjuan.sqlite, apply schema, and return the
    connection. Caller is responsible for closing. Used by CLI verbs and tests."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    apply_schema(conn, CANONICAL_SCHEMA)
    return conn


def open_corpus_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the corpus.sqlite, apply schema, and return the connection.
    Caller is responsible for closing. Used by CLI verbs and tests."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    apply_schema(conn, CORPUS_SCHEMA)
    return conn
