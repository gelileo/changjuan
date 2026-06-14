def test_clan_groups_merge_on_surname_stem():
    """Cast clan groups with household-suffix variants collapse to one stem node;
    state (history) groups keep exact-name matching."""
    import sqlite3
    from pathlib import Path

    from pipeline.stage7_load.groups import _clan_stem, load_candidate_groups

    assert _clan_stem("贾府") == "贾"
    assert _clan_stem("史侯家") == "史"
    assert _clan_stem("尤氏家") == "尤"
    assert _clan_stem("贾") == "贾"

    SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    for i, nm in enumerate(["贾府", "贾家", "贾"], 1):
        c.execute(
            "INSERT INTO candidate_groups (id,name,type,confidence,pipeline_run_id,chunk_id,quote) "
            "VALUES (?,?,?,0.9,'r1','ch:1','q')",
            (f"cand:grp:r1:s{i}", nm, "家族"),
        )
    load_candidate_groups(c, "r1", profile="cast")
    rows = c.execute("SELECT name, group_type FROM groups").fetchall()
    assert rows == [("贾", "clan")], rows
