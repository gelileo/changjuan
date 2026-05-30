"""Stage 9 — Freeze and export.

Produces `out_dir/` with:
- manifest.json: version, schema_version, generated_at, counts per canonical table,
  source corpus editions
- graph.sqlite: read-only snapshot with candidate_* tables prefix-excluded and
  llm_cache excluded
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pipeline.export_enrich import add_pinyin_columns, build_citations_table, build_deed_importance

SCHEMA_VERSION = 2


def export_bundle(
    src_db: Path,
    out_dir: Path,
    *,
    version: str,
    corpus_db: Path,
    book_meta: Mapping[str, object],
) -> Path:
    """Export a versioned bundle: manifest.json + canonical-only sqlite snapshot.

    corpus_db must be the path to corpus.sqlite; it is used to denormalize cited
    chunk passages into graph.sqlite's `citations` table.

    book_meta must contain at least "book_id" and "capabilities"; optionally
    "title", "author", "edition", "cover".  Source this from
    data/books/<book_id>/book-meta.json.

    Returns out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    snap_path = out_dir / "graph.sqlite"
    _snapshot_canonical_only(src_db, snap_path)
    build_citations_table(snap_path, corpus_db)
    add_pinyin_columns(snap_path)
    build_deed_importance(snap_path)

    counts = _count_rows(snap_path)
    manifest: dict[str, object] = {
        "version": version,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "book_id": book_meta["book_id"],
        "title": book_meta.get("title"),
        "author": book_meta.get("author"),
        "edition": book_meta.get("edition"),
        "cover": book_meta.get("cover"),
        "capabilities": book_meta["capabilities"],
        "counts": counts,
        "source_corpus_editions": _source_editions(corpus_db),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_dir


def _snapshot_canonical_only(src_db: Path, snap_path: Path) -> None:
    """Copy src_db to snap_path then DROP every candidate_* table and llm_cache, then VACUUM."""
    if snap_path.exists():
        snap_path.unlink()
    # Copy file first — simpler than building from scratch; preserves indexes + views.
    shutil.copyfile(src_db, snap_path)
    with sqlite3.connect(snap_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")  # dropping tables; FK constraints would block
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';"
        )
        for (name,) in cur.fetchall():
            conn.execute(f"DROP TABLE IF EXISTS {name};")  # — name from sqlite_master
        # llm_cache is an extraction implementation detail, not part of the export contract
        conn.execute("DROP TABLE IF EXISTS llm_cache;")
        conn.execute("VACUUM;")


def _count_rows(snap_path: Path) -> dict[str, int]:
    """Return row counts for every table in the snapshot, enumerated dynamically.

    Enumerates via sqlite_master rather than a hardcoded list, so any future
    table added to the canonical schema is counted automatically without touching
    this function.  The snapshot has already had candidate_* and llm_cache tables
    stripped, so dynamic enumeration produces exactly the canonical set.
    """
    counts: dict[str, int] = {}
    with sqlite3.connect(snap_path) as conn:
        table_names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
        ]
        for t in table_names:
            row = conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()
            counts[t] = row[0]
    return counts


def _source_editions(corpus_db: Path) -> dict[str, str]:
    """Pull MAX(source_edition) per corpus from corpus_db if present.

    Returns an empty dict if corpus_db does not exist or lacks the documents table.
    """
    if not corpus_db.exists():
        return {}
    with sqlite3.connect(corpus_db) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents';"
        ).fetchone()
        if not has_table:
            return {}
        rows = conn.execute(
            "SELECT corpus, MAX(source_edition) FROM documents GROUP BY corpus;"
        ).fetchall()
    return {corpus: edition for corpus, edition in rows}
