import json
import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage9_export import export_bundle

_CHUNKS_DDL = (
    "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
    "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
)

_MINIMAL_BOOK_META = {
    "book_id": "dzl",
    "title": "东周列国志",
    "author": "冯梦龙 / 蔡元放",
    "edition": "明刊本",
    "cover": None,
    "capabilities": ["cast", "timeline", "states"],
}


def _empty_corpus(tmp_path: Path) -> Path:
    """Return a path to an empty-but-valid corpus.sqlite (no chunks, no citations needed)."""
    corpus = tmp_path / "corpus.sqlite"
    with sqlite3.connect(corpus) as cc:
        cc.execute(_CHUNKS_DDL)
    return corpus


def test_export_creates_manifest_and_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "changjuan-export-test-v1"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:a', 'a', 0.9, 'auto');"
        )
    export_bundle(
        src,
        out,
        version="test-v1",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    assert (out / "manifest.json").is_file()
    assert (out / "graph.sqlite").is_file()
    assert not (out / "changjuan.sqlite").exists()
    assert (out / "texts").is_dir()  # absent readable_dir → empty texts/ still created
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["version"] == "test-v1"
    assert manifest["schema_version"] == 2
    assert manifest["counts"]["persons"] == 1


def test_export_snapshot_is_readable_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "changjuan-export-test-v1"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(
        src,
        out,
        version="test-v1",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    with sqlite3.connect(out / "graph.sqlite") as snap:
        cur = snap.execute("SELECT name FROM sqlite_master WHERE type='table';")
        names = {r[0] for r in cur}
    assert "persons" in names


def test_export_strips_all_candidate_tables(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "x-v1"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Seed a candidate_persons row so the table is non-empty in src
        conn.execute(
            "INSERT INTO candidate_persons"
            " (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote)"
            " VALUES ('cper:1', 'x', 0.5, 'r', 'c', 'q');"
        )
    export_bundle(
        src,
        out,
        version="x-v1",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    with sqlite3.connect(out / "graph.sqlite") as snap:
        cur = snap.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';"
        )
        leaked = [r[0] for r in cur]
    assert leaked == [], f"export leaked candidate tables: {leaked}"


def test_export_strips_llm_cache(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "x-v1"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(
        src,
        out,
        version="x-v1",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    with sqlite3.connect(out / "graph.sqlite") as snap:
        cur = snap.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_cache';"
        )
        assert cur.fetchone() is None


def test_export_roundtrip_preserves_canonical_data(tmp_path: Path) -> None:
    """Load export bundle into a fresh sqlite handle; counts and key rows must match source."""
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "rt-v1"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:a', 'a', 0.9, 'auto');"
        )
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:b', 'b', 0.5, 'curated');"
        )
        conn.execute(
            "INSERT INTO events (id, type, confidence, provenance)"
            " VALUES ('evt:1', 'battle', 0.8, 'auto');"
        )
    export_bundle(
        src,
        out,
        version="rt-v1",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )

    # Fresh handle on the snapshot
    with sqlite3.connect(out / "graph.sqlite") as snap:
        persons = list(
            snap.execute("SELECT id, canonical_name, provenance FROM persons ORDER BY id;")
        )
        events = list(snap.execute("SELECT id, type FROM events;"))
    assert [r[0] for r in persons] == ["per:a", "per:b"]
    assert [r[2] for r in persons] == ["auto", "curated"]
    assert events == [("evt:1", "battle")]

    # Manifest counts agree with snapshot reality
    import json as _json

    manifest = _json.loads((out / "manifest.json").read_text())
    assert manifest["counts"]["persons"] == 2
    assert manifest["counts"]["events"] == 1


def test_export_copies_readable_texts(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    readable = tmp_path / "readable"
    readable.mkdir()
    (readable / "ch01.md").write_text("第一回 正文", encoding="utf-8")
    (readable / "ch02.md").write_text("第二回 正文", encoding="utf-8")
    out = tmp_path / "exports" / "t"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    with sqlite3.connect(corpus) as cc:
        cc.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )
    export_bundle(
        src, out, version="t", corpus_db=corpus, book_meta=_MINIMAL_BOOK_META, readable_dir=readable
    )
    assert (out / "texts" / "ch01.md").read_text(encoding="utf-8") == "第一回 正文"
    assert (out / "texts" / "ch02.md").is_file()


def test_snapshot_includes_uncheckpointed_wal_data(tmp_path: Path) -> None:
    """A row committed to the WAL but not checkpointed must survive the snapshot.

    shutil.copyfile copies only the main DB file, silently dropping
    un-checkpointed WAL frames. VACUUM INTO reads the live (main+WAL) view, so
    the sentinel row must appear in the exported graph.sqlite.
    """
    src = tmp_path / "changjuan.sqlite"
    writer = sqlite3.connect(src)
    writer.execute("PRAGMA journal_mode=WAL;")
    writer.execute("PRAGMA wal_autocheckpoint=0;")  # never auto-merge to main
    apply_schema(writer, CANONICAL_SCHEMA)
    writer.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES ('per:wal', '王在WAL', 0.9, 'auto');"
    )
    writer.commit()  # committed, but lives in -wal, not the main file
    # IMPORTANT: do NOT close `writer` before snapshotting — closing may checkpoint.

    corpus = tmp_path / "corpus.sqlite"
    with connect(corpus) as cc:
        cc.execute(_CHUNKS_DDL)
    out = tmp_path / "exports" / "wal"
    export_bundle(
        src,
        out,
        version="wal",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    writer.close()

    with sqlite3.connect(out / "graph.sqlite") as snap:
        got = snap.execute("SELECT canonical_name FROM persons WHERE id='per:wal';").fetchone()
    assert got is not None and got[0] == "王在WAL"


def test_manifest_includes_book_identity_and_capabilities(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    corpus = _empty_corpus(tmp_path)
    out = tmp_path / "exports" / "b"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(
        src,
        out,
        version="b",
        corpus_db=corpus,
        book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["book_id"] == _MINIMAL_BOOK_META["book_id"]
    assert manifest["title"] == _MINIMAL_BOOK_META["title"]
    assert manifest["author"] == _MINIMAL_BOOK_META["author"]
    assert manifest["edition"] == _MINIMAL_BOOK_META["edition"]
    assert manifest["capabilities"] == _MINIMAL_BOOK_META["capabilities"]
    assert manifest["cover"] == _MINIMAL_BOOK_META["cover"]  # None → JSON null branch
