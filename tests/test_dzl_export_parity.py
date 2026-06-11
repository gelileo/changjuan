import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from pipeline.migrations import migrate_0001_state_to_group as migrate
from pipeline.stage9_export import manifest_reader_capabilities


def test_reader_caps_for_dzl_meta():
    meta = json.loads(Path("data/books/dzl/book-meta.json").read_text("utf-8"))
    assert meta["profile"] == "history"
    assert manifest_reader_capabilities(meta) == ["cast", "timeline", "groups"]


@pytest.mark.integration
def test_dzl_migration_preserves_counts(tmp_path):
    """Migrating dzl canonical.sqlite preserves row counts: groups == old states,
    person_groups == old person_states, persons.group_id non-null == old state_id non-null."""
    src = Path("data/books/dzl/canonical.sqlite")
    if not src.exists():
        pytest.skip("dzl canonical.sqlite not present")
    work = tmp_path / "canonical.sqlite"
    shutil.copyfile(src, work)
    c = sqlite3.connect(work)
    has_states = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='states'"
    ).fetchone()
    if not has_states:
        pytest.skip("dzl canonical.sqlite already migrated to groups schema")
    n_states = c.execute("SELECT COUNT(*) FROM states").fetchone()[0]
    n_person_states = c.execute("SELECT COUNT(*) FROM person_states").fetchone()[0]
    n_state_fk = c.execute("SELECT COUNT(*) FROM persons WHERE state_id IS NOT NULL").fetchone()[0]

    migrate.run(c)

    assert c.execute("SELECT COUNT(*) FROM groups").fetchone()[0] == n_states
    assert c.execute("SELECT COUNT(*) FROM person_groups").fetchone()[0] == n_person_states
    assert (
        c.execute("SELECT COUNT(*) FROM persons WHERE group_id IS NOT NULL").fetchone()[0]
        == n_state_fk
    )
    assert (
        c.execute("SELECT COUNT(*) FROM groups WHERE group_type='state'").fetchone()[0] == n_states
    )
