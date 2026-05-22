"""Smoke checks: per-chapter post-load integrity helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.smoke_checks import smoke_check_run

_INSERT_RUN = (
    "INSERT INTO pipeline_runs "
    "(id, stage, prompt_version, model, scope_json, stats_json, stats_schema_version) "
    "VALUES (?, 'extract-load', 'v2', 'opus', ?, ?, 1)"
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_pipeline_run(conn: sqlite3.Connection, run_id: str, chapter: int) -> None:
    conn.execute(
        _INSERT_RUN,
        (run_id, json.dumps({"chapter": chapter}), json.dumps({"dates_out_of_range": 0})),
    )
    conn.commit()


def test_smoke_check_passes_on_clean_run(conn: sqlite3.Connection) -> None:
    _seed_pipeline_run(conn, "run:ch2", 2)
    conn.execute(
        "INSERT INTO states (id, name, provenance, confidence, pipeline_run_id) "
        "VALUES ('sta:jin', '晋', 'auto', 0.9, 'run:ch2')"
    )
    conn.execute(
        "INSERT INTO persons (id, canonical_name, provenance, confidence, pipeline_run_id) "
        "VALUES ('per:test', '重耳', 'auto', 0.9, 'run:ch2')"
    )
    conn.commit()
    result = smoke_check_run(conn, "run:ch2")
    assert result["status"] == "pass"
    assert result["fk_orphans"] == 0
    assert result["dates_out_of_range"] == 0


def test_smoke_check_fails_when_pipeline_run_missing(conn: sqlite3.Connection) -> None:
    result = smoke_check_run(conn, "run:nonexistent")
    assert result["status"] == "fail"
    assert "no_pipeline_run" in result["failures"]


def test_smoke_check_flags_dates_out_of_range(conn: sqlite3.Connection) -> None:
    conn.execute(
        _INSERT_RUN,
        ("run:ch3", json.dumps({"chapter": 3}), json.dumps({"dates_out_of_range": 2})),
    )
    conn.commit()
    result = smoke_check_run(conn, "run:ch3")
    assert result["dates_out_of_range"] == 2
    assert "dates_out_of_range" in result["warnings"]


def test_smoke_check_runs_without_crash_on_minimal_seed(conn: sqlite3.Connection) -> None:
    """Even with no entities, the check should not crash."""
    _seed_pipeline_run(conn, "run:ch4", 4)
    result = smoke_check_run(conn, "run:ch4")
    assert "fk_orphans" in result
    assert "status" in result
