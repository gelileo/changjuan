"""Per-chapter post-load integrity checks.

Used by Phase 4c after each chapter's `extract → link → load` cycle. CLI
wrapper at `scripts/smoke-check-run`.

Exits 0 on pass, 1 on fail. Warnings are non-fatal but logged.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from pipeline.db import open_canonical_db


def smoke_check_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """Run smoke checks for one pipeline_run. Returns a result dict."""
    failures: list[str] = []
    warnings: list[str] = []

    run_row = conn.execute(
        "SELECT id, stats_json FROM pipeline_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if run_row is None:
        return {
            "status": "fail",
            "failures": ["no_pipeline_run"],
            "warnings": [],
            "run_id": run_id,
        }

    stats = json.loads(run_row[1]) if run_row[1] else {}
    dates_out_of_range = stats.get("dates_out_of_range", 0)
    if dates_out_of_range > 0:
        warnings.append("dates_out_of_range")

    # Schema integrity
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        failures.append(f"integrity_check: {integrity}")

    # FK orphan checks for person_relations endpoints
    fk_orphans = 0
    orphan_queries = [
        (
            "person_relations.person_a_id",
            """
            SELECT COUNT(*) FROM person_relations pr
            LEFT JOIN persons p ON p.id = pr.person_a_id
            WHERE p.id IS NULL
        """,
        ),
        (
            "person_relations.person_b_id",
            """
            SELECT COUNT(*) FROM person_relations pr
            LEFT JOIN persons p ON p.id = pr.person_b_id
            WHERE p.id IS NULL
        """,
        ),
        (
            "event_participants.event_id",
            """
            SELECT COUNT(*) FROM event_participants ep
            LEFT JOIN events e ON e.id = ep.event_id
            WHERE e.id IS NULL
        """,
        ),
        (
            "event_participants.person_id",
            """
            SELECT COUNT(*) FROM event_participants ep
            LEFT JOIN persons p ON p.id = ep.person_id
            WHERE p.id IS NULL
        """,
        ),
    ]
    for label, q in orphan_queries:
        try:
            n = conn.execute(q).fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if n > 0:
            fk_orphans += n
            failures.append(f"fk_orphan: {label} ({n})")

    n_persons = conn.execute(
        "SELECT COUNT(*) FROM persons WHERE pipeline_run_id = ?",
        (run_id,),
    ).fetchone()[0]
    if n_persons == 0:
        warnings.append("zero_persons")

    return {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings,
        "run_id": run_id,
        "fk_orphans": fk_orphans,
        "dates_out_of_range": dates_out_of_range,
        "n_persons": n_persons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-root", default=Path.cwd(), type=Path)
    args = parser.parse_args()

    conn = open_canonical_db(args.repo_root / "data" / "changjuan.sqlite")
    result = smoke_check_run(conn, args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
