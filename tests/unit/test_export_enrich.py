import sqlite3
from pathlib import Path

from pipeline.export_enrich import (
    add_pinyin_columns,
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
    # same low-weight event type; the person for whom it is their ONLY deed of
    # that type (fraction=1.0 -> rare relative to a rich record) is boosted vs.
    # a person for whom that type is common (fraction=0.5).
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
