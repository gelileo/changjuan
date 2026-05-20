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


def test_load_updates_scalar_when_new_confidence_higher(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # First load: gender unset
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', NULL, 0.5, 'run:1', 'chk:dzl:1:0', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second load: gender='M', higher confidence
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:2', '重耳', 'M', 0.9, 'run:2', 'chk:dzl:1:5', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        row = conn.execute("SELECT gender FROM persons WHERE canonical_name='重耳';").fetchone()
    assert row["gender"] == "M"


def test_load_does_not_overwrite_curated(tmp_path: Path) -> None:
    """Curated Person: re-extraction must not silently overwrite any field."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Pre-seed a curated Person
        conn.execute(
            "INSERT INTO persons (id, canonical_name, gender, confidence, provenance) "
            "VALUES ('per:zhong-er', '重耳', 'F', 0.99, 'curated');"
        )
        # New extraction proposes a different gender
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 'M', 0.95, 'run:1', 'chk:1', 'q');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        gender = conn.execute("SELECT gender FROM persons WHERE canonical_name='重耳';").fetchone()[
            "gender"
        ]
        conflicts = list(conn.execute("SELECT subject_id, field FROM conflicts;"))
    assert gender == "F", "curated value must not be silently overwritten"
    assert len(conflicts) == 1
    assert conflicts[0]["field"] == "gender"


def test_load_emits_conflict_on_disagreement_at_similar_confidence(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 'M', 0.85, 'run:1', 'chk:1', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second extraction disagrees, similar confidence
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:2', '重耳', 'F', 0.83, 'run:2', 'chk:2', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        conflicts = list(
            conn.execute("SELECT field, variants_json, current_best_variant_idx FROM conflicts;")
        )
    assert len(conflicts) == 1
    import json as _json

    variants = _json.loads(conflicts[0]["variants_json"])
    assert {"M", "F"} == {v["value"] for v in variants}
