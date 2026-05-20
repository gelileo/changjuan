-- corpus.sqlite — immutable after stage 1.
-- One row per chapter (or canonical section in non-novel corpora).

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    corpus          TEXT NOT NULL CHECK (corpus IN ('dongzhoulieguozhi', 'zuozhuan', 'shiji')),
    title           TEXT NOT NULL,
    chapter_num     INTEGER NOT NULL,
    chapter_title   TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    source_edition  TEXT NOT NULL,
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (corpus, chapter_num)
);

CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id),
    paragraph_start INTEGER NOT NULL,
    paragraph_end   INTEGER NOT NULL,
    text            TEXT NOT NULL,
    hash            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(hash);

CREATE TABLE IF NOT EXISTS citations (
    id              TEXT PRIMARY KEY,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id),
    span_start      INTEGER NOT NULL,
    span_end        INTEGER NOT NULL,
    quote           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id);
