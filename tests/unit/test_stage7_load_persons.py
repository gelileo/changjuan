import hashlib
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


def test_load_updates_scalar_when_new_confidence_strictly_higher_by_delta(
    tmp_path: Path,
) -> None:
    """Exercise the > current + _SIMILAR_CONFIDENCE_DELTA branch specifically:

    Scenario 1: new confidence (0.85) > current (0.70) + delta (0.10) → UPDATE
    Scenario 2: new confidence (0.75) ≤ current (0.70) + delta (0.10) → NO UPDATE (Conflict)
    """

    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)

        # Scenario 1: Seed canonical Person with gender=male, confidence=0.70
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 'M', 0.70, 'run:1', 'chk:1', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")

        # Verify initial state: gender='M', confidence=0.70
        row = conn.execute(
            "SELECT gender, confidence FROM persons WHERE canonical_name='重耳';"
        ).fetchone()
        assert row["gender"] == "M"
        assert row["confidence"] == 0.70

        # Load a candidate with gender='F', confidence=0.85
        # 0.85 > 0.70 + 0.10 (0.80) → should UPDATE to 'F'
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:2', '重耳', 'F', 0.85, 'run:2', 'chk:2', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")

        row = conn.execute("SELECT gender FROM persons WHERE canonical_name='重耳';").fetchone()
        assert row["gender"] == "F", "confidence 0.85 > 0.70 + 0.10 should update"

        # Scenario 2: Load a candidate with gender='M', confidence=0.75
        # 0.75 ≤ 0.85 + 0.10 (0.95) → should NOT update, should create Conflict
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:3', '重耳', 'M', 0.75, 'run:3', 'chk:3', 'q3');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:3")

        row = conn.execute("SELECT gender FROM persons WHERE canonical_name='重耳';").fetchone()
        assert row["gender"] == "F", "confidence 0.75 is not > 0.85 + 0.10, should NOT update"

        # Verify a conflict was emitted
        conflicts = list(
            conn.execute("SELECT field, variants_json FROM conflicts WHERE field='gender';")
        )
        assert len(conflicts) == 1, f"expected 1 Conflict for gender, got {len(conflicts)}"

        import json as _json

        variants = _json.loads(conflicts[0]["variants_json"])
        variant_values = {v["value"] for v in variants}
        assert variant_values == {
            "F",
            "M",
        }, f"expected {{F, M}} in variants, got {variant_values}"


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


def test_load_unions_name_variants(tmp_path: Path) -> None:
    """Candidate whose canonical_name is a known variant maps to the existing Person."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Pre-seed Person per:zhong-er with canonical_name 重耳
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:zhong-er', '重耳', 0.9, 'auto');"
        )
        # Pre-seed variant mapping 晋文公 → per:zhong-er
        conn.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind)"
            " VALUES ('pv:1', 'per:zhong-er', '晋文公', '谥号');"
        )
        # Load a candidate with canonical_name 晋文公
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:2', '晋文公', 0.92, 'run:2', 'chk:2', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        rows = list(conn.execute("SELECT id, canonical_name FROM persons;"))
        variants = list(
            conn.execute(
                "SELECT variant, kind FROM person_variants WHERE person_id='per:zhong-er';"
            )
        )
    # Still one Person; 晋文公 was already a variant; no duplicate should be created.
    assert len(rows) == 1
    assert any(v["variant"] == "晋文公" for v in variants)


def test_load_slug_collision_guard(tmp_path: Path) -> None:
    """When a new candidate's slug collides with an existing Person id, the loader
    must append a hash suffix to the new id instead of crashing on PRIMARY KEY violation."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Pre-seed a Person whose id is per:foo (canonical_name 'alpha' ≠ 'beta')
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:foo', 'alpha', 0.9, 'auto');"
        )
        # Craft a candidate_persons row whose canonical_name slugifies to 'foo'
        # so _slugify('foo-candidate') -> 'foo-candidate', but we use canonical_name='foo'
        # which slugifies to exactly 'foo', producing id 'per:foo' — the collision.
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:c1', 'foo', 0.8, 'run:1', 'chk:1', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        persons = {
            r["id"]: r["canonical_name"]
            for r in conn.execute("SELECT id, canonical_name FROM persons;")
        }

    # Still exactly two Persons (not a crash, not a collision)
    assert len(persons) == 2, f"expected 2 persons, got {persons}"
    assert "per:foo" in persons
    assert persons["per:foo"] == "alpha"
    # The new person must carry the hash-suffixed id
    expected_hash = hashlib.sha256(b"foo").hexdigest()[:6]
    expected_id = f"per:foo-{expected_hash}"
    assert expected_id in persons, f"expected '{expected_id}' in {list(persons)}"
    assert persons[expected_id] == "foo"


