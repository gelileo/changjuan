"""End-to-end Phase 1 integration test.

Walks the deterministic pipeline: ingest a tiny synthetic corpus → chunk → seed a
synthetic candidate_persons row → load → export. Asserts the export bundle has
the expected data and no candidate tables. This is the regression target for the
Phase 1 build sequence.
"""

import json
import sqlite3
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi
from pipeline.stage2_chunk import chunk_documents
from pipeline.stage7_load import load_candidate_persons
from pipeline.stage9_export import export_bundle


def _seed_fake_corpus(corpora_dir: Path) -> None:
    repo = corpora_dir / "dongzhoulieguozhi" / "json"
    repo.mkdir(parents=True)
    (repo / "东周列国志.json").write_text(
        json.dumps(
            {
                "title": "东周列国志",
                "chapters": [
                    {
                        "title": "第一回　test",
                        "content": "para 1 about 重耳.\n\npara 2 about 晋.",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_phase1_roundtrip(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    _seed_fake_corpus(cfg.corpora_dir)

    # 1. Ingest
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n_docs = ingest_dongzhoulieguozhi(conn, cfg)
    assert n_docs == 1

    # 2. Chunk
    with connect(cfg.corpus_db) as conn:
        n_chunks = chunk_documents(conn, cfg)
    assert n_chunks >= 1

    # 3. Load synthetic candidates (Phase 2 will produce these from LLM; Phase 1 fakes them)
    with connect(cfg.canonical_db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons "
            "(id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 0.9, 'run:1', 'chk:dzl:1:0', 'para 1 about 重耳');"
        )
        n_loaded = load_candidate_persons(conn, pipeline_run_id="run:1")
    assert n_loaded == 1

    # 4. Export
    out = cfg.exports_dir / "changjuan-export-rt-v1"
    _meta = {
        "book_id": "dzl",
        "title": "东周列国志",
        "author": "冯梦龙 / 蔡元放",
        "edition": "明刊本",
        "cover": None,
        "capabilities": ["cast", "timeline", "states"],
    }
    export_bundle(
        cfg.canonical_db,
        out,
        version="rt-v1",
        corpus_db=cfg.corpus_db,
        book_meta=_meta,
        readable_dir=cfg.readable_dir,
    )

    # Bundle assertions
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["counts"]["persons"] == 1
    assert "audit_log" in manifest["counts"]
    with sqlite3.connect(out / "graph.sqlite") as snap:
        leaked = list(
            snap.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';"
            )
        )
        person_name = snap.execute("SELECT canonical_name FROM persons;").fetchone()[0]
    assert leaked == []
    assert person_name == "重耳"
