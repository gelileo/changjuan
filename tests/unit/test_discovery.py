"""Discovery: scan corpus chapters for state-name occurrences."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pipeline.discovery import (
    STATE_NAMES,
    discover_states_for_chapters,
)


def _seed_corpus(path: Path) -> sqlite3.Connection:
    """Build a synthetic corpus.sqlite mirroring the real schema."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            chapter_num INTEGER NOT NULL
        );
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            text TEXT NOT NULL
        );
        """
    )
    return conn


def _insert_chapter(conn: sqlite3.Connection, chapter_num: int, text: str) -> None:
    doc_id = f"doc:ch{chapter_num}"
    conn.execute("INSERT INTO documents (id, chapter_num) VALUES (?, ?)", (doc_id, chapter_num))
    conn.execute(
        "INSERT INTO chunks (id, document_id, text) VALUES (?, ?, ?)",
        (f"chk:{chapter_num}:1", doc_id, text),
    )
    conn.commit()


def test_finds_known_states_in_text(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    conn = _seed_corpus(db)
    _insert_chapter(conn, 2, "晋公子重耳出奔齐, 齐桓公厚待之.")
    conn.close()

    result = discover_states_for_chapters(db, [2])
    state_ids = {row["state_id"] for row in result}
    assert "sta:jin" in state_ids
    assert "sta:qi" in state_ids


def test_counts_occurrences(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    conn = _seed_corpus(db)
    _insert_chapter(conn, 2, "晋晋晋齐")
    conn.close()

    result = discover_states_for_chapters(db, [2])
    jin = next(r for r in result if r["state_id"] == "sta:jin")
    qi = next(r for r in result if r["state_id"] == "sta:qi")
    assert jin["count"] == 3
    assert qi["count"] == 1


def test_aggregates_across_chapters(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    conn = _seed_corpus(db)
    _insert_chapter(conn, 2, "晋")
    _insert_chapter(conn, 3, "晋晋")
    conn.close()

    result = discover_states_for_chapters(db, [2, 3])
    jin = next(r for r in result if r["state_id"] == "sta:jin")
    assert jin["count"] == 3
    assert jin["chapters"] == [2, 3]


def test_excludes_states_not_in_text(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    conn = _seed_corpus(db)
    _insert_chapter(conn, 2, "晋")
    conn.close()

    result = discover_states_for_chapters(db, [2])
    state_ids = {r["state_id"] for r in result}
    assert "sta:qi" not in state_ids
    assert "sta:jin" in state_ids


def test_state_names_constant_has_expected_entries() -> None:
    assert STATE_NAMES["晋"] == "sta:jin"
    assert STATE_NAMES["周"] == "sta:zhou"
    assert STATE_NAMES["鲁"] == "sta:lu"
    assert len(STATE_NAMES) >= 14
