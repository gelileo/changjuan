"""Stage 1 — Ingest source corpora into corpus.sqlite.

Reads a book's chaptered JSON (located via book_meta) and inserts one `documents`
row per chapter with a stable id `<book_id>:<chapter_num>` so downstream stages
get reproducible references.

Idempotent: re-running over the same corpus has no effect (ON CONFLICT DO NOTHING
on the unique `(corpus, chapter_num)` constraint).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from pipeline.config import Config


def ingest_book(conn: sqlite3.Connection, cfg: Config, book_meta: Mapping[str, object]) -> int:
    """Ingest a book's chaptered JSON into corpus.sqlite. Returns the number of inserts.

    Source + labels come from book_meta: `corpus_dir`/`corpus_json` locate the JSON
    under corpora/, `corpus` is the stamped documents.corpus label. Document ids are
    `<book_id>:<chapter_num>`. Idempotent (ON CONFLICT DO NOTHING on (corpus, chapter_num)).
    """
    corpus = str(book_meta["corpus"])
    src = cfg.corpora_dir / str(book_meta["corpus_dir"]) / "json" / str(book_meta["corpus_json"])
    data = json.loads(src.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    title = str(book_meta.get("title") or data.get("title") or corpus)
    rows = [
        {
            "id": f"{cfg.book_id}:{i + 1}",
            "corpus": corpus,
            "title": title,
            "chapter_num": i + 1,
            "chapter_title": ch["title"],
            "raw_text": ch["content"],
            "source_edition": f"{book_meta['corpus_dir']}/json",
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
        inserted += cur.rowcount
    conn.commit()
    return inserted
