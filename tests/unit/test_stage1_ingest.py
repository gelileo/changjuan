import json
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi


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
        count = ingest_dongzhoulieguozhi(conn, cfg)
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
        ingest_dongzhoulieguozhi(conn, cfg)
        # second call must not crash on UNIQUE constraint
        ingest_dongzhoulieguozhi(conn, cfg)
        count = conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    assert count == 2
