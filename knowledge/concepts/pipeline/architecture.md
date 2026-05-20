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

## First commitments (true once code lands)

- Stages live under `pipeline/stage{1,2,3,4,5,6,7,9}_*.py`. Stage 8 is the Streamlit curation app under `curation/`.
- LLM cache: `pipeline/llm_cache.py`, keyed by `hash(prompt_template_version, model, input)`.
- Conflict auto-resolution rule: configurable precedence (default 史记 > 左传 > 东周列国志 for dates; 东周列国志 wins narrative detail). The picked variant is recorded in `Conflict.current_best_variant_idx`; alternatives are preserved.
- `pipeline_runs.stats_json.thresholds_breached` is the gate for stage-9 freeze.
- `--chapters N..M` flag on every stage for dry runs; nothing requires "full corpus" mode to run.
