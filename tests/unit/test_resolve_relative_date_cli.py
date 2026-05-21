"""list-unresolved-dates + resolve-relative-date CLI verbs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app
from pipeline.db import open_canonical_db, open_corpus_db


def _seed(tmp_path: Path) -> sqlite3.Connection:
    # ensure data/ dir exists relative to tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    open_corpus_db(
        tmp_path / "data" / "corpus.sqlite"
    )  # ensure corpus exists (may be needed by some paths)
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    # one anchored event
    canonical.execute(
        "INSERT INTO events (id, type, date_json, provenance, confidence, pipeline_run_id) "
        "VALUES ('evt:anchor', '攻陷', "
        '\'{"year_bce": 771, "inference_kind": "explicit_reign_zhou", '
        '"original": "周幽王十一年", "uncertainty": "point"}\', '
        "'auto', 0.9, 'run:test')"
    )
    # one unresolved relative
    canonical.execute(
        "INSERT INTO events (id, type, date_json, provenance, confidence, pipeline_run_id) "
        "VALUES ('evt:rel', '盟会', "
        '\'{"year_bce": null, "inference_kind": "relative_to_prior_event", '
        '"original": "明年", "uncertainty": "point"}\', '
        "'auto', 0.7, 'run:test')"
    )
    canonical.commit()
    return canonical


def test_list_unresolved_shows_dangling_relatives(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["list-unresolved-dates", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert "evt:rel" in result.stdout
    assert "evt:anchor" not in result.stdout


def test_resolve_relative_date_sets_anchor_and_recomputes(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "resolve-relative-date",
            "--repo-root",
            str(tmp_path),
            "--event-id",
            "evt:rel",
            "--anchor-event-id",
            "evt:anchor",
        ],
    )
    assert result.exit_code == 0, result.stdout

    canonical = sqlite3.connect(tmp_path / "data" / "changjuan.sqlite")
    row = canonical.execute("SELECT date_json FROM events WHERE id = 'evt:rel'").fetchone()
    date = json.loads(row[0])
    assert date["year_bce"] == 770  # 771 + (-1)
    assert date["relative_anchor_event_id"] == "evt:anchor"

    # audit_log entry
    n = canonical.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_id = 'evt:rel' AND actor LIKE 'curator:%'"
    ).fetchone()[0]
    assert n == 1


def test_resolve_with_explicit_offset_unknown_token(tmp_path: Path) -> None:
    canonical = _seed(tmp_path)
    canonical.execute(
        "UPDATE events "
        "SET date_json = json_set(date_json, '$.original', '其后五年') "
        "WHERE id = 'evt:rel'"
    )
    canonical.commit()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "resolve-relative-date",
            "--repo-root",
            str(tmp_path),
            "--event-id",
            "evt:rel",
            "--anchor-event-id",
            "evt:anchor",
            "--offset",
            "5",
        ],
    )
    assert result.exit_code == 0, result.stdout

    canonical = sqlite3.connect(tmp_path / "data" / "changjuan.sqlite")
    row = canonical.execute(
        "SELECT json_extract(date_json, '$.year_bce') FROM events WHERE id = 'evt:rel'"
    ).fetchone()
    assert row[0] == 766  # 771 + (-5)


def test_resolve_dangling_anchor_errors(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "resolve-relative-date",
            "--repo-root",
            str(tmp_path),
            "--event-id",
            "evt:rel",
            "--anchor-event-id",
            "evt:nope",
        ],
    )
    assert result.exit_code != 0
    output = (result.stdout + result.stderr).lower()
    assert "not found" in output or "dangling" in output
