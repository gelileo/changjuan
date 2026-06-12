---
title: 红楼梦 corpus (book_id hlm)
affects:
  - corpora/hlm/**
  - corpora/**/红楼梦*
status: staged (not yet ingestable — see below)
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

**Staged, not yet ingestable.** Stage-1 ingest is still hardwired to the dzl JSON
path; reading `corpora/hlm` requires the **ingest generalization** that is Plan 3's
first code task. 红楼梦 is the `cast`-profile test book (huge cast, dense kin/
romance relations, no historical chronology) — see
[[../pipeline/profiles]] and the design spec
`docs/superpowers/specs/2026-06-10-capability-genre-profiles-design.md`.
