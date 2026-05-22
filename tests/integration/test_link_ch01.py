"""End-to-end: load the frozen v2 fixture, run linker, then load, assert
exactly 13 canonical persons (Ch.1 golden's count). No false-positive merges
within a single chapter's candidates."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction
from pipeline.stage5_link import link_run
from pipeline.stage7_load import (
    load_candidate_persons,
    load_candidate_places,
    load_candidate_states,
)

pytestmark = pytest.mark.golden


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_link_then_load_ch01_yields_thirteen_canonical_persons(tmp_path: Path) -> None:
    """Run extract-load → link → load on Ch.1's v2 fixture. Expect exactly
    13 canonical persons (the golden Ch.1 count). Zero false-positive merges
    within the chapter's own candidate set."""
    src_corpus = REPO_ROOT / "data" / "corpus.sqlite"
    if not src_corpus.exists():
        pytest.skip(f"corpus.sqlite missing at {src_corpus}")

    (tmp_path / "data").mkdir()
    shutil.copyfile(src_corpus, tmp_path / "data" / "corpus.sqlite")

    corpus = open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")

    fixture = REPO_ROOT / "tests" / "fixtures" / "ch01-extraction-v1.yaml"
    assert fixture.exists()

    # 1) extract-load: writes candidate_* rows
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=fixture,
        prompt_version="v1",
        pipeline_run_id="run:link-ch01-test",
    )

    # 2) link: writes match_target_id on candidates that auto-merge
    stats = link_run(canonical, "run:link-ch01-test")
    # All Ch.1 candidates are distinct persons (golden has 13 separate ids),
    # so within a single run no auto-merges should fire.
    assert stats["auto_merges"] == 0, (
        f"Phase 3 linker should NOT auto-merge any same-chapter Ch.1 candidates "
        f"(all 13 golden persons are distinct). Got {stats['auto_merges']} auto-merges. "
        f"Either the scorer is too aggressive or the candidate pool is wrong."
    )

    # 3) load: places → states → persons (FK order required by the schema)
    load_candidate_places(canonical, "run:link-ch01-test")
    load_candidate_states(canonical, "run:link-ch01-test")
    load_candidate_persons(canonical, "run:link-ch01-test")

    n_persons = canonical.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    assert n_persons == 13, (
        f"Ch.1 golden has 13 distinct persons; got {n_persons} canonical persons "
        f"after link+load. Names:\n"
        + "\n".join(r[0] for r in canonical.execute("SELECT canonical_name FROM persons"))
    )
