from __future__ import annotations

import sqlite3
import uuid


def _audit(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: str,
    change_kind: str,
    after_json: str,
    actor: str,
    pipeline_run_id: str,
    field: str | None = None,
    before_json: str | None = None,
    citation_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log"
        " (id, entity_kind, entity_id, field, change_kind,"
        " before_json, after_json, actor, citation_id, pipeline_run_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        (
            f"al:{uuid.uuid4().hex[:12]}",
            entity_kind,
            entity_id,
            field,
            change_kind,
            before_json,
            after_json,
            actor,
            citation_id,
            pipeline_run_id,
        ),
    )