def test_merge_uses_per_field_confidence_from_audit_log(tmp_path: Path) -> None:
    """_merge_scalar_fields must consult audit_log for per-field confidence, not just the
    stale row-level confidence. Scenario: Run1 creates Person (confidence 0.5), Run2 sets
    gender='M' with confidence 0.9 (audit_log records 0.9), Run3 proposes gender='F' with
    confidence 0.7 — should emit a Conflict (0.7 < 0.9 + 0.1), not silently overwrite.
    """
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Run 1: create Person with confidence 0.5, no gender
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:r1', '重耳', 0.5, 'run:1', 'chk:1', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Run 2: same name, gender='M', confidence 0.9 → sets gender, audit_log records 0.9
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:r2', '重耳', 'M', 0.9, 'run:2', 'chk:2', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        # Verify gender was set to 'M' and audit_log has confidence 0.9 for it
        gender_after_run2 = conn.execute(
            "SELECT gender FROM persons WHERE canonical_name='重耳';"
        ).fetchone()["gender"]
        assert gender_after_run2 == "M", "pre-condition: Run2 must set gender='M'"
        # Run 3: same name, gender='F', confidence 0.7 → 0.7 < 0.9 + 0.1 → Conflict, NOT update
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:r3', '重耳', 'F', 0.7, 'run:3', 'chk:3', 'q3');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:3")
        gender_final = conn.execute(
            "SELECT gender FROM persons WHERE canonical_name='重耳';"
        ).fetchone()["gender"]
        conflicts = list(
            conn.execute("SELECT field, variants_json FROM conflicts WHERE field='gender';")
        )

    import json as _json

    assert gender_final == "M", "gender must remain 'M'; Run3 confidence 0.7 is not > 0.9 + 0.1"
    assert len(conflicts) == 1, f"expected 1 Conflict for gender, got {conflicts}"
    variants = _json.loads(conflicts[0]["variants_json"])
    variant_values = {v["value"] for v in variants}
    assert variant_values == {"M", "F"}, f"expected {{M, F}} in variants, got {variant_values}"
    confidences = {v["confidence"] for v in variants}
    assert 0.9 in confidences, f"expected 0.9 (audit_log per-field confidence) in {confidences}"


def test_merge_json_field_same_content_different_key_order_no_conflict(tmp_path: Path) -> None:
    """Two JSON strings with the same content but different key orderings must not produce
    a spurious Conflict or audit-log set-event for *_json fields."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Create Person via direct insert (not load) to set birth_date_json with one key order
        conn.execute(
            "INSERT INTO persons"
            " (id, canonical_name, birth_date_json, confidence, provenance)"
            " VALUES ('per:zhong-er', '重耳',"
            ' \'{"year_bce": 632, "uncertainty": "point"}\', 0.9, \'auto\');'
        )
        # Load a candidate with same JSON content but different key order
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, birth_date_json, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳',"
            ' \'{"uncertainty": "point", "year_bce": 632}\','
            " 0.85, 'run:1', 'chk:1', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        conflicts = list(conn.execute("SELECT field FROM conflicts WHERE field='birth_date_json';"))
        set_events = list(
            conn.execute(
                "SELECT field FROM audit_log"
                " WHERE change_kind='set' AND field='birth_date_json';"
            )
        )

    assert conflicts == [], "same JSON content with different key order must not produce a Conflict"
    assert (
        set_events == []
    ), "same JSON content with different key order must not produce a set audit-log event"


def test_load_propagates_social_category_on_create(tmp_path: Path) -> None:
    """Regression: candidate's social_category must land on the canonical person.

    The original loader omitted `social_category` from both the SELECT and the
    INSERT, so canonical `persons.social_category` was always NULL despite
    extractions setting it on every candidate. Surfaced by Ch.6 smoke audit.
    """
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, social_category, confidence,"
            "  pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 'royalty', 0.95, 'run:1',"
            "  'chk:dzl:1:0', 'fixture quote');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        row = conn.execute(
            "SELECT social_category FROM persons WHERE canonical_name='重耳';"
        ).fetchone()
    assert row is not None
    assert row["social_category"] == "royalty"


def test_load_fills_null_social_category_on_merge(tmp_path: Path) -> None:
    """A later candidate with social_category set must backfill a NULL on the
    existing canonical row (same null-fill rule as gender / state_id)."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # First load: candidate without social_category
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second load: candidate with social_category populated
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, social_category, confidence,"
            "  pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:2', '重耳', 'royalty', 0.92, 'run:2',"
            "  'chk:dzl:1:5', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        row = conn.execute(
            "SELECT social_category FROM persons WHERE canonical_name='重耳';"
        ).fetchone()
    assert row["social_category"] == "royalty"
