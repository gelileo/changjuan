import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.integration
def test_dzl_ingest_unchanged():
    """dzl ingest still produces dzl:<n> ids + corpus 'dongzhoulieguozhi' from its book-meta."""
    meta = json.loads((ROOT / "data/books/dzl/book-meta.json").read_text("utf-8"))
    assert meta["corpus"] == "dongzhoulieguozhi"
    src = ROOT / "corpora" / meta["corpus_dir"] / "json" / meta["corpus_json"]
    if not src.exists():
        pytest.skip("dzl corpus source not present")
    from pipeline.config import Config
    from pipeline.db import apply_schema
    from pipeline.stage1_ingest import ingest_book

    SCHEMA = (ROOT / "pipeline/schemas/corpus_schema.sql").read_text("utf-8")
    conn = sqlite3.connect(":memory:")
    apply_schema(conn, SCHEMA)
    cfg = Config(repo_root=ROOT, book_id="dzl")
    n = ingest_book(conn, cfg, meta)
    assert n == 108
    first = conn.execute("SELECT id, corpus FROM documents ORDER BY chapter_num LIMIT 1").fetchone()
    assert first == ("dzl:1", "dongzhoulieguozhi")


@pytest.mark.integration
def test_hlm_ingest_120_chapters():
    meta = json.loads((ROOT / "data/books/hlm/book-meta.json").read_text("utf-8"))
    src = ROOT / "corpora" / meta["corpus_dir"] / "json" / meta["corpus_json"]
    if not src.exists():
        pytest.skip("hlm corpus source not present (corpora/hlm staged?)")
    from pipeline.config import Config
    from pipeline.db import apply_schema
    from pipeline.stage1_ingest import ingest_book

    SCHEMA = (ROOT / "pipeline/schemas/corpus_schema.sql").read_text("utf-8")
    conn = sqlite3.connect(":memory:")
    apply_schema(conn, SCHEMA)
    cfg = Config(repo_root=ROOT, book_id="hlm")
    n = ingest_book(conn, cfg, meta)
    assert n == 120
    row = conn.execute(
        "SELECT id, corpus, chapter_title FROM documents ORDER BY chapter_num LIMIT 1"
    ).fetchone()
    assert row[0] == "hlm:1" and row[1] == "honglou" and "第一回" in row[2]
