---
title: 红楼梦 corpus (book_id hlm)
affects:
  - corpora/hlm/**
  - corpora/**/红楼梦*
status: ingestable (Plan 3a complete)
---

# 红楼梦 corpus

The 红楼梦 (Dream of the Red Chamber) source for the forthcoming **cast** genre
profile (Plan 3). `book_id` = `hlm`.

## Source

Cloned from `https://github.com/EaconTang/gitbook-hongloumeng` as a sibling repo
at `unroll/gitbook-hongloumeng`, symlinked into the pipeline as
`corpora/hlm` → `../../gitbook-hongloumeng` (mirrors the `corpora/dongzhoulieguozhi`
pattern). We use the **程高本** edition under `ch_cgb/` — the complete **120 回**
(`001.md`–`120.md`). The 脂评本 under `ch/` is not used.

## Shape for ingest

Each `ch_cgb/NNN.md` is `### 第N回 <title>` + a `----` rule + prose wrapped in
`<p>`/`<blockquote>` HTML. A one-off converter (`/tmp/build_hlm_json.py`) produced
`corpora/hlm/json/红楼梦.json` in the canonical shape stage-1 reads
(`{title, chapters:[{title, content}]}`): title from the `###` line, content =
`<p>` paragraphs with tags stripped to clean prose joined by newlines. Result:
120 chapters, ~864K chars, only ~5 chars of non-`<p>` text dropped across the
whole novel. The generated JSON lives inside the clone (not committed to changjuan).

## Status

**Ingestable (Plan 3a complete).** `changjuan ingest --book-id hlm` reads
`corpus_dir`/`corpus_json` from `data/books/hlm/book-meta.json` and populates
`data/books/hlm/corpus.sqlite` with 120 documents (corpus label `honglou`,
ids `hlm:1`–`hlm:120`). `changjuan chunk --book-id hlm` produces 835 chunks
(paragraph-aware; avg ~7 chunks/chapter across ~864K chars). Both commands are
idempotent. Integration test: `tests/integration/test_hlm_ingest.py::test_hlm_ingest_120_chapters`.

红楼梦 is the `cast`-profile test book (huge cast, dense kin/romance relations,
no historical chronology) — see [[../pipeline/profiles]] and the design spec
`docs/superpowers/specs/2026-06-10-capability-genre-profiles-design.md`.

## Infrastructure prep (Plan 3 Task 2)

The `pipeline/schemas/corpus_schema.sql` CHECK constraint on `documents.corpus` — which
hardcoded the enum `('dongzhoulieguozhi', 'zuozhuan', 'shiji')` — was removed to allow
the corpus label to be a free string. This enables hlm (and future Plan 3+ books) to be
registered without schema changes. The `UNIQUE (corpus, chapter_num)` uniqueness constraint
remains and enforces the actual invariant (no duplicate chapters per book).
