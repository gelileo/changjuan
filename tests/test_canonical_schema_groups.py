import sqlite3
from pathlib import Path

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def _conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    return c


def _tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cols(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def test_groups_table_replaces_states():
    c = _conn()
    tables = _tables(c)
    assert "groups" in tables and "states" not in tables
    assert "group_type" in _cols(c, "groups")


def test_person_and_junctions_renamed():
    c = _conn()
    tables = _tables(c)
    assert "group_id" in _cols(c, "persons") and "state_id" not in _cols(c, "persons")
    assert "person_groups" in tables and "person_states" not in tables
    assert "group_seats" in tables and "state_capitals" not in tables
    assert "candidate_groups" in tables and "candidate_states" not in tables
    assert "candidate_person_groups" in tables


def test_person_relations_has_no_kind_check():
    c = _conn()
    c.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES ('per:a','A',0.9,'auto'),('per:b','B',0.9,'auto')"
    )
    c.execute(
        "INSERT INTO person_relations "
        "(from_person_id,to_person_id,kind,confidence,provenance) "
        "VALUES ('per:a','per:b','恋慕',0.9,'auto')"
    )


def test_entity_citations_kind_values():
    import pytest

    c = _conn()
    c.execute(
        "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
        "VALUES ('group','sta:jin','cit:1')"
    )
    c.execute(
        "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
        "VALUES ('group_seat','sta:jin','cit:2')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
            "VALUES ('state','sta:jin','cit:3')"
        )
