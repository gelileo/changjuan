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
        tmp_path / "data" / "books" / "dzl" / "corpus.sqlite"
    )  # ensure corpus exists (may be needed by some paths)
    canonical = open_canonical_db(tmp_path / "data" / "books" / "dzl" / "canonical.sqlite")
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

    canonical = sqlite3.connect(tmp_path / "data" / "books" / "dzl" / "canonical.sqlite")
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

    canonical = sqlite3.connect(tmp_path / "data" / "books" / "dzl" / "canonical.sqlite")
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


def test_backfill_narrative_dates_fills_and_audits(tmp_path: Path) -> None:
    canonical = _seed(tmp_path)
    # Give both events a narrative position in the same chapter; the dated anchor
    # (771) sits at an earlier paragraph than the undated relative event.
    canonical.executemany(
        "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) VALUES ('event',?,?)",
        [("evt:anchor", "chk:dzl:7:3"), ("evt:rel", "chk:dzl:7:5")],
    )
    canonical.commit()

    result = CliRunner().invoke(app, ["backfill-narrative-dates", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr

    db = open_canonical_db(tmp_path / "data" / "books" / "dzl" / "canonical.sqlite")
    rel = json.loads(db.execute("SELECT date_json FROM events WHERE id='evt:rel'").fetchone()[0])
    assert rel["year_bce"] == 771  # inherits the nearest prior dated event
    assert rel["relative_anchor_event_id"] == "evt:anchor"
    assert rel["narrative_inferred"] is True
    # Regression guard for the audit_log change_kind CHECK constraint: a valid
    # 'set' row is written (an invalid kind raised IntegrityError before the fix).
    n = db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_id='evt:rel' AND change_kind='set'"
    ).fetchone()[0]
    assert n == 1
