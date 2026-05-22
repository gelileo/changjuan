"""End-to-end: load the recorded extraction fixture + golden YAML, run P/R,
assert thresholds from pipeline/config.py."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from pipeline import config
from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction
from tests.golden.loader import load_golden
from tests.golden.precision_recall import compute_pr

pytestmark = pytest.mark.golden


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _build_candidates(
    canonical: sqlite3.Connection, run_id: str
) -> dict[str, list[dict[str, object]]]:
    """Mirror golden_eval_cmd's logic. Convert candidate_* rows into the dict
    shape compute_pr expects. Includes chunk-local id suffix extraction
    (split(':')[-1])."""
    persons = []
    for row in canonical.execute(
        "SELECT id, canonical_name, state_id, social_category FROM candidate_persons "
        "WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        persons.append(
            {
                "id": row[0].split(":")[-1],
                "canonical_name": row[1],
                "state_id": row[2],
                "social_category": row[3],
                "variants": [],
            }
        )
    events = []
    for row in canonical.execute(
        "SELECT id, type, date_json, primary_place_id FROM candidate_events "
        "WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        date = json.loads(row[2]) if row[2] else {}
        events.append(
            {
                "id": row[0].split(":")[-1],
                "type": row[1],
                "date": {"year_bce": date.get("year_bce")} if date else {},
                "primary_place_id": row[3],
            }
        )
    places = []
    for row in canonical.execute(
        "SELECT id, name FROM candidate_places WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        places.append({"id": row[0].split(":")[-1], "name": row[1]})
    states = []
    for row in canonical.execute(
        "SELECT id, name FROM candidate_states WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        states.append({"id": row[0].split(":")[-1], "name": row[1]})

    relations: list[dict[str, object]] = []

    def _cl(full_id: str | None) -> str | None:
        return full_id.split(":")[-1] if full_id else None

    for row in canonical.execute(
        "SELECT candidate_event_id, candidate_person_id, role FROM candidate_event_participants "
        "WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        relations.append(
            {
                "kind": "event_participant",
                "event_id": _cl(row[0]),
                "person_id": _cl(row[1]),
                "role": row[2],
            }
        )
    for row in canonical.execute(
        "SELECT candidate_event_id, candidate_place_id, role FROM candidate_event_places "
        "WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        relations.append(
            {
                "kind": "event_place",
                "event_id": _cl(row[0]),
                "place_id": _cl(row[1]),
                "role": row[2],
            }
        )
    for row in canonical.execute(
        "SELECT from_candidate_event_id, to_candidate_event_id, kind "
        "FROM candidate_event_relations WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        relations.append({"kind": row[2], "from_event_id": _cl(row[0]), "to_event_id": _cl(row[1])})
    for row in canonical.execute(
        "SELECT from_candidate_person_id, to_candidate_person_id, kind "
        "FROM candidate_person_relations WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        relations.append(
            {"kind": row[2], "from_person_id": _cl(row[0]), "to_person_id": _cl(row[1])}
        )
    for row in canonical.execute(
        "SELECT candidate_person_id, candidate_state_id, role FROM candidate_person_states "
        "WHERE pipeline_run_id = ?",
        (run_id,),
    ):
        relations.append(
            {
                "kind": "person_state",
                "person_id": _cl(row[0]),
                "state_id": _cl(row[1]),
                "role": row[2],
            }
        )

    return {
        "persons": persons,
        "events": events,
        "places": places,
        "states": states,
        "relations": relations,
    }


def test_golden_ch01_meets_thresholds(tmp_path: Path) -> None:
    """The committed fixture (tests/fixtures/ch01-extraction-v1.yaml) is the v2
    extraction output. Loading it and comparing to golden Ch.1 must pass all 5
    kinds' thresholds in pipeline/config.GOLDEN_PR_THRESHOLDS."""
    # Set up temp dirs
    (tmp_path / "data").mkdir()
    # Copy the real corpus.sqlite so Ch.1 chunks exist for the loader to validate against
    src_corpus = REPO_ROOT / "data" / "corpus.sqlite"
    if not src_corpus.exists():
        pytest.skip(
            f"corpus.sqlite not present at {src_corpus} — "
            "run `changjuan ingest && changjuan chunk` first"
        )
    shutil.copyfile(src_corpus, tmp_path / "data" / "corpus.sqlite")

    corpus = open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")

    # Load the frozen fixture as a new pipeline_run_id
    fixture = REPO_ROOT / "tests" / "fixtures" / "ch01-extraction-v1.yaml"
    assert fixture.exists(), f"fixture missing: {fixture}"
    load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=1,
        extraction_file=fixture,
        prompt_version="v1",
        pipeline_run_id="run:integration-test",
    )

    # Build candidate set + golden
    candidates = _build_candidates(canonical, "run:integration-test")
    golden = load_golden(REPO_ROOT / "tests" / "golden" / "ch01")

    # Compute + assert thresholds
    report = compute_pr(golden, candidates)
    failures = []
    for kind, scores in report["per_entity_type"].items():
        target = config.GOLDEN_PR_THRESHOLDS[kind]
        if scores["precision"] < target["precision"]:
            failures.append(f"{kind}: precision {scores['precision']:.4f} < {target['precision']}")
        if scores["recall"] < target["recall"]:
            failures.append(f"{kind}: recall {scores['recall']:.4f} < {target['recall']}")
    assert not failures, "\n".join(failures)
