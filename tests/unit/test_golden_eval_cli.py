"""golden-eval CLI verb: load golden + most-recent extract-load run, compute P/R, gate on
thresholds."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pipeline.cli import app


def _seed_minimal(tmp_path: Path) -> None:
    from pipeline.db import open_canonical_db, open_corpus_db

    (tmp_path / "data").mkdir()
    corpus = open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    corpus.execute(
        "INSERT INTO documents "
        "(id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at) "
        "VALUES (1, 'dongzhoulieguozhi', 't', 1, 'ch1', '...', 'test', datetime('now'))"
    )
    corpus.execute(
        "INSERT INTO chunks (id, document_id, paragraph_start, paragraph_end, text, hash) "
        "VALUES ('chk:ch01-001', 1, 1, 1, '重耳', 'h')"
    )
    corpus.commit()

    # Record a pipeline_runs row from a (synthetic) extract-load run
    canonical.execute(
        "INSERT INTO pipeline_runs (id, stage, started_at, ended_at, prompt_version, model, "
        "scope_json, stats_json, stats_schema_version) "
        "VALUES (?, 'extract-load', datetime('now'), datetime('now'), "
        "'v1', 'claude-code', ?, ?, 1)",
        ("run:test", json.dumps({"chapter": 1}), json.dumps({})),
    )
    canonical.commit()


def _write_golden(tmp_path: Path) -> None:
    """Write a minimal golden directory with one person record."""
    g = tmp_path / "tests" / "golden" / "ch01"
    g.mkdir(parents=True)
    (g / "citations.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "cit:1",
                    "chunk_id": "chk:ch01-001",
                    "paragraph": 1,
                    "span": [0, 2],
                    "quote": "重耳",
                },
            ]
        ),
        encoding="utf-8",
    )
    (g / "persons.yaml").write_text(
        yaml.safe_dump(
            [
                {"id": "per:zhong-er", "canonical_name": "重耳", "citations": ["cit:1"]},
            ]
        ),
        encoding="utf-8",
    )
    for name in ("events", "places", "states", "relations"):
        (g / f"{name}.yaml").write_text(yaml.safe_dump([]), encoding="utf-8")


def test_golden_eval_with_no_candidates_reports_recall_zero(
    tmp_path: Path, monkeypatch: object
) -> None:
    _seed_minimal(tmp_path)
    _write_golden(tmp_path)

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    runner = CliRunner()
    result = runner.invoke(app, ["golden-eval", "--chapter", "1", "--repo-root", str(tmp_path)])
    # Below threshold → non-zero
    assert result.exit_code != 0, result.stdout
    assert "person" in result.stdout
    # Recall should be 0 (no candidates loaded), triggering ✗
    assert "✗" in result.stdout


def test_golden_eval_with_matching_candidate_passes(tmp_path: Path, monkeypatch: object) -> None:
    _seed_minimal(tmp_path)
    _write_golden(tmp_path)

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    # Seed a matching candidate_persons row tagged with run:test
    from pipeline.db import open_canonical_db

    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    # candidate_persons columns: id, canonical_name, gender, birth_date_json,
    # death_date_json, notes, state_id, clan_name, social_category, confidence,
    # pipeline_run_id, chunk_id, quote, created_at
    canonical.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
        "VALUES ('cp:1', '重耳', 0.9, 'run:test', 'chk:ch01-001', '重耳')"
    )
    canonical.commit()

    runner = CliRunner()
    result = runner.invoke(app, ["golden-eval", "--chapter", "1", "--repo-root", str(tmp_path)])
    # 1/1 person matches → precision=1.0 recall=1.0 → both above thresholds.
    # Other kinds: all empty golden + empty candidates → 1.0/1.0 by convention.
    assert result.exit_code == 0, result.stdout
    assert "person" in result.stdout
    assert "✓" in result.stdout
