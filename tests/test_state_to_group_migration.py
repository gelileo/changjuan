import sqlite3

from pipeline.migrations import migrate_0001_state_to_group as migrate

OLD_SCHEMA = """
CREATE TABLE states (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT,
    ruling_clan TEXT, founded_date_json TEXT, ended_date_json TEXT,
    confidence REAL NOT NULL, provenance TEXT NOT NULL, pipeline_run_id TEXT,
    created_at TEXT, updated_at TEXT);
CREATE TABLE persons (id TEXT PRIMARY KEY, canonical_name TEXT, state_id TEXT,
    confidence REAL NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE person_states (person_id TEXT, state_id TEXT, role TEXT,
    from_date_json TEXT, confidence REAL NOT NULL, provenance TEXT NOT NULL,
    PRIMARY KEY (person_id, state_id, role, from_date_json));
CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT,
    PRIMARY KEY (entity_kind, entity_id, citation_id));
CREATE TABLE candidate_persons (id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL,
    state_id TEXT, confidence REAL NOT NULL, pipeline_run_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL, quote TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE candidate_states (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT,
    confidence REAL NOT NULL, pipeline_run_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
    quote TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE candidate_person_states (candidate_person_id TEXT, candidate_state_id TEXT,
    role TEXT, confidence REAL NOT NULL,
    PRIMARY KEY (candidate_person_id, candidate_state_id, role));
"""


def test_migration_preserves_rows_and_sets_group_type_state():
    c = sqlite3.connect(":memory:")
    c.executescript(OLD_SCHEMA)
    c.execute(
        "INSERT INTO states (id,name,type,confidence,provenance) "
        "VALUES ('sta:jin','晋','诸侯国',0.9,'auto')"
    )
    c.execute(
        "INSERT INTO persons (id,canonical_name,state_id,confidence,provenance) "
        "VALUES ('per:x','重耳','sta:jin',0.9,'auto')"
    )
    c.execute("INSERT INTO person_states VALUES ('per:x','sta:jin','ruler',NULL,0.9,'auto')")
    c.execute("INSERT INTO entity_citations VALUES ('state','sta:jin','cit:1')")

    c.execute(
        "INSERT INTO candidate_persons "
        "(id,canonical_name,state_id,confidence,pipeline_run_id,chunk_id,quote) "
        "VALUES ('cper:y','候选人','sta:jin',0.8,'run1','ch01','quote')"
    )
    c.execute(
        "INSERT INTO candidate_states (id,name,type,confidence,pipeline_run_id,chunk_id,quote) "
        "VALUES ('csta:jin','晋','诸侯国',0.8,'run1','ch01','quote')"
    )
    c.execute("INSERT INTO candidate_person_states VALUES ('cper:y','csta:jin','minister',0.8)")

    migrate.run(c)

    g = c.execute("SELECT id,name,type,group_type FROM groups").fetchone()
    # extracted sub-classification preserved; collective kind set by migration
    assert g == ("sta:jin", "晋", "诸侯国", "state")
    assert c.execute("SELECT group_id FROM persons WHERE id='per:x'").fetchone()[0] == "sta:jin"
    assert c.execute("SELECT group_id FROM person_groups").fetchone()[0] == "sta:jin"
    assert c.execute("SELECT entity_kind FROM entity_citations").fetchone()[0] == "group"
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "states" not in names and "person_states" not in names
    # candidate tables migrated
    assert "candidate_states" not in names, "candidate_states should be renamed to candidate_groups"
    assert "candidate_groups" in names, "candidate_groups should exist after migration"
    cand_person_cols = {r[1] for r in c.execute("PRAGMA table_info(candidate_persons)")}
    assert "group_id" in cand_person_cols, "candidate_persons should have group_id"
    assert "state_id" not in cand_person_cols, "candidate_persons should not have state_id"
    assert "candidate_person_states" not in names, "candidate_person_states should be renamed"
    assert "candidate_person_groups" in names, "candidate_person_groups should exist"
    cpg_cols = {r[1] for r in c.execute("PRAGMA table_info(candidate_person_groups)")}
    assert (
        "candidate_group_id" in cpg_cols
    ), "candidate_person_groups should have candidate_group_id"


def test_migration_is_idempotent():
    c = sqlite3.connect(":memory:")
    c.executescript(OLD_SCHEMA)
    c.execute(
        "INSERT INTO states (id,name,confidence,provenance) VALUES ('sta:lu','鲁',0.9,'auto')"
    )
    migrate.run(c)
    migrate.run(c)  # second run is a no-op, must not raise
    assert c.execute("SELECT COUNT(*) FROM groups").fetchone()[0] == 1
