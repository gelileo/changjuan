import hashlib
from pathlib import Path

from pipeline.publish_depot import build_entry, sha256_file, upsert_catalog


def test_sha256_file(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"SQLITEDATA")
    assert sha256_file(p) == hashlib.sha256(b"SQLITEDATA").hexdigest()


def test_build_entry_carries_manifest_fields_and_defaults_language() -> None:
    manifest = {
        "book_id": "dzl",
        "slug": "dongzhoulieguozhi",
        "title": "东周列国志",
        "author": "冯",
        "edition": "明",
        "cover": None,
        "capabilities": ["cast"],
        "schema_version": 6,
        "counts": {"persons": 1},
        "version": "2026-06-v8",
    }
    entry = build_entry(
        manifest, bundle_path="books/dzl/dzl-2026-06-v8.sqlite", bytes_=10, sha256="abc"
    )
    assert entry["book_id"] == "dzl"
    assert entry["language"] == "zh-CN"  # manifest lacks language → default
    assert entry["bundle"] == {
        "path": "books/dzl/dzl-2026-06-v8.sqlite",
        "bytes": 10,
        "sha256": "abc",
    }
    assert entry["counts"] == {"persons": 1}


def test_upsert_appends_then_replaces_and_sorts() -> None:
    out = upsert_catalog({}, {"book_id": "dzl", "version": "v1", "bundle": {}}, "T1")
    assert [b["book_id"] for b in out["books"]] == ["dzl"]
    assert out["catalog_schema"] == 1 and out["generated_at"] == "T1"
    out2 = upsert_catalog(out, {"book_id": "dzl", "version": "v2", "bundle": {}}, "T2")
    assert len(out2["books"]) == 1 and out2["books"][0]["version"] == "v2"  # replaced, no dup
    out3 = upsert_catalog(out2, {"book_id": "abc", "version": "v1", "bundle": {}}, "T3")
    assert [b["book_id"] for b in out3["books"]] == ["abc", "dzl"]  # sorted by book_id
