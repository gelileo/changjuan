"""scripts/check-extraction — read-only validator for stage-3 YAML.

Invoked as a subprocess (matching how the skill calls it) so the test exercises
the real CLI surface, not just the helper function. Covers a clean pass and
two of the most common failure modes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from pipeline.db import open_corpus_db

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-extraction"


@pytest.fixture
def tiny_corpus(tmp_path: Path) -> Path:
    """A throwaway corpus DB with one chunk; returned path."""
    corpus_path = tmp_path / "corpus.sqlite"
    corpus = open_corpus_db(corpus_path)
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
    corpus.close()
    return corpus_path


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def _run(yaml_path: Path, corpus_db: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), str(yaml_path), "--db", str(corpus_db)],
        capture_output=True,
        text=True,
    )


def test_clean_yaml_exits_zero(tiny_corpus: Path, tmp_path: Path) -> None:
    f = tmp_path / "extract.yaml"
    _write_yaml(
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
                        "quote": "重耳奔狄",
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
    result = _run(f, tiny_corpus)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout.lower()


def test_justification_not_in_quote_reports_error(tiny_corpus: Path, tmp_path: Path) -> None:
    """The Ch.6 failure mode: justification value points to text outside the quote."""
    f = tmp_path / "extract.yaml"
    _write_yaml(
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
                    # "奔狄" is in the chunk but NOT in the quote — this should fail.
                    "justifications": {"canonical_name": "奔狄"},
                }
            ],
            "events": [],
            "places": [],
            "states": [],
            "relations": [],
        },
    )
    result = _run(f, tiny_corpus)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "justification" in result.stdout
    assert "not substring of citation.quote" in result.stdout


def test_quote_not_in_chunk_reports_error(tiny_corpus: Path, tmp_path: Path) -> None:
    """The other Ch.6 failure mode: paraphrased / ellipsis-laden quote."""
    f = tmp_path / "extract.yaml"
    _write_yaml(
        f,
        {
            "persons": [
                {
                    "id": "p1",
                    "canonical_name": "重耳",
                    "citation": {
                        "chunk_id": "chk:ch01-001",
                        "paragraph": 1,
                        "span": [0, 6],
                        # Adds an ellipsis that's not in the chunk text "重耳奔狄"
                        "quote": "重耳……奔狄",
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
    result = _run(f, tiny_corpus)
    assert result.returncode == 1
    assert "verbatim-quote invariant failed" in result.stdout
