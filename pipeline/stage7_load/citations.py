"""entity_citations accumulator. Idempotent: same (entity_kind, entity_id, citation_id)
inserts once and is a no-op on repeat.

The entity_citations table has PRIMARY KEY (entity_kind, entity_id, citation_id) which
acts as the unique constraint; INSERT OR IGNORE exploits this for idempotence.
"""

from __future__ import annotations

import sqlite3


def record_citation(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: str,
    citation_id: str,
) -> None:
    """Insert an entity_citations row; idempotent on the unique (kind, id, citation) tuple."""
    conn.execute(
        """INSERT OR IGNORE INTO entity_citations (entity_kind, entity_id, citation_id)
           VALUES (?, ?, ?)""",
        (entity_kind, entity_id, citation_id),
    )
