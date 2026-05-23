"""Read helpers for the curation app.

Connections opened here are READ-ONLY. Every write path must go through
pipeline.stage5_link.merge (which opens its own write connection).
"""

from __future__ import annotations

import json as _json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pipeline.config import LOW_CONFIDENCE_THRESHOLD


@dataclass(frozen=True)
class MergeCandidateRow:
    mc_id: str
    kind: str
    candidate_a_id: str
    candidate_b_id: str
    score: float
    surface_features_json: str | None
    llm_judgment_json: str | None
    created_at: str


@dataclass(frozen=True)
class ChapterStatus:
    chapter_num: int
    title: str
    extracted: bool
    latest_run_id: str | None


@dataclass(frozen=True)
class ChapterContext:
    citation_id: str
    text: str
    span_start: int
    span_end: int
    paragraphs: list[str]


@contextmanager
def _ro_connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a read-only sqlite connection. Closes on context exit."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def open_merge_candidates(db_path: Path) -> list[MergeCandidateRow]:
    with _ro_connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, kind, candidate_a_id, candidate_b_id, score, "
            "       surface_features_json, llm_judgment_json, created_at "
            "FROM merge_candidates WHERE status = 'open' "
            "ORDER BY created_at ASC"
        ).fetchall()
    return [
        MergeCandidateRow(
            mc_id=r["id"],
            kind=r["kind"],
            candidate_a_id=r["candidate_a_id"],
            candidate_b_id=r["candidate_b_id"],
            score=r["score"],
            surface_features_json=r["surface_features_json"],
            llm_judgment_json=r["llm_judgment_json"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def coverage_stats(db_path: Path, *, corpus_path: Path | None = None) -> list[ChapterStatus]:
    corpus_path = corpus_path or db_path.parent / "corpus.sqlite"
    with _ro_connect(corpus_path) as corpus_conn:
        chapters = corpus_conn.execute(
            "SELECT chapter_num, chapter_title FROM documents ORDER BY chapter_num"
        ).fetchall()
    with _ro_connect(db_path) as canon_conn:
        runs = canon_conn.execute(
            "SELECT id, scope_json FROM pipeline_runs WHERE stage = 'extract'"
        ).fetchall()
    extracted_chapters: dict[int, str] = {}
    for r in runs:
        scope = r["scope_json"] or ""
        try:
            payload = _json.loads(scope)
        except (ValueError, TypeError):
            continue
        ch = payload.get("chapter_num") or payload.get("chapter")
        if isinstance(ch, int):
            extracted_chapters[ch] = r["id"]
    return [
        ChapterStatus(
            chapter_num=c["chapter_num"],
            title=c["chapter_title"] or f"第{c['chapter_num']}回",
            extracted=c["chapter_num"] in extracted_chapters,
            latest_run_id=extracted_chapters.get(c["chapter_num"]),
        )
        for c in chapters
    ]


def low_confidence_count(db_path: Path) -> int:
    with _ro_connect(db_path) as conn:
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM candidate_facts WHERE confidence < ?",
                (LOW_CONFIDENCE_THRESHOLD,),
            ).fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row["n"]) if row else 0


def chapter_citation_context(
    citation_id: str,
    *,
    corpus_path: Path,
    paragraphs_before: int = 2,
    paragraphs_after: int = 2,
) -> ChapterContext:
    """Resolve a citation to its source paragraph + context window.

    Returns ChapterContext(text="(citation not found)") on miss rather than
    raising — evidence-column failure must be non-blocking per spec §5.
    """
    with _ro_connect(corpus_path) as conn:
        row = conn.execute(
            "SELECT c.id, c.span_start, c.span_end, c.quote, c.chunk_id, "
            "       ch.text, ch.document_id, ch.paragraph_start, ch.paragraph_end "
            "FROM citations c JOIN chunks ch ON c.chunk_id = ch.id "
            "WHERE c.id = ?",
            (citation_id,),
        ).fetchone()
    if row is None:
        return ChapterContext(
            citation_id=citation_id,
            text="(citation not found)",
            span_start=0,
            span_end=0,
            paragraphs=[],
        )
    return ChapterContext(
        citation_id=citation_id,
        text=row["quote"],
        span_start=row["span_start"],
        span_end=row["span_end"],
        paragraphs=[row["text"]],
    )
