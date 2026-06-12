import json
import sqlite3
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema
from pipeline.stage1_ingest import ingest_book

SCHEMA = Path("pipeline/schemas/corpus_schema.sql").read_text(encoding="utf-8")


def _make_corpus(corpora_dir: Path, corpus_dir: str, fname: str) -> None:
    d = corpora_dir / corpus_dir / "json"
    d.mkdir(parents=True)
    (d / fname).write_text(
        json.dumps(
            {
                "title": "T",
                "chapters": [
                    {"title": "C1", "content": "p1"},
                    {"title": "C2", "content": "p2"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_ingest_book_uses_book_meta_source_and_book_id_prefix(tmp_path):
    (tmp_path / "data" / "books" / "bk").mkdir(parents=True)
    _make_corpus(tmp_path / "corpora", "myc", "x.json")
    cfg = Config(repo_root=tmp_path, book_id="bk")
    meta = {
        "book_id": "bk",
        "title": "MyBook",
        "corpus": "mycorpus",
        "corpus_dir": "myc",
        "corpus_json": "x.json",
    }
    conn = sqlite3.connect(cfg.corpus_db)
    apply_schema(conn, SCHEMA)
    n = ingest_book(conn, cfg, meta)
    assert n == 2
    rows = conn.execute(
        "SELECT id, corpus, title, chapter_num, chapter_title FROM documents ORDER BY chapter_num"
    ).fetchall()
    assert rows[0] == ("bk:1", "mycorpus", "MyBook", 1, "C1")
    assert rows[1][0] == "bk:2"


def test_ingest_book_is_idempotent(tmp_path):
    (tmp_path / "data" / "books" / "bk").mkdir(parents=True)
    _make_corpus(tmp_path / "corpora", "myc", "x.json")
    cfg = Config(repo_root=tmp_path, book_id="bk")
    meta = {"book_id": "bk", "corpus": "mycorpus", "corpus_dir": "myc", "corpus_json": "x.json"}
    conn = sqlite3.connect(cfg.corpus_db)
    apply_schema(conn, SCHEMA)
    ingest_book(conn, cfg, meta)
    assert ingest_book(conn, cfg, meta) == 0
