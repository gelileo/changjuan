"""End-to-end: ch01 extraction YAML produces non-empty candidate_person_relations.

Phase 6 Track C: the stage3 loader previously read r["relation_kind"], which the
extractor does not emit. The actual field is kind_detail. After the fix, replaying
the extraction populates candidate_person_relations with real kinds (which stage 7
can then promote).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTION = REPO_ROOT / "data" / "extractions" / "ch01" / "extract-v2.yaml"
CORPUS = REPO_ROOT / "data" / "corpus.sqlite"


@pytest.mark.skipif(
    not (EXTRACTION.exists() and CORPUS.exists()),
    reason="ch01 extraction YAML or corpus.sqlite missing",
)
def test_kind_detail_populates_candidate_person_relations(tmp_path: Path) -> None:
    canonical_db = tmp_path / "canonical.sqlite"
    canonical = open_canonical_db(canonical_db)
    corpus = open_corpus_db(CORPUS)
    run_id = "run:test-c1"
    try:
        load_extraction(
            canonical,
            corpus_conn=corpus,
            chapter_num=1,
            extraction_file=EXTRACTION,
            prompt_version="v2",
            pipeline_run_id=run_id,
        )
        canonical.commit()

        rows = canonical.execute(
            "SELECT kind FROM candidate_person_relations WHERE pipeline_run_id = ?",
            (run_id,),
        ).fetchall()
    finally:
        canonical.close()
        corpus.close()

    assert rows, "no candidate_person_relations rows produced"
    kinds = {r[0] for r in rows}
    expected_subset = {"parent", "ally", "mentor", "spouse", "killed_by"}
    assert kinds & expected_subset, f"expected one of {expected_subset}; got {kinds}"
    assert "" not in kinds, "empty kind leaked through"
