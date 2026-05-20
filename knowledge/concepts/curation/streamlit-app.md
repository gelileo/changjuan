---
title: Curation app — Streamlit retrospective review
type: concept
area: curation
updated: 2026-05-20
status: thin
load_bearing: false
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
affects:
  - curation/**/*.py
---

## What it is

The curation app is a single-page Streamlit application run locally by the project's single curator. It reads from and writes to `data/changjuan.sqlite` — the same database produced by the pipeline. It is not a gate on pipeline delivery: the pipeline produces a complete, usable knowledge graph without any human review. The curation app enables retrospective correction and quality uplift at any time after extraction.

## Three review queues

The app presents three queues in priority order:

1. **Unresolved Person merge candidates** — stage 5 produced candidate merges that require human confirmation (e.g., two names that might or might not refer to the same person). Estimated 3–5 min per decision. Built first because stage-5 linking errors compound: a missed merge duplicates every downstream fact about that person.

2. **Open Conflicts** — field-level disagreements between extraction runs (both auto-provenance, similar confidence) that the pipeline flagged for human resolution. Estimated under 1 min per decision. Each Conflict row already carries a `current_best_variant_idx` suggestion based on highest confidence.

3. **Low-confidence extractions** — canonical field values whose confidence is below a configurable threshold (TBD in Phase 2). Estimated under 30 s per decision since these are quick accept/reject judgements.

## Home screen (v1)

The v1 home screen is a 108-cell chapter coverage grid showing extraction status per chapter, three queue entry-point buttons with pending-count badges, and a free-text search box. No headline counters (total persons, total events) are displayed in v1 — those are deferred to Phase 2 once extraction coverage is meaningful.

## Audit and reversibility

Every curator decision writes an `audit_log` row with `change_kind='set'` or `change_kind='resolve'`, `actor='curator'`, and the before/after values. No decision is permanent: the audit log preserves full history and any change can be manually reverted by a curator. The pipeline never overwrites a `provenance='curated'` field silently — disagreements become new Conflict records.

## Phase 1 status

Not yet implemented. `curation/__init__.py` is a placeholder. The curation app is a Phase 2 build target. This article exists so the `curation/**/*.py` drift-check mapping resolves to a valid article from the first Phase 2 commit touching `curation/`.
