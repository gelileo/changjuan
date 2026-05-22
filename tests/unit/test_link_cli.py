"""changjuan link CLI verb tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app
from pipeline.db import open_canonical_db


def test_link_cli_runs_on_empty_run(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    runner = CliRunner()
    result = runner.invoke(app, ["link", "run:empty", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "processed=0" in result.stdout


def test_link_cli_reports_counts(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    # Seed a candidate with no overlap → will be skipped
    canonical.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES ('cand:per:run:1:p1', '孤独人物', 'chk:t', '', 0.9, 'run:1')"
    )
    canonical.commit()
    runner = CliRunner()
    result = runner.invoke(app, ["link", "run:1", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "processed=1" in result.stdout
    assert "skipped=1" in result.stdout
