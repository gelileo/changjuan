from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage7_load import load_candidate_persons


def test_load_new_person_creates_canonical_row(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'fixture quote');"
        )
        n = load_candidate_persons(conn, pipeline_run_id="run:1")
    assert n == 1
    with connect(tmp_path / "changjuan.sqlite") as conn:
        rows = list(conn.execute("SELECT id, canonical_name, provenance FROM persons;"))
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "重耳"
    assert rows[0]["provenance"] == "auto"


def test_load_emits_create_audit_log(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'fixture');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        logs = list(conn.execute("SELECT entity_id, change_kind, actor FROM audit_log;"))
    assert any(r["change_kind"] == "create" and r["actor"].startswith("load@") for r in logs)


def test_load_matches_existing_person_by_canonical_name(tmp_path: Path) -> None:
    """Second candidate with same canonical_name should NOT create a duplicate Person."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # First load
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'fixture');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second load with same canonical name
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:2', '重耳', 0.92, 'run:2', 'chk:dzl:1:5', 'fixture 2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        rows = list(conn.execute("SELECT id, canonical_name FROM persons;"))
    assert len(rows) == 1, f"expected 1 Person, got {len(rows)}: {rows}"
