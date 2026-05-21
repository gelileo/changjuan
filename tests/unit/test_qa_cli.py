"""qa-sample + qa-load CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pipeline.cli import app


def _seed_corpus(tmp_path: Path) -> sqlite3.Connection:
    from pipeline.db import open_canonical_db, open_corpus_db

    (tmp_path / "data").mkdir()
    open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    return canonical


def test_qa_sample_emits_yaml_with_triples(tmp_path: Path) -> None:
    canonical = _seed_corpus(tmp_path)
    # Seed at least one candidate_persons row — fallback path enumerates scalar
    # facts directly from candidate_persons when candidate_facts is unpopulated.
    canonical.execute(
        "INSERT INTO candidate_persons (id, canonical_name, gender, social_category, "
        " chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES ('cand:per:1', '重耳', 'male', 'royalty', 'chk:1', '重耳', 0.9, 'run:1')"
    )
    canonical.commit()

    runner = CliRunner()
    result = runner.invoke(app, ["qa-sample", "run:1", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = yaml.safe_load(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 1


def test_qa_load_writes_qa_samples_and_updates_stats(tmp_path: Path) -> None:
    canonical = _seed_corpus(tmp_path)
    canonical.execute(
        "INSERT INTO pipeline_runs (id, stage, started_at, ended_at, prompt_version, "
        "model, scope_json, stats_json, stats_schema_version) "
        "VALUES ('run:1', 'extract-load', datetime('now'), datetime('now'), 'v1', "
        "'claude-code', '{}', '{}', 1)"
    )
    canonical.commit()

    qa_file = tmp_path / "qa.yaml"
    qa_file.write_text(
        yaml.safe_dump(
            [
                {
                    "record_kind": "person",
                    "record_id": "cand:per:1",
                    "field": "canonical_name",
                    "verdict": "yes",
                    "reason": "ok",
                },
                {
                    "record_kind": "person",
                    "record_id": "cand:per:2",
                    "field": "canonical_name",
                    "verdict": "no",
                    "reason": "off",
                },
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "qa-load",
            "--run-id",
            "run:1",
            "--qa-file",
            str(qa_file),
            "--repo-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    rows = canonical.execute(
        "SELECT verdict FROM qa_samples WHERE pipeline_run_id='run:1'"
    ).fetchall()
    assert sorted(r[0] for r in rows) == ["no", "yes"]

    stats_row = canonical.execute(
        "SELECT stats_json FROM pipeline_runs WHERE id='run:1'"
    ).fetchone()
    stats = json.loads(stats_row[0])
    assert stats["claim_defensible_sample"]["sample_size"] == 2
    assert stats["claim_defensible_sample"]["yes"] == 1
    assert stats["claim_defensible_sample"]["no"] == 1


def test_qa_load_breaches_threshold_when_mismatch_high(tmp_path: Path) -> None:
    canonical = _seed_corpus(tmp_path)
    canonical.execute(
        "INSERT INTO pipeline_runs (id, stage, started_at, ended_at, prompt_version, "
        "model, scope_json, stats_json, stats_schema_version) "
        "VALUES ('run:bad', 'extract-load', datetime('now'), datetime('now'), 'v1', "
        "'claude-code', '{}', '{}', 1)"
    )
    canonical.commit()
    qa_file = tmp_path / "qa.yaml"
    # 4 no verdicts out of 4 = 1.0 mismatch rate > 0.10 threshold
    qa_file.write_text(
        yaml.safe_dump(
            [
                {
                    "record_kind": "person",
                    "record_id": f"r{i}",
                    "field": "f",
                    "verdict": "no",
                    "reason": "x",
                }
                for i in range(4)
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "qa-load",
            "--run-id",
            "run:bad",
            "--qa-file",
            str(qa_file),
            "--repo-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout

    stats_row = canonical.execute(
        "SELECT stats_json FROM pipeline_runs WHERE id='run:bad'"
    ).fetchone()
    stats = json.loads(stats_row[0])
    assert "claim_defensible_mismatch_rate" in stats.get("thresholds_breached", [])
