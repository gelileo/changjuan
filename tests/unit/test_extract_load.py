"""End-to-end: skill-produced YAML → candidate_* rows."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml

from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction


@pytest.fixture
def setup(
    tmp_path: Path,
) -> Generator[tuple[sqlite3.Connection, sqlite3.Connection], None, None]:
    corpus = open_corpus_db(tmp_path / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "changjuan.sqlite")
    corpus.execute(
        "INSERT INTO documents "
        "(id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at) "
        "VALUES (1, 'dongzhoulieguozhi', 't', 1, 'ch1', '...', 'test', datetime('now'))"
    )
    corpus.execute(
        "INSERT INTO chunks "
        "(id, document_id, paragraph_start, paragraph_end, text, hash) "
        "VALUES ('chk:ch01-001', 1, 1, 1, '重耳奔狄', 'h')"
    )
    corpus.commit()
    yield corpus, canonical


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def test_valid_extraction_loads_to_candidates(
    setup: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
) -> None:
    corpus, canonical = setup
    f = tmp_path / "extract.yaml"
    _write(
        f,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [0, 2],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳"},
                }
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    stats = load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f,
        prompt_version="v1",
        pipeline_run_id="run:test",
    )
    assert stats["persons_written"] == 1
    assert stats["invariant_violations"] == []
    rows = canonical.execute(
        "SELECT canonical_name FROM candidate_persons WHERE pipeline_run_id='run:test'"
    ).fetchall()
    assert rows[0][0] == "重耳"


def test_invalid_record_skipped(
    setup: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
) -> None:
    corpus, canonical = setup
    f = tmp_path / "extract.yaml"
    _write(
        f,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "X",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [0, 4],
                        "quote": "不存在",
                    },
                    "justifications": {"canonical_name": "不存在"},
                }
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    stats = load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f,
        prompt_version="v1",
        pipeline_run_id="run:test",
    )
    assert stats["persons_written"] == 0
    assert len(stats["invariant_violations"]) == 1


def test_loads_event_place_state_relation(
    setup: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
) -> None:
    """All five kinds round-trip into candidate_* tables."""
    corpus, canonical = setup
    f = tmp_path / "extract.yaml"
    _write(
        f,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [0, 2],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳"},
                },
            ],
            "places": [
                {
                    "id": "pl1",
                    "name": "狄",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [3, 4],
                        "quote": "狄",
                    },
                    "justifications": {"name": "狄"},
                },
            ],
            "states": [
                {
                    "id": "s1",
                    "name": "狄",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [3, 4],
                        "quote": "狄",
                    },
                    "justifications": {"name": "狄"},
                },
            ],
            "events": [
                {
                    "id": "e1",
                    "type": "出奔",
                    "primary_place_id": "pl1",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [2, 4],
                        "quote": "奔狄",
                    },
                    "justifications": {"type": "奔"},
                },
            ],
            "relations": [
                {
                    "kind": "event_participant",
                    "event_id": "e1",
                    "person_id": "p1",
                    "role": "主",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [0, 4],
                        "quote": "重耳奔狄",
                    },
                },
            ],
        },
    )
    stats = load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f,
        prompt_version="v1",
        pipeline_run_id="run:multi",
    )
    assert stats["persons_written"] == 1
    assert stats["events_written"] == 1
    assert stats["places_written"] == 1
    assert stats["states_written"] == 1
    assert stats["relations_written"] >= 1
