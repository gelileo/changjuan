"""Unit tests for curation.db read helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from curation.db import (
    ChapterStatus,
    coverage_stats,
    low_confidence_count,
    open_merge_candidates,
)
from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "curation_test.sqlite"
    with connect(db_path) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    return db_path


def test_open_merge_candidates_filters_status(empty_db: Path) -> None:
    # merge_candidates has no FK to persons — insert directly
    with connect(empty_db) as conn:
        conn.execute(
            "INSERT INTO merge_candidates "
            "(id, kind, candidate_a_id, candidate_b_id, score, status) "
            "VALUES ('mc:1', 'person', 'cand:per:run:1:p1', 'cand:per:run:1:p2', 0.7, 'open'), "
            "       ('mc:2', 'person', 'cand:per:run:1:p1', 'cand:per:run:1:p2', 0.7, 'merged')"
        )
    rows = open_merge_candidates(empty_db)
    assert len(rows) == 1
    assert rows[0].mc_id == "mc:1"


def test_open_merge_candidates_sorted_by_created_at(empty_db: Path) -> None:
    # merge_candidates has no FK to persons — insert directly
    with connect(empty_db) as conn:
        _CA, _CB = "cand:per:run:1:p1", "cand:per:run:1:p2"
        conn.executemany(
            "INSERT INTO merge_candidates "
            "(id, kind, candidate_a_id, candidate_b_id, score, status, created_at) "
            "VALUES (?, 'person', ?, ?, 0.7, 'open', ?)",
            [
                ("mc:2", _CA, _CB, "2026-05-22 10:00:00"),
                ("mc:1", _CA, _CB, "2026-05-22 09:00:00"),
            ],
        )
    rows = open_merge_candidates(empty_db)
    assert [r.mc_id for r in rows] == ["mc:1", "mc:2"]


def test_coverage_stats_returns_108_rows(empty_db: Path, tmp_path: Path) -> None:
    """Even with an empty corpus, coverage_stats should return exactly 108 ChapterStatus rows.

    coverage_stats reads chapter list from corpus.sqlite; for the test we
    point at a synthetic corpus DB with 108 rows.
    """
    corpus_path = tmp_path / "corpus.sqlite"
    from pipeline.schemas import CORPUS_SCHEMA

    with connect(corpus_path) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        for n in range(1, 109):
            conn.execute(
                "INSERT INTO documents (id, corpus, title, chapter_num, "
                "chapter_title, raw_text, source_edition, ingested_at) "
                "VALUES (?, 'dongzhoulieguozhi', '东周列国志', ?, ?, "
                "'', 'test', '2026-05-22')",
                (f"doc:{n}", n, f"第{n}回"),
            )
    stats = coverage_stats(empty_db, corpus_path=corpus_path)
    assert len(stats) == 108
    assert all(isinstance(s, ChapterStatus) for s in stats)
    assert all(not s.extracted for s in stats)


def test_low_confidence_count_handles_empty_db(empty_db: Path) -> None:
    assert low_confidence_count(empty_db) == 0


def test_chapter_citation_context_miss_returns_placeholder(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.sqlite"
    from pipeline.schemas import CORPUS_SCHEMA

    with connect(corpus) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
    from curation.db import chapter_citation_context

    ctx = chapter_citation_context("cite:does-not-exist", corpus_path=corpus)
    assert ctx.text == "(citation not found)"
