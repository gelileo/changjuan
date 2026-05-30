import sqlite3
from pathlib import Path

from pipeline.export_enrich import build_citations_table


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
    assert rows == {
        "chk:dzl:1:0": "周幽王嬖褒姒。",
        "chk:dzl:2:5": "郑伯克段于鄢。",
    }


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
