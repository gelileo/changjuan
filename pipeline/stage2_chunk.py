"""Stage 2 — paragraph-aware chunking with overlap.

A chunk never splits a paragraph mid-text. Chunks accumulate paragraphs until the
target character count is reached, then a new chunk starts. The new chunk's first
paragraph(s) overlap with the prior chunk's last paragraph(s) by approximately
`chunk_overlap_chars` characters — preserving cross-paragraph references for the
LLM extraction stage.

Chunk ids are deterministic: `chk:<document_id>:<paragraph_start>`. This lets
citations encode chunk identity stably across re-runs.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3

from pipeline.config import Config

_PARA_SEP = re.compile(r"\r?\n\s*\r?\n+")


def _split_paragraphs(raw: str) -> list[str]:
    parts = [p.strip() for p in _PARA_SEP.split(raw) if p.strip()]
    return parts


def _chunk_paragraphs(
    paragraphs: list[str], target: int, overlap: int
) -> list[tuple[int, int, str]]:
    """Return list of (paragraph_start, paragraph_end_inclusive, text)."""
    if not paragraphs:
        return []
    chunks: list[tuple[int, int, str]] = []
    i = 0
    n = len(paragraphs)
    while i < n:
        start = i
        running = ""
        end = i
        while end < n and len(running) + len(paragraphs[end]) + 2 <= target:
            running = running + ("\n\n" if running else "") + paragraphs[end]
            end += 1
        if end == start:  # single paragraph longer than target — keep it whole
            running = paragraphs[end]
            end += 1
        chunks.append((start, end - 1, running))
        if end >= n:
            break
        # Walk back paragraphs from end until we've covered ~overlap chars
        back = end
        back_chars = 0
        while back > start + 1 and back_chars < overlap:
            back -= 1
            back_chars += len(paragraphs[back])
        i = back
    return chunks


def chunk_documents(conn: sqlite3.Connection, cfg: Config) -> int:
    """Chunk every document that has no chunks yet. Returns number of chunks written."""
    docs = conn.execute(
        "SELECT id, raw_text FROM documents"
        " WHERE id NOT IN (SELECT DISTINCT document_id FROM chunks);"
    ).fetchall()
    written = 0
    for doc in docs:
        paragraphs = _split_paragraphs(doc["raw_text"])
        for p_start, p_end, text in _chunk_paragraphs(
            paragraphs, cfg.chunk_target_chars, cfg.chunk_overlap_chars
        ):
            chunk_id = f"chk:{doc['id']}:{p_start}"
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            conn.execute(
                "INSERT INTO chunks (id, document_id, paragraph_start, paragraph_end, text, hash) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (chunk_id, doc["id"], p_start, p_end, text, h),
            )
            written += 1
    return written
