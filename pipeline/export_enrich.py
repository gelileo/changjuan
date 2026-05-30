"""Post-snapshot enrichment passes for the export bundle (stage 9).

Each function mutates the already-copied graph.sqlite in place. Kept separate
from stage9_export.py orchestration so each pass has one responsibility and is
unit-testable without building a full bundle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def build_citations_table(graph_db: Path, corpus_db: Path) -> None:
    """Create `citations` in graph_db, denormalizing each distinct cited chunk's
    passage text from corpus_db's `chunks` table.

    Raises ValueError if any cited chunk id is absent from the corpus (fail loud:
    the reader's one-tap-to-source feature must not silently lose passages).
    """
    with sqlite3.connect(graph_db) as g:
        cited = [r[0] for r in g.execute("SELECT DISTINCT citation_id FROM entity_citations;")]
        g.execute("DROP TABLE IF EXISTS citations;")
        g.execute(
            "CREATE TABLE citations ("
            " citation_id TEXT PRIMARY KEY,"
            " document_id TEXT,"
            " paragraph_start INTEGER,"
            " paragraph_end INTEGER,"
            " text TEXT NOT NULL);"
        )
        if not cited:
            return
        with sqlite3.connect(corpus_db) as cor:
            placeholders = ",".join("?" * len(cited))
            found = {
                cid: (cid, doc, ps, pe, txt)
                for cid, doc, ps, pe, txt in cor.execute(
                    "SELECT id, document_id, paragraph_start, paragraph_end, text "
                    f"FROM chunks WHERE id IN ({placeholders});",
                    cited,
                )
            }
        missing = [c for c in cited if c not in found]
        if missing:
            raise ValueError(
                f"{len(missing)} cited chunk(s) absent from corpus "
                f"(e.g. {missing[:3]}); cannot denormalize citation text."
            )
        g.executemany(
            "INSERT INTO citations VALUES (?,?,?,?,?);",
            [found[c] for c in cited],
        )
