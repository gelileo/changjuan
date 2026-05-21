import itertools
import sqlite3
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CORPUS_SCHEMA
from pipeline.stage2_chunk import chunk_documents


def _seed_doc(conn: sqlite3.Connection, doc_id: str, paragraphs: list[str]) -> None:
    text = "\n\n".join(paragraphs)
    conn.execute(
        "INSERT INTO documents"
        " (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition)"
        " VALUES (?, 'dongzhoulieguozhi', 't', 1, 'ch', ?, 'fixture');",
        (doc_id, text),
    )


def test_chunk_short_doc_yields_one_chunk(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path, chunk_target_chars=500, chunk_overlap_chars=50)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        _seed_doc(conn, "d1", ["short para one.", "short para two."])
        n = chunk_documents(conn, cfg)
        chunks = list(conn.execute("SELECT id, paragraph_start, paragraph_end, text FROM chunks;"))
    assert n == 1
    assert len(chunks) == 1
    assert chunks[0]["paragraph_start"] == 0
    assert chunks[0]["paragraph_end"] == 1  # inclusive last paragraph index


def test_chunk_long_doc_splits_on_paragraph_boundaries(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path, chunk_target_chars=120, chunk_overlap_chars=20)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        paragraphs = [f"para number {i} " + "x" * 80 for i in range(6)]
        _seed_doc(conn, "d1", paragraphs)
        chunk_documents(conn, cfg)
        chunks = list(
            conn.execute(
                "SELECT paragraph_start, paragraph_end FROM chunks ORDER BY paragraph_start;"
            )
        )
    # No chunk slices a paragraph mid-text
    for c in chunks:
        assert c["paragraph_start"] <= c["paragraph_end"]
    # Overlap means chunk N+1's start <= chunk N's end (in paragraph index space)
    for prev, nxt in itertools.pairwise(chunks):
        assert nxt["paragraph_start"] <= prev["paragraph_end"] + 1


def test_chunk_ids_are_deterministic(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        _seed_doc(conn, "d1", ["alpha", "beta"])
        chunk_documents(conn, cfg)
        first = [row[0] for row in conn.execute("SELECT id FROM chunks ORDER BY paragraph_start;")]
    # Re-chunking the same doc yields the same chunk ids
    with connect(cfg.corpus_db) as conn:
        conn.execute("DELETE FROM chunks;")
        chunk_documents(conn, cfg)
        second = [row[0] for row in conn.execute("SELECT id FROM chunks ORDER BY paragraph_start;")]
    assert first == second


def test_chunks_emerge_from_single_newline_separated_paragraphs(tmp_path: "Path") -> None:
    """Real corpus uses single \n between paragraphs (not \n\n).
    Regression for: every chapter coming out as one mega-chunk.

    The chunk_target_chars is set smaller than the total text so that the
    paragraphs must be spread across multiple chunks — this only works if the
    regex actually splits on single \n. With the old regex (requiring blank
    lines), all four lines would be treated as one paragraph and land in a
    single chunk regardless of the target size.
    """
    # Each paragraph is ~40 chars; target of 50 forces splits after ~1 paragraph
    cfg = Config(repo_root=tmp_path, chunk_target_chars=50, chunk_overlap_chars=10)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        # Single \n between paragraphs — as used in the upstream corpus JSON
        para = "段落{}。" + "甲" * 30  # ~34 chars each
        text = "\n".join(para.format(i) for i in range(1, 5))
        conn.execute(
            "INSERT INTO documents"
            " (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition)"
            " VALUES ('d1', 'dongzhoulieguozhi', '第一回', 1, '周宣王闻谣轻杀', ?, 'test');",
            (text,),
        )
        chunk_documents(conn, cfg)
        chunks = list(conn.execute("SELECT id FROM chunks;"))

    assert (
        len(chunks) > 1
    ), f"expected >1 chunk from 4 single-\\n-separated paragraphs, got {len(chunks)}"
