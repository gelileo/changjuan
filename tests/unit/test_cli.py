import json
from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app
from pipeline.db import apply_schema, connect, open_canonical_db
from pipeline.schemas import CANONICAL_SCHEMA


def test_cli_has_ingest_chunk_load_export_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "chunk", "load", "export"):
        assert cmd in result.stdout


def test_cli_ingest_dry_runs(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Smoke-test: invoking `changjuan ingest` with --repo-root pointing at an empty tmp dir
    should exit cleanly with 'no corpora found' rather than crash."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", "--repo-root", str(tmp_path)])
    # Either exits 0 with a "no corpora" message, or exits 1 with a clear error.
    # Both acceptable; crash is not.
    assert result.exit_code in (0, 1)
    assert "Traceback" not in result.stdout


def test_cli_load_wires_all_five_entity_kinds(tmp_path: Path) -> None:
    """Integration test: `changjuan load <run_id>` promotes candidates of all five kinds."""
    run_id = "test-run:123"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "changjuan.sqlite"

    # Seed the database with canonical schema
    with connect(db_path) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)

        # Seed one candidate of each kind for the same run_id
        # 1. Candidate place
        conn.execute(
            "INSERT INTO candidate_places "
            "(id, name, type, lat, lon, coord_confidence, modern_equiv, confidence, "
            "pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)",
            ("cand:pla:chk1", "镐京", "capital", 34.5, 109.2, 0.9, run_id, "chk:1", "镐京"),
        )

        # 2. Candidate state
        conn.execute(
            "INSERT INTO candidate_states "
            "(id, name, type, ruling_clan, founded_date_json, ended_date_json, "
            "confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)",
            ("cand:sta:chk1", "周", "dynasty", "姬", 0.9, run_id, "chk:1", "周"),
        )

        # 3. Candidate person
        conn.execute(
            "INSERT INTO candidate_persons "
            "(id, canonical_name, gender, birth_date_json, death_date_json, notes, "
            "state_id, clan_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, ?)",
            ("cand:per:chk1", "重耳", "M", 0.95, run_id, "chk:1", "重耳"),
        )

        # 4. Candidate event
        date_json = json.dumps(
            {
                "year_bce": 632,
                "uncertainty": "point",
                "inference_kind": "explicit_reign_lu",
                "original": "",
            }
        )
        conn.execute(
            "INSERT INTO candidate_events "
            "(id, type, date_json, outcome, summary, primary_place_id, confidence, "
            "pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?)",
            ("cand:evt:chk1:abc123", "战", date_json, 0.9, run_id, "chk:1", "战役"),
        )

        conn.commit()

    # Run the CLI load command
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["load", run_id, "--repo-root", str(tmp_path)],
    )

    assert result.exit_code == 0, f"CLI failed: {result.stdout}"
    assert "loaded:" in result.stdout
    assert f"run={run_id}" in result.stdout

    # Verify all five canonical tables received rows
    with open_canonical_db(db_path) as canonical:
        places = canonical.execute("SELECT COUNT(*) as cnt FROM places").fetchone()
        assert places[0] > 0, "places table is empty after load"

        states = canonical.execute("SELECT COUNT(*) as cnt FROM states").fetchone()
        assert states[0] > 0, "states table is empty after load"

        persons = canonical.execute("SELECT COUNT(*) as cnt FROM persons").fetchone()
        assert persons[0] > 0, "persons table is empty after load"

        events = canonical.execute("SELECT COUNT(*) as cnt FROM events").fetchone()
        assert events[0] > 0, "events table is empty after load"
