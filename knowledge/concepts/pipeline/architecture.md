---
title: Automation-first pipeline architecture
type: concept
area: pipeline
updated: 2026-05-20
status: thin
load_bearing: true
references:
  - concepts/data-model/knowledge-graph.md
  - concepts/verification/confidence-and-invariants.md
affects:
  - pipeline/config.py
  - pipeline/stage1_ingest.py
  - pipeline/stage2_chunk.py
  - pipeline/stage4_normalize.py
  - pipeline/stage7_load.py
  - pipeline/stage9_export.py
---

## What this is

The pipeline that produces the knowledge graph is a 9-stage sequential ETL: **Ingest → Chunk → Extract (LLM) → Normalize → Link & dedup (LLM) → Cross-canon check (LLM, gated) → Load → Curate (human, optional) → Freeze & export**. Each stage has typed inputs/outputs, is idempotent over its input, and is resumable from the last successful chunk. Three stages are LLM-driven (3, 5, 6) and share a content-hash cache; the rest are deterministic Python. The load-bearing rule is that **every stage produces a complete, usable best-guess result without any human in the loop**. Curation is purely retrospective: a curator can revisit and correct any record at any time, but no stage waits for human input. The output `data/changjuan.sqlite` is queryable end-to-end after any stage-7 load, with or without curation.

## Why this shape, not the alternatives

A single-LLM-agent pipeline (one tool-using agent decides everything per chapter) was considered and rejected — hard to evaluate, hard to cache, hard to tune one capability without breaking another, non-deterministic failures. A "curate-as-you-go" pipeline where human review gates downstream stages was considered and rejected because the user is one person extracting from 108 chapters plus 左传/史记; making curation mandatory would mean the system is unusable until hundreds of hours of review are done. Optional retrospective curation lets the system deliver value immediately and improve incrementally.

## What would invalidate this article

- Any stage starting to require human input to complete.
- "Current best variant" auto-resolution becoming impossible for some class of disagreement.
- Curator overrides ever getting silently overwritten by re-extraction (they don't; divergences become Conflict records).
- A new corpus that can't be added without redesigning stages 1–2.

## Stage 4 — normalize

`pipeline/stage4_normalize.py` provides `normalize_date_string(original, anchor_json=None) -> str`, a thin wrapper over `pipeline.dates.parse_date`. Callers pass a raw date string and optionally a prior date's JSON (for relative references); the function returns a JSON string ready to insert into any `*_date_json` column. This is the only stage-4 entry point in Phase 1; extraction prompts and batch normalization land in Phase 2.

## Stage 9 — dynamic table enumeration in counts

`_count_rows` in `stage9_export.py` enumerates tables via `sqlite_master` rather than a hardcoded list, matching the same dynamic approach used in `_snapshot_canonical_only`. Since the snapshot has `candidate_*` and `llm_cache` already stripped, the dynamic set equals the canonical set exactly. No separate constant to keep in sync.

## Stage 7 — per-field confidence lookup

`_merge_scalar_fields` consults `_last_field_confidence` (an `audit_log` query) to determine the prior confidence for each scalar field before deciding whether to update or emit a Conflict. This prevents the stale row-level `persons.confidence` from being used as the baseline after a high-confidence update has already occurred in a previous run. If no prior set-event exists for the field, the row-level confidence is used as fallback.

## Stage 7 — slug collision guard

`load_candidate_persons` derives each new Person's id as `per:<slug>`. If that id is already held by a *different* Person (slug collision from distinct names), the loader appends a 6-character SHA-256 hex suffix: `per:<slug>-<hash6>`. This is a defensive correctness guarantee; in practice the matcher merges same-name candidates before this path is reached, but it prevents a `PRIMARY KEY` crash when two distinct canonical names happen to produce the same ASCII slug.

## First commitments (true once code lands)

- Stages live under `pipeline/stage{1,2,3,4,5,6,7,9}_*.py`. Stage 8 is the Streamlit curation app under `curation/`.
- LLM cache: `pipeline/llm_cache.py`, keyed by `hash(prompt_template_version, model, input)`.
- Conflict auto-resolution rule: configurable precedence (default 史记 > 左传 > 东周列国志 for dates; 东周列国志 wins narrative detail). The picked variant is recorded in `Conflict.current_best_variant_idx`; alternatives are preserved.
- `pipeline_runs.stats_json.thresholds_breached` is the gate for stage-9 freeze.
- `--chapters N..M` flag on every stage for dry runs; nothing requires "full corpus" mode to run.
