import json
import os
from pathlib import Path

import pytest

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_book

_DZL_META = {
    "book_id": "dzl",
    "corpus": "dongzhoulieguozhi",
    "corpus_dir": "dongzhoulieguozhi",
    "corpus_json": "东周列国志.json",
    "title": "东周列国志",
}


def _make_fake_corpus(corpora_dir: Path) -> Path:
    """Synthesize the dongzhoulieguozhi/json/东周列国志.json file the real corpus exposes."""
    repo = corpora_dir / "dongzhoulieguozhi"
    (repo / "json").mkdir(parents=True)
    data = {
        "title": "东周列国志",
        "chapters": [
            {"title": "第一回　test 1", "content": "para A\r\npara B"},
            {"title": "第二回　test 2", "content": "para C"},
        ],
    }
    p = repo / "json" / "东周列国志.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return repo


def test_ingest_inserts_one_row_per_chapter(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    _make_fake_corpus(cfg.corpora_dir)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        count = ingest_book(conn, cfg, _DZL_META)
    assert count == 2
    with connect(cfg.corpus_db) as conn:
        rows = list(
            conn.execute(
                "SELECT corpus, chapter_num, chapter_title FROM documents ORDER BY chapter_num;"
            )
        )
    assert rows[0]["corpus"] == "dongzhoulieguozhi"
    assert rows[0]["chapter_num"] == 1
    assert rows[1]["chapter_num"] == 2


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    _make_fake_corpus(cfg.corpora_dir)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        ingest_book(conn, cfg, _DZL_META)
        # second call must not crash on UNIQUE constraint
        ingest_book(conn, cfg, _DZL_META)
        count = conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    assert count == 2


def test_ingest_returns_actual_insert_count_not_input_length(tmp_path: Path) -> None:
    """If the same row is ingested twice, the second call's return value should be 0,
    not len(rows). Phase 1 returned len(rows) regardless of whether anything was inserted.
    """
    cfg = Config(repo_root=tmp_path)
    _make_fake_corpus(cfg.corpora_dir)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n1 = ingest_book(conn, cfg, _DZL_META)
        n2 = ingest_book(conn, cfg, _DZL_META)
    assert n1 == 2, f"first ingest should report 2 inserts, got {n1}"
    assert n2 == 0, f"re-ingest of same rows should report 0 inserts, got {n2}"


@pytest.mark.skipif(
    not Path("corpora/dongzhoulieguozhi/json/东周列国志.json").exists(),
    reason="real corpus not present (symlink missing?)",
)
def test_ingest_real_corpus_has_108_chapters() -> None:
    """Sanity check against the real upstream corpus."""
    cfg = Config()
    tmp = Path(os.environ.get("PYTEST_TMP", "/tmp")) / "changjuan-test-corpus.sqlite"
    if tmp.exists():
        tmp.unlink()
    cfg_with_tmp = Config(repo_root=cfg.repo_root)
    from pipeline.db import apply_schema, connect
    from pipeline.schemas import CORPUS_SCHEMA

    with connect(tmp) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = ingest_book(conn, cfg_with_tmp, _DZL_META)
        assert n == 108
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM documents WHERE corpus='dongzhoulieguozhi';"
            ).fetchone()[0]
            == 108
        )
