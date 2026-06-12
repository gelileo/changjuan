import sqlite3
from pathlib import Path

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def _conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    return c


def _tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_theme_tables_exist():
    c = _conn()
    assert {"themes", "theme_occurrences", "candidate_themes"} <= _tables(c)


def test_theme_occurrence_insert_and_entity_citation_theme_kind():
    c = _conn()
    c.execute(
        "INSERT INTO themes (id,name,confidence,provenance) VALUES ('thm:命运','命运',0.9,'auto')"
    )
    c.execute(
        "INSERT INTO persons (id,canonical_name,confidence,provenance) "
        "VALUES ('per:黛玉','林黛玉',0.9,'auto')"
    )
    c.execute(
        "INSERT INTO theme_occurrences (theme_id,entity_kind,entity_id,confidence,provenance) "
        "VALUES ('thm:命运','person','per:黛玉',0.9,'auto')"
    )
    c.execute(
        "INSERT INTO entity_citations (entity_kind,entity_id,citation_id) "
        "VALUES ('theme','thm:命运','cit:1')"
    )


def test_candidate_themes_columns():
    c = _conn()
    cols = {r[1] for r in c.execute("PRAGMA table_info(candidate_themes)")}
    assert {
        "id",
        "name",
        "description",
        "occurrences_json",
        "confidence",
        "pipeline_run_id",
        "chunk_id",
        "quote",
    } <= cols
