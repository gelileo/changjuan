import sqlite3
from pathlib import Path

from pipeline.export_enrich import (
    add_narrative_seq,
    add_pinyin_columns,
    build_chapter_texts,
    build_citations_table,
    build_deed_importance,
    deed_importance,
    to_pinyin,
)


def _mk_graph(path: Path) -> None:
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT);"
        )
        c.executemany(
            "INSERT INTO entity_citations VALUES (?,?,?);",
            [
                ("person", "per:a", "chk:dzl:1:0"),
                ("person", "per:a", "chk:dzl:1:0"),  # duplicate id
                ("event", "evt:x", "chk:dzl:2:5"),
                # run: ids are pipeline-run provenance on edge entities — not passage citations
                ("event_participant", "evt:x:per:a:role", "run:extract-chX-vY"),
            ],
        )


def _mk_corpus(path: Path) -> None:
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )
        c.executemany(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?);",
            [
                ("chk:dzl:1:0", "dzl:1", 0, 0, "周幽王嬖褒姒。", "h1"),
                ("chk:dzl:2:5", "dzl:2", 5, 6, "郑伯克段于鄢。", "h2"),
                ("chk:dzl:9:9", "dzl:9", 9, 9, "uncited chunk", "h3"),
            ],
        )


def test_add_narrative_seq_min_chapter_then_paragraph(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE events (id TEXT PRIMARY KEY, type TEXT);")
        c.executemany(
            "INSERT INTO events VALUES (?,?);",
            [("evt:mid", "x"), ("evt:later", "x"), ("evt:nocite", "x")],
        )
        c.execute(
            "CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT);"
        )
        c.executemany(
            "INSERT INTO entity_citations VALUES ('event',?,?);",
            [
                ("evt:mid", "chk:dzl:76:16"),  # later chapter
                ("evt:mid", "chk:dzl:75:31"),  # earliest → wins the MIN
                ("evt:later", "chk:dzl:77:17"),
                ("evt:nocite", "run:extract-chX"),  # non-chk → ignored
            ],
        )
        c.execute(
            "CREATE TABLE citations (citation_id TEXT, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT);"
        )
        c.executemany(
            "INSERT INTO citations VALUES (?,?,?,?,'');",
            [
                ("chk:dzl:76:16", "dzl:76", 16, 16),
                ("chk:dzl:75:31", "dzl:75", 31, 31),
                ("chk:dzl:77:17", "dzl:77", 17, 17),
            ],
        )

    add_narrative_seq(graph)

    with sqlite3.connect(graph) as c:
        seq = dict(c.execute("SELECT id, narrative_seq FROM events;"))
    assert seq["evt:mid"] == 75 * 100000 + 31  # MIN across citations → earliest chapter
    assert seq["evt:later"] == 77 * 100000 + 17
    assert seq["evt:nocite"] is None  # no chunk citation
    # Ordering key behaves: earlier chapter sorts first, citation-less last.
    assert seq["evt:mid"] < seq["evt:later"]


def test_build_citations_table_denormalizes_cited_chunks(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    _mk_graph(graph)
    _mk_corpus(corpus)

    build_citations_table(graph, corpus)

    with sqlite3.connect(graph) as c:
        rows = dict(
            (cid, txt) for cid, txt in c.execute("SELECT citation_id, text FROM citations;")
        )
    # Only chk: chunk pointers appear — run: provenance ids are excluded
    assert rows == {
        "chk:dzl:1:0": "周幽王嬖褒姒。",
        "chk:dzl:2:5": "郑伯克段于鄢。",
    }
    assert "run:extract-chX-vY" not in rows


def test_to_pinyin_toneless_joined_lowercase() -> None:
    assert to_pinyin("管仲") == "guanzhong"
    assert to_pinyin("赵盾") == "zhaodun"
    assert to_pinyin("") == ""


def test_add_pinyin_columns_populates_persons_and_variants(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE persons (id TEXT PRIMARY KEY, canonical_name TEXT);")
        c.execute(
            "CREATE TABLE person_variants (id TEXT PRIMARY KEY, "
            "person_id TEXT, variant TEXT, kind TEXT);"
        )
        c.execute("INSERT INTO persons VALUES ('per:gz', '管仲');")
        c.execute(
            "INSERT INTO person_variants (person_id, variant, kind) "
            "VALUES ('per:gz', '夷吾', '本名');"
        )
    add_pinyin_columns(graph)
    with sqlite3.connect(graph) as c:
        p = c.execute("SELECT pinyin FROM persons WHERE id='per:gz';").fetchone()[0]
        v = c.execute("SELECT pinyin FROM person_variants WHERE variant='夷吾';").fetchone()[0]
    assert p == "guanzhong"
    assert v == "yiwu"


def test_build_citations_table_raises_when_chunk_missing(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    _mk_graph(graph)
    with sqlite3.connect(corpus) as c:
        c.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )  # empty — cited chunks absent
    import pytest

    with pytest.raises(ValueError, match="2 cited chunk"):
        build_citations_table(graph, corpus)


def test_deed_importance_high_weight_beats_low_for_same_person() -> None:
    # dense person: a battle outranks a sickbed visit
    battle = deed_importance(event_type="战", participants=6, citations=2, person_type_fraction=0.1)
    visit = deed_importance(
        event_type="探病", participants=2, citations=1, person_type_fraction=0.1
    )
    assert battle > visit


def test_deed_importance_rarity_boosts_sole_defining_act() -> None:
    # fraction=1/8: only 1 of 8 deeds is this type -> high rarity -> boosted.
    # fraction=4/8: 4 of 8 deeds are this type -> lower rarity -> smaller boost.
    sole = deed_importance(
        event_type="谏", participants=2, citations=1, person_type_fraction=1.0 / 8
    )
    common = deed_importance(
        event_type="谏", participants=2, citations=1, person_type_fraction=4.0 / 8
    )
    assert sole > common


def test_build_deed_importance_writes_a_row_per_participation(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE events (id TEXT PRIMARY KEY, type TEXT);")
        c.execute(
            "CREATE TABLE event_participants (event_id TEXT, person_id TEXT, "
            "role TEXT, role_detail TEXT, citation_id TEXT, confidence REAL, "
            "provenance TEXT);"
        )
        c.execute(
            "CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT);"
        )
        c.execute("INSERT INTO events VALUES ('evt:war', '战'), ('evt:visit', '探病');")
        c.executemany(
            "INSERT INTO event_participants (event_id, person_id, role, confidence, provenance)"
            " VALUES (?,?,?,1.0,'auto');",
            [("evt:war", "per:a", "主将"), ("evt:visit", "per:a", "主行")],
        )
    build_deed_importance(graph)
    with sqlite3.connect(graph) as c:
        scores = dict(
            c.execute("SELECT event_id, score FROM deed_importance WHERE person_id='per:a';")
        )
    assert set(scores) == {"evt:war", "evt:visit"}
    assert scores["evt:war"] > scores["evt:visit"]


def test_add_prominence_tiers_and_overrides(tmp_path: Path) -> None:
    """deed-sum ranks tiers; promote raises a sparse figure to 'notable'."""
    from pipeline.export_enrich import add_prominence

    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE persons (id TEXT PRIMARY KEY, canonical_name TEXT);")
        c.execute("CREATE TABLE deed_importance (event_id TEXT, person_id TEXT, score REAL);")
        c.executemany(
            "INSERT INTO persons VALUES (?,?);",
            [("per:big", "霸主"), ("per:mid", "中人"), ("per:icon", "卞和"), ("per:none", "路人")],
        )
        c.executemany(
            "INSERT INTO deed_importance VALUES (?,?,?);",
            [
                ("e1", "per:big", 900.0),
                ("e2", "per:big", 100.0),
                ("e3", "per:mid", 50.0),
                ("e4", "per:icon", 0.5),
            ],  # per:none has no deeds
        )
    overrides = tmp_path / "ov.yaml"
    overrides.write_text("promote:\n  - 卞和\ndemote: []\n", encoding="utf-8")

    # tiny cutoffs so the 4-person fixture exercises all tiers
    import pipeline.export_enrich as ee

    orig = (ee.PROMINENCE_MAJOR_TOP, ee.PROMINENCE_NOTABLE_TOP)
    ee.PROMINENCE_MAJOR_TOP, ee.PROMINENCE_NOTABLE_TOP = 1, 2
    try:
        add_prominence(graph, overrides)
    finally:
        ee.PROMINENCE_MAJOR_TOP, ee.PROMINENCE_NOTABLE_TOP = orig

    with sqlite3.connect(graph) as c:
        tiers = dict(c.execute("SELECT id, prominence_tier FROM persons;"))
        scores = dict(c.execute("SELECT id, prominence FROM persons;"))
    assert tiers["per:big"] == "major"  # rank 1 (1000.0)
    assert tiers["per:mid"] == "notable"  # rank 2 (50.0)
    assert tiers["per:icon"] == "notable"  # rank 3 -> minor, but promoted by override
    assert tiers["per:none"] == "minor"  # no deeds
    assert scores["per:big"] == 1000.0
    assert scores["per:none"] == 0.0


def test_add_event_prominence_tiers_with_boundary_promotion(tmp_path: Path) -> None:
    """deed-sum ranks event tiers; a low-score reign/state-boundary type is promoted."""
    from pipeline.export_enrich import add_event_prominence

    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE events (id TEXT PRIMARY KEY, type TEXT);")
        c.execute("CREATE TABLE deed_importance (event_id TEXT, person_id TEXT, score REAL);")
        c.executemany(
            "INSERT INTO events VALUES (?,?);",
            [("evt:big", "战"), ("evt:mid", "盟会"), ("evt:acc", "即位"), ("evt:dull", "朝议")],
        )
        c.executemany(
            "INSERT INTO deed_importance VALUES (?,?,?);",
            [("evt:big", "p1", 900.0), ("evt:big", "p2", 100.0), ("evt:mid", "p1", 50.0)],
        )  # evt:acc and evt:dull have no deeds -> score 0

    import pipeline.export_enrich as ee

    orig = (ee.EVENT_MAJOR_TOP, ee.EVENT_NOTABLE_TOP)
    ee.EVENT_MAJOR_TOP, ee.EVENT_NOTABLE_TOP = 1, 2
    try:
        add_event_prominence(graph)
    finally:
        ee.EVENT_MAJOR_TOP, ee.EVENT_NOTABLE_TOP = orig

    with sqlite3.connect(graph) as c:
        tiers = dict(c.execute("SELECT id, prominence_tier FROM events;"))
        scores = dict(c.execute("SELECT id, prominence FROM events;"))
    assert tiers["evt:big"] == "major"  # rank 1 (1000.0)
    assert tiers["evt:mid"] == "notable"  # rank 2 (50.0)
    assert tiers["evt:acc"] == "notable"  # rank 3 -> minor, promoted by 即位 boundary type
    assert tiers["evt:dull"] == "minor"  # rank 4, non-boundary, no deeds
    assert scores["evt:big"] == 1000.0
    assert scores["evt:dull"] == 0.0


def test_add_state_prominence_curated_allowlist(tmp_path: Path) -> None:
    """group score = deed-sum over its persons; tier = curated allow-list (major) else minor."""
    from pipeline.export_enrich import add_state_prominence

    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE groups (id TEXT PRIMARY KEY, name TEXT);")
        c.execute("CREATE TABLE persons (id TEXT PRIMARY KEY, group_id TEXT);")
        c.execute("CREATE TABLE deed_importance (event_id TEXT, person_id TEXT, score REAL);")
        c.executemany("INSERT INTO groups VALUES (?,?);", [("sta:晋", "晋"), ("sta:滑", "滑")])
        c.executemany(
            "INSERT INTO persons VALUES (?,?);",
            [("per:a", "sta:晋"), ("per:b", "sta:晋"), ("per:c", "sta:滑")],
        )
        c.executemany(
            "INSERT INTO deed_importance VALUES (?,?,?);",
            [("e1", "per:a", 300.0), ("e2", "per:b", 100.0), ("e3", "per:c", 5.0)],
        )
    overrides = tmp_path / "ov.yaml"
    overrides.write_text("states:\n  - 晋\n", encoding="utf-8")

    add_state_prominence(graph, overrides)

    with sqlite3.connect(graph) as c:
        tiers = dict(c.execute("SELECT id, prominence_tier FROM groups;"))
        scores = dict(c.execute("SELECT id, prominence FROM groups;"))
    assert tiers["sta:晋"] == "major"  # on the allow-list
    assert tiers["sta:滑"] == "minor"  # not on the allow-list
    assert scores["sta:晋"] == 400.0  # 300 + 100
    assert scores["sta:滑"] == 5.0


def test_build_chapter_texts_one_row_per_chapter(tmp_path: Path) -> None:
    readable = tmp_path / "readable"
    readable.mkdir()
    (readable / "ch01.md").write_text("# Chapter 1\n\n周宣王", encoding="utf-8")
    (readable / "ch10.md").write_text("# Chapter 10\n\n楚熊通", encoding="utf-8")
    (readable / "changelog.md").write_text("notes", encoding="utf-8")  # non-chapter → ignored
    graph = tmp_path / "graph.sqlite"
    sqlite3.connect(graph).close()
    build_chapter_texts(graph, readable)
    with sqlite3.connect(graph) as c:
        rows = dict(
            c.execute("SELECT chapter, markdown FROM chapter_texts ORDER BY chapter;").fetchall()
        )
    assert set(rows) == {1, 10}
    assert rows[1] == "# Chapter 1\n\n周宣王"
    assert rows[10].startswith("# Chapter 10")


def test_build_chapter_texts_idempotent_and_tolerates_missing_dir(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    sqlite3.connect(graph).close()
    build_chapter_texts(graph, tmp_path / "nope")  # absent dir → table created, no rows
    with sqlite3.connect(graph) as c:
        assert c.execute("SELECT COUNT(*) FROM chapter_texts;").fetchone()[0] == 0
    readable = tmp_path / "readable"
    readable.mkdir()
    (readable / "ch01.md").write_text("x", encoding="utf-8")
    build_chapter_texts(graph, readable)
    build_chapter_texts(graph, readable)  # re-run is idempotent (drop + recreate)
    with sqlite3.connect(graph) as c:
        assert c.execute("SELECT COUNT(*) FROM chapter_texts;").fetchone()[0] == 1
