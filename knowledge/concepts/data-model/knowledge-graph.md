---
title: Knowledge graph — entities, relations, citations
type: concept
area: data-model
updated: 2026-05-21 (Task 8)
status: thin
load_bearing: true
references:
  - concepts/pipeline/architecture.md
  - concepts/verification/confidence-and-invariants.md
affects:
  - pipeline/schemas/corpus_schema.sql
  - pipeline/schemas/canonical_schema.sql
  - pipeline/stage5_link/**
---

## What this is

The output of `changjuan` is a typed knowledge graph of Eastern-Zhou history, built from 《东周列国志》 and validated against 《左传》 / 《史记》. Six entity types — **Person, State, Place, Event, Citation, Conflict** — connected by typed relations (`event_participants`, `person_relations` including `clan_member`, `person_states`, `event_places`, `state_capitals`, …). A `Family` entity was considered and deferred; clan/lineage facts ride on `Person.clan_name` + `person_relations(kind="clan_member")` until the data demands promotion. Every entity and every relation carries at least one **citation** (a verbatim quote span in a source corpus), a deterministic-computed **confidence** score, and full **audit history**. Dates are structured values (`year_bce`, `uncertainty`, `original`, `era`, `inference_kind`), never primitives. Name variants are first-class on Person — `重耳`, `晋文公`, `公子重耳` resolve to one id.

## Why this shape, not the alternatives

A flat events table would be cheap but useless for the eventual map UI — readers can't traverse "where was 重耳 in 645 BCE?" without a Person-with-trajectory model. A document-oriented store (one JSON per chapter) would make linking across chapters impossible — and almost every interesting fact in this corpus is cross-chapter. The relational schema costs upfront complexity but enables every reader question we want to answer later.

## entity_citations table

`entity_citations(entity_kind, entity_id, citation_id)` is the citation accumulator for all canonical records. The `entity_kind` CHECK constraint (Task 19) covers four entity kinds (`person`, `state`, `place`, `event`) and six relation kinds (`event_participant`, `event_place`, `event_relation`, `person_relation`, `person_state`, `state_capital`). For relation rows (which have composite PKs and no surrogate `id`), `entity_id` is a synthetic string formed by joining the composite key elements with `:` — e.g. `evt:1:per:a:主将` for an event_participant row.

## What would invalidate this article

- A class of historical fact in the source that doesn't fit one of {Person, State, Place, Event, person_relation, Citation, Conflict}. (Family entity sits in the promotion-path queue; promotion is not invalidation.)
- A "fact" in the canonical store without a citation.
- A date whose uncertainty cannot be represented.
- Two records that should be the same id but cannot be merged because the model lacks a variant kind, role, or relation `kind`.
- Adding a new relation kind not covered by the `entity_citations.entity_kind` CHECK constraint.

## First commitments (true once code lands)

- SQLite schema in `pipeline/schemas/canonical_schema.sql` and loader in `pipeline/stage7_load.py`. Tables enumerated in the design spec §5. Schema is split into two committed parts: entity + relation tables (Task 9) and candidate staging + bookkeeping + `field_history` view (Task 10).
- Candidate staging tables (`candidate_persons`, `candidate_events`, etc.) are the unvetted extractor output; stage 7 merges them into canonical tables with full conflict detection. `candidate_persons` carries a `variants_json` column (Task 38) — a JSON array of `{"variant": str, "kind": str}` objects copied from the extraction payload and promoted to `person_variants` by `load_candidate_persons`.
- `audit_log` stores field-level changes as `{value, confidence}` JSON in `after_json`; the `field_history` view reconstructs per-field history without a redundant blob on entity rows. Index on `(entity_kind, entity_id, field)` keeps the view fast.
- Person identity rule: `canonical_name` + `variants[]` with `kind ∈ {本名, 字, 谥号, 封号, 别名}`.
- Person carries an optional `social_category` enum (royalty / noble / official / military / religious / clergy / commoner / servant / foreign / mythic / unknown). Added 2026-05-21 after annotating golden Ch.1 exposed that unnamed-but-acting figures (老宫人, 女婴, 妇人, 男子) have no state-office to put in `person_states.role` — the field is too narrow for coarse social class. `social_category` is independent of `person_states.role`: specific positions (太宰, 大宗伯, etc.) remain in `person_states.role`; `social_category` applies even when no state-role record exists. Optional in the schema — a record may omit it — but expected to be filled by the extractor whenever the text provides a clue.
- Every relation row carries its own `citation_id`, `confidence`, `provenance` — not just entities.
- Date type: `{year_bce, uncertainty (point|range|circa), year_bce_end?, original, era, inference_kind}`.
- Stable IDs are human-readable slugs (`per:jin-wen-gong`, `evt:cheng-pu-zhi-zhan-632bce`), seeded from curated `canonical_name`.

## person_match_score and identity scoring (Phase 3 Task 6)

`pipeline/stage5_link/scoring.py` provides `person_match_score(a, b)` — a pure function that returns `{score: float, features: dict}`. The scorer is the central identity-judgement kernel: it answers "how likely are two Person records the same entity?" without touching the database. Hard veto when no name overlap exists; otherwise a weighted sum over five dimensions (variant_overlap, state_agreement, clan_agreement, social_category_agreement, temporal_proximity) clamped to [0, 1]. All five dimensions are **independent**: temporal contributions (+0.10 compatible, −0.30 conflict) apply regardless of variant_overlap level — spec §4 regression walkthrough (召公奭↔召虎: partial + state same + conflict = 0.10) confirms this. The score feeds the linker dispatch dial in `pipeline/stage5_link/linker.py` (Task 8): ≥0.75 → auto-merge, 0.40–0.75 → human queue, <0.40 → treat as new record. Full formula documented in `concepts/pipeline/linking.md` (Task 12).

## candidate_person_variants table (Phase 3 Task 7, hardened Task 7 fix)

`candidate_person_variants(id, candidate_person_id, variant, kind)` gives the Stage 5 linker structured SQL access to candidate-side name variants, enabling efficient name-overlap pre-filtering via JOIN without deserializing JSON. The table complements (does not replace) `candidate_persons.variants_json` — Phase 2's JSON column stays; Phase 4 may migrate Stage 3 to populate this table directly instead. For Phase 3, the linker tests and Task 14's integration test write directly to this table.

`candidate_person_id` carries a FOREIGN KEY to `candidate_persons(id)`, mirroring the `person_variants.person_id → persons(id)` constraint (added in Task 7 fix; the initial schema omitted the FK). Two indices exist:
- `idx_candidate_person_variants_variant` — keeps the cross-table name-overlap JOIN fast.
- `idx_candidate_person_variants_candidate_id` — avoids a full-scan on the per-row `SELECT variant FROM candidate_person_variants WHERE candidate_person_id = ?` lookup inside `_load_candidate()`.

## link_run orchestrator and _denormalize_variants (Phase 3 Task 8)

`pipeline/stage5_link/linker.py::link_run(conn, pipeline_run_id)` is the Stage 5 dispatch loop. It walks all `candidate_persons` rows for the run, scores each against its `candidate_pool`, and dispatches:

- **score ≥ 0.75**: writes `match_target_id` on the candidate row + an `audit_log` row with `change_kind='set'`, `actor='link@v1'`.
- **0.40 ≤ score < 0.75**: writes a `merge_candidates` row with `kind='person'`, `status='open'`.
- **score < 0.40**: no action (candidate creates a new canonical record at load time).

`_denormalize_variants(conn, pipeline_run_id)` bridges Phase 2 and Phase 3: Phase 2's stage 3 writes variants only to `candidate_persons.variants_json` (a JSON array column); Phase 3's `candidate_pool` reads the structured `candidate_person_variants` table. `_denormalize_variants` runs idempotently at the start of every `link_run` call, copying any unpopulated variants from `variants_json` into the structured table. Cross-run sibling matches are recorded as `match_target_id` pointing at the sibling candidate id; Stage 7's chain helper (Task 10) resolves to canonical at load time.

**Stats reconciliation invariant (Phase 3 Task 8 fix):** `link_run` returns a stats dict where `candidates_processed == auto_merges + queued + skipped`. The `already_matched` short-circuit (skipping same-run siblings that already became a match target) now correctly bumps `skipped` before continuing, so the invariant holds for cross-run sibling merges.

## candidate_persons.match_target_id (Phase 3)

`candidate_persons.match_target_id` is a nullable TEXT column added in Phase 3 Task 1. It is populated by Stage 5 (linker, see `concepts/pipeline/linking.md`) after the linker identifies a canonical or sibling-candidate identity for this record. The value may be either a canonical `persons.id` slug (e.g. `per:jin-wen-gong`) or the `id` of a sibling `candidate_persons` row from the same pipeline run that the linker has decided is the same entity. Stage 7 honors this column during the candidate-promotion pass: when `match_target_id` is set, Stage 7 routes the candidate's data into the identified target record via field-merge logic and uses the target's `canonical_name` as the fallback name rather than minting a new slug. No foreign-key constraint is applied — an FK would reject rows whose target is a sibling candidate not yet promoted to canonical at insert time (spec §6 anti-pattern: "no FK on match_target_id").
