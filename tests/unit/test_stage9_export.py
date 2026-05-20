import json
import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage9_export import export_bundle


def test_export_creates_manifest_and_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "changjuan-export-test-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO persons (id, canonical_name, confidence, provenance)"
            " VALUES ('per:a', 'a', 0.9, 'auto');"
        )
    export_bundle(src, out, version="test-v1")
    assert (out / "manifest.json").is_file()
    assert (out / "changjuan.sqlite").is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["version"] == "test-v1"
    assert manifest["counts"]["persons"] == 1


def test_export_snapshot_is_readable_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "changjuan-export-test-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(src, out, version="test-v1")
    with sqlite3.connect(out / "changjuan.sqlite") as snap:
        cur = snap.execute("SELECT name FROM sqlite_master WHERE type='table';")
        names = {r[0] for r in cur}
    assert "persons" in names
