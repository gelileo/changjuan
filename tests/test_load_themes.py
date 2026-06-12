import json
import sqlite3
from pathlib import Path

from pipeline.stage7_load.themes import load_candidate_themes

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def _seed(c):
    c.execute(
        "INSERT INTO persons (id,canonical_name,confidence,provenance) "
        "VALUES ('per:黛玉','林黛玉',0.9,'auto')"
    )
    c.execute(
        "INSERT INTO candidate_persons "
        "(id,canonical_name,confidence,pipeline_run_id,chunk_id,quote) "
        "VALUES ('cand:per:r1:p1','林黛玉',0.9,'r1','hlm:1','q')"
    )
    occ = json.dumps(
        [
            {"entity_kind": "person", "entity_id": "p1"},
            {"entity_kind": "chapter", "entity_id": "hlm:1"},
        ],
        ensure_ascii=False,
    )
    c.execute(
        "INSERT INTO candidate_themes "
        "(id,name,description,occurrences_json,confidence,pipeline_run_id,chunk_id,quote) "
        "VALUES ('cand:thm:r1:t1','命运','宿命与无常',?,0.9,'r1','hlm:1','q')",
        (occ,),
    )


def test_load_candidate_themes_creates_theme_and_resolves_occurrences():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    _seed(c)
    n = load_candidate_themes(c, pipeline_run_id="r1")
    assert n == 1
    th = c.execute("SELECT id, name, description FROM themes").fetchone()
    assert th[0].startswith("thm:") and th[1] == "命运"
    occ = c.execute(
        "SELECT entity_kind, entity_id FROM theme_occurrences ORDER BY entity_kind"
    ).fetchall()
    assert ("person", "per:黛玉") in occ
    assert ("chapter", "hlm:1") in occ
    assert (
        c.execute("SELECT COUNT(*) FROM entity_citations WHERE entity_kind='theme'").fetchone()[0]
        >= 1
    )


def test_load_candidate_themes_idempotent_name_match():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    _seed(c)
    load_candidate_themes(c, pipeline_run_id="r1")
    load_candidate_themes(c, pipeline_run_id="r1")
    assert c.execute("SELECT COUNT(*) FROM themes").fetchone()[0] == 1


def test_history_profile_has_no_themes_capability():
    from typing import cast as tcast

    from pipeline.profile import PROFILES

    history_caps: list[str] = tcast(list[str], PROFILES["history"]["capabilities"])
    cast_caps: list[str] = tcast(list[str], PROFILES["cast"]["capabilities"])
    assert "themes" not in history_caps
    assert "themes" in cast_caps
