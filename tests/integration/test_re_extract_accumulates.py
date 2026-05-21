"""Re-extract v1 → v2 with a deliberately divergent payload; assert:
- variants from both runs accumulate.
- scalar disagreements become Conflict rows.
- both citations land in entity_citations.
- provenance='curated' fields aren't silently overwritten."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml

from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction
from pipeline.stage7_load import load_candidate_persons

pytestmark = pytest.mark.integration

_DOC_INSERT = (
    "INSERT INTO documents"
    " (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at)"
    " VALUES (1, 'dongzhoulieguozhi', 't', 1, 'ch1', ?, 'test', datetime('now'))"
)
_CHUNK_INSERT = (
    "INSERT INTO chunks"
    " (id, document_id, paragraph_start, paragraph_end, text, hash)"
    " VALUES (?, 1, ?, ?, ?, ?)"
)


def _write(p: Path, payload: dict[str, Any]) -> None:
    p.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def _seed_corpus(
    tmp_path: Path,
) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    corpus = open_corpus_db(tmp_path / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "changjuan.sqlite")
    corpus.execute(_DOC_INSERT, ("重耳奔狄",))
    corpus.execute(_CHUNK_INSERT, ("chk:1", 1, 1, "重耳奔狄", "h"))
    corpus.commit()
    return corpus, canonical


def test_re_extract_accumulates_variants(tmp_path: Path) -> None:
    """v1 adds a variant; v2 adds a different variant; the canonical Person should have both."""
    corpus, canonical = _seed_corpus(tmp_path)

    # v1: 重耳 with variant 公子重耳
    f1 = tmp_path / "v1.yaml"
    _write(
        f1,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "variants": [{"variant": "公子重耳", "kind": "别名"}],
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [0, 2],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f1,
        prompt_version="v1",
        pipeline_run_id="run:v1",
    )
    load_candidate_persons(canonical, "run:v1")

    # v2: 重耳 with a DIFFERENT variant 晋公子
    f2 = tmp_path / "v2.yaml"
    _write(
        f2,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "variants": [{"variant": "晋公子", "kind": "别名"}],
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [2, 4],
                        "quote": "奔狄",
                    },
                    "justifications": {"canonical_name": "奔狄"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f2,
        prompt_version="v2",
        pipeline_run_id="run:v2",
    )
    load_candidate_persons(canonical, "run:v2")

    # One canonical Person; two variants accumulated
    persons = canonical.execute("SELECT id, canonical_name FROM persons").fetchall()
    assert len(persons) == 1
    person_id = persons[0][0]

    variants = canonical.execute(
        "SELECT variant FROM person_variants WHERE person_id = ?", (person_id,)
    ).fetchall()
    variant_names = sorted(v[0] for v in variants)
    assert "公子重耳" in variant_names
    assert "晋公子" in variant_names


def test_re_extract_emits_conflict_on_scalar_disagreement(tmp_path: Path) -> None:
    """v1 sets clan_name=姬; v2 sets clan_name=姚 at similar confidence → Conflict row."""
    corpus, canonical = _seed_corpus(tmp_path)

    # v1: clan_name=姬
    f1 = tmp_path / "v1.yaml"
    _write(
        f1,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "clan_name": "姬",
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [0, 2],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳", "clan_name": "重耳"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f1,
        prompt_version="v1",
        pipeline_run_id="run:v1",
    )
    load_candidate_persons(canonical, "run:v1")

    # v2: clan_name=姚 (disagreement at similar confidence)
    f2 = tmp_path / "v2.yaml"
    _write(
        f2,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "clan_name": "姚",
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [2, 4],
                        "quote": "奔狄",
                    },
                    "justifications": {"canonical_name": "奔狄", "clan_name": "奔狄"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f2,
        prompt_version="v2",
        pipeline_run_id="run:v2",
    )
    load_candidate_persons(canonical, "run:v2")

    # Conflict emitted for clan_name disagreement
    conflicts = canonical.execute(
        "SELECT subject_kind, field FROM conflicts WHERE field = 'clan_name'"
    ).fetchall()
    assert len(conflicts) >= 1


def _seed_corpus_two_chunks(
    tmp_path: Path,
) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    """Seed corpus with two chunks so each run can reference a distinct chunk."""
    corpus = open_corpus_db(tmp_path / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "changjuan.sqlite")
    corpus.execute(_DOC_INSERT, ("重耳奔狄晋公子",))
    corpus.execute(_CHUNK_INSERT, ("chk:1", 1, 1, "重耳奔狄", "h1"))
    corpus.execute(_CHUNK_INSERT, ("chk:2", 1, 2, "晋公子重耳", "h2"))
    corpus.commit()
    return corpus, canonical


def test_re_extract_accumulates_citations(tmp_path: Path) -> None:
    """Two runs citing different chunks → both citations in entity_citations."""
    corpus, canonical = _seed_corpus_two_chunks(tmp_path)

    # v1 cites chk:1
    f1 = tmp_path / "v1.yaml"
    _write(
        f1,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [0, 2],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f1,
        prompt_version="v1",
        pipeline_run_id="run:v1",
    )
    load_candidate_persons(canonical, "run:v1")

    # v2 cites chk:2 (a different chunk)
    f2 = tmp_path / "v2.yaml"
    _write(
        f2,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "citation": {
                        "chunk_id": "chk:2",
                        "paragraph": 2,
                        "span": [2, 4],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f2,
        prompt_version="v2",
        pipeline_run_id="run:v2",
    )
    load_candidate_persons(canonical, "run:v2")

    persons = canonical.execute("SELECT id FROM persons").fetchall()
    assert len(persons) == 1
    person_id = persons[0][0]

    n_citations = canonical.execute(
        "SELECT COUNT(*) FROM entity_citations WHERE entity_kind='person' AND entity_id=?",
        (person_id,),
    ).fetchone()[0]
    assert n_citations >= 2


def test_curated_field_not_silently_overwritten(tmp_path: Path) -> None:
    """A field marked provenance='curated' must not be overwritten by a new auto run.
    Either: Conflict emitted, or skip update silently — but the curated value persists."""
    corpus, canonical = _seed_corpus(tmp_path)

    # v1 creates Person with clan_name=姬
    f1 = tmp_path / "v1.yaml"
    _write(
        f1,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "clan_name": "姬",
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [0, 2],
                        "quote": "重耳",
                    },
                    "justifications": {"canonical_name": "重耳", "clan_name": "重耳"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f1,
        prompt_version="v1",
        pipeline_run_id="run:v1",
    )
    load_candidate_persons(canonical, "run:v1")

    # Curator marks the Person as curated (simulates retrospective curation)
    canonical.execute("UPDATE persons SET provenance='curated' WHERE clan_name='姬'")
    canonical.commit()

    # v2 attempts to set clan_name=姚 at higher confidence
    f2 = tmp_path / "v2.yaml"
    _write(
        f2,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "clan_name": "姚",
                    "citation": {
                        "chunk_id": "chk:1",
                        "paragraph": 1,
                        "span": [2, 4],
                        "quote": "奔狄",
                    },
                    "justifications": {"canonical_name": "奔狄", "clan_name": "奔狄"},
                },
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=f2,
        prompt_version="v2",
        pipeline_run_id="run:v2",
    )
    load_candidate_persons(canonical, "run:v2")

    # Curated value must persist
    row = canonical.execute("SELECT clan_name FROM persons").fetchone()
    assert row[0] == "姬", f"Curated clan_name was silently overwritten to {row[0]!r}"
