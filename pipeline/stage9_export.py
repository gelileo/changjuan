"""Stage 9 — Freeze and export.

Produces `out_dir/` with:
- manifest.json: version, schema_version, generated_at, counts per canonical table,
  source corpus editions
- changjuan.sqlite: read-only snapshot with candidate_* tables prefix-excluded and
  llm_cache excluded
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_CANONICAL_TABLES = (
    "persons",
    "person_variants",
    "states",
    "state_capitals",
    "places",
    "events",
    "event_participants",
    "event_places",
    "event_relations",
    "person_relations",
    "person_states",
    "entity_citations",
    "conflicts",
    "audit_log",
    "pipeline_runs",
    "merge_candidates",
    "qa_samples",
)

SCHEMA_VERSION = 1


def export_bundle(src_db: Path, out_dir: Path, *, version: str) -> Path:
    """Export a versioned bundle: manifest.json + canonical-only sqlite snapshot.

    Returns out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    snap_path = out_dir / "changjuan.sqlite"
    _snapshot_canonical_only(src_db, snap_path)

    counts = _count_rows(snap_path)
    manifest: dict[str, object] = {
        "version": version,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": counts,
        "source_corpus_editions": _source_editions(src_db),
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
    """Return row counts for every canonical table that exists in the snapshot."""
    counts: dict[str, int] = {}
    with sqlite3.connect(snap_path) as conn:
        for t in _CANONICAL_TABLES:
            row = conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()
            counts[t] = row[0]
    return counts


def _source_editions(src_db: Path) -> dict[str, str]:
    """Pull MAX(source_edition) per corpus from the sibling corpus.sqlite if present.

    Returns an empty dict if corpus.sqlite does not exist next to src_db.
    """
    corpus_db = src_db.parent / "corpus.sqlite"
    if not corpus_db.exists():
        return {}
    with sqlite3.connect(corpus_db) as conn:
        rows = conn.execute(
            "SELECT corpus, MAX(source_edition) FROM documents GROUP BY corpus;"
        ).fetchall()
    return {corpus: edition for corpus, edition in rows}
