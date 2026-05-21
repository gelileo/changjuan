"""Stage 1 — Ingest source corpora into corpus.sqlite.

Reads the upstream dongzhoulieguozhi repo's pre-built JSON (`json/东周列国志.json`)
which holds one entry per chapter. Inserts one `documents` row per chapter with a
stable id `dzl:<chapter_num>` so downstream stages get reproducible references.

Idempotent: re-running over the same corpus has no effect (ON CONFLICT DO NOTHING
on the unique `(corpus, chapter_num)` constraint).
"""

from __future__ import annotations

import json
import sqlite3

from pipeline.config import Config


def ingest_dongzhoulieguozhi(conn: sqlite3.Connection, cfg: Config) -> int:
    """Ingest 东周列国志. Returns the number of actual inserts.

    Idempotent: re-ingesting existing chapters is a no-op (ON CONFLICT DO NOTHING
    on the unique (corpus, chapter_num) constraint).
    """
    src = cfg.corpora_dir / "dongzhoulieguozhi" / "json" / "东周列国志.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    rows = [
        {
            "id": f"dzl:{i + 1}",
            "corpus": "dongzhoulieguozhi",
            "title": data.get("title", "东周列国志"),
            "chapter_num": i + 1,
            "chapter_title": ch["title"],
            "raw_text": ch["content"],
            "source_edition": "dongzhoulieguozhi/json (upstream repo)",
        }
        for i, ch in enumerate(chapters)
    ]
    inserted = 0
    cur = conn.cursor()
    for row in rows:
        cur.execute(
            """
            INSERT INTO documents
                (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition)
            VALUES
                (:id, :corpus, :title, :chapter_num, :chapter_title, :raw_text, :source_edition)
            ON CONFLICT (corpus, chapter_num) DO NOTHING;
            """,
            row,
        )
        inserted += cur.rowcount  # 1 on insert, 0 on conflict-ignored
    conn.commit()
    return inserted
