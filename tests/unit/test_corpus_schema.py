import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CORPUS_SCHEMA


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}


def test_corpus_schema_creates_expected_tables(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        names = _table_names(conn)
    assert {"documents", "chunks", "citations"} <= names


def test_corpus_schema_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        apply_schema(conn, CORPUS_SCHEMA)
        assert "documents" in _table_names(conn)


def test_documents_required_columns(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(documents);")}
    assert {
        "id",
        "corpus",
        "title",
        "chapter_num",
        "chapter_title",
        "raw_text",
        "source_edition",
        "ingested_at",
    } <= cols
