---
title: Stage 7 load-and-merge semantics
type: concept
area: pipeline
updated: 2026-05-21
implemented: Task 20 (variant-aware matching); Phase 1 code-review fixes; Task 5 Phase 2 (citation accumulation); Task 16 Phase 2 (load_candidate_places)
status: thin
load_bearing: true
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/stage7_load/**
  - pipeline/stage7_load/citations.py
---

## What this is

Stage 7 (`pipeline/stage7_load.py`) is the boundary between the candidate staging area and the canonical knowledge graph. It promotes `candidate_persons` rows into `persons`, applying field-level merge semantics when a candidate matches an existing canonical record.

## Matching rules

Candidate records are matched against existing canonical Persons by two checks applied in order:

1. **canonical_name equality** — if a Person with the same `canonical_name` exists, the candidate merges into it.
2. **person_variants lookup** — if the candidate's `canonical_name` appears as a `variant` in `person_variants`, the candidate merges into the owning Person.

If neither check finds a match, a new canonical Person is created with id `per:<slug>` where the slug is derived from `canonical_name` via `_slugify` (regex `[^\w]+` → `-`, lowercased). If that id already exists in `persons` (slug collision from a different `canonical_name`), a 6-character SHA-256 hex suffix is appended: `per:<slug>-<hash6>`.

## Provenance: auto vs curated

Every canonical record carries `provenance ∈ {auto, curated}`. The load stage only creates records with `provenance='auto'`. Curated records are set by a human curator via the curation app and are never silently overwritten by re-extraction.

## Scalar merge rules

When a candidate matches an existing Person, each scalar field (`gender`, `birth_date_json`, `death_date_json`, `notes`, `state_id`, `clan_name`) is merged independently:

- **Skip if candidate value is None** — no change.
- **Skip if old == new** — already in sync. For `*_json` fields, equality is checked semantically (deserialize both JSON strings and compare as Python dicts/lists via `_scalars_equal`), so different key orderings of the same object do not produce a spurious Conflict.
- **Set if old is None** — first non-null value wins; logged as `change_kind='set'` in `audit_log`.
- **Curated provenance** — if the existing Person is `provenance='curated'`, any disagreement emits a `Conflict` record instead of overwriting.
- **Both auto, new confidence > prior field confidence + 0.1** — update the field; logged as `change_kind='set'`. The "prior field confidence" is read from the most recent `set`-event in `audit_log` for this field (via `_last_field_confidence`); if no prior set-event exists, the row-level `persons.confidence` is used as the fallback.
- **Otherwise** — emit a `Conflict` record (both values, both confidences, `resolution_rule='highest_confidence'`, `status='open'`).

The confidence delta threshold is `_SIMILAR_CONFIDENCE_DELTA = 0.1`. Below this margin the new extraction is not considered meaningfully better, so disagreement is flagged for human review.

## Conflict emission

A `Conflict` row records both variants with their confidence and source, and sets `current_best_variant_idx` to the index (0 or 1) of the higher-confidence variant. This gives the curation app a pre-scored suggestion without requiring human intervention for every disagreement.

## Citation accumulation

`pipeline/stage7_load/citations.py::record_citation` is called from every Person create/update path. The function is idempotent on the unique `(entity_kind, entity_id, citation_id)` tuple — re-loading the same candidate twice writes one `entity_citations` row, not two. Every appearance of an entity in a new chunk accumulates a citation; nothing overwrites. The `field_history` view (Phase 1) joins on `entity_citations` to render "how do we know this?" in the future curation UI.

Each `candidate_persons` row carries a `chunk_id`; `record_citation` stores this as the `citation_id` in `entity_citations`. The `entity_citations` PRIMARY KEY `(entity_kind, entity_id, citation_id)` doubles as the unique constraint that `INSERT OR IGNORE` exploits for idempotence.

## Variant union

When a candidate's `canonical_name` is already a `variant` of an existing Person, the loader maps to that Person and calls `_merge_scalar_fields`. No duplicate variant rows are created. New variant proposals from Phase 2 linking (stage 5) will extend `person_variants` separately.

## Audit log

Every create and every scalar field set emits an `audit_log` row with:
- `entity_kind='person'`
- `change_kind ∈ {'create', 'set'}`
- `actor='load@v1'`
- `after_json={"value": ..., "confidence": ...}` for field-level sets; `{"canonical_name": ..., "confidence": ...}` for creates.

The `field_history` view reconstructs per-field history from these rows.

## Per-field confidence lookup

`_last_field_confidence(conn, entity_kind, entity_id, field)` queries `audit_log` for the most recent `set`-event for a given field and returns the `confidence` extracted from `after_json`. This prevents a stale row-level confidence (set at Person creation time) from being used as the comparison baseline in multi-run scenarios where a high-confidence update has already occurred.

## Places

`pipeline/stage7_load/places.py::load_candidate_places` mirrors the persons loader but is simpler — there is no variants table for places. Candidates are matched against existing canonical `places` rows by `name` equality only. If no match exists, a new Place is created with id `pla:<slug>`, with the same SHA-256 hex-suffix collision guard as persons.

Scalar fields merged: `type`, `lat`, `lon`, `coord_confidence`, `modern_equiv`. The merge rules are identical to persons: skip if candidate value is `None`; set unconditionally if existing value is `None`; otherwise apply the `_SIMILAR_CONFIDENCE_DELTA = 0.1` threshold using per-field confidence from `audit_log` (via `_last_field_confidence`). Conflict emission is not implemented for places in this phase (places are auto-only at this stage and have no curation path yet). Citation accumulation works identically — `record_citation(conn, "place", place_id, chunk_id)` is called for every candidate, whether it created or merged.

Every create emits `audit_log` with `change_kind='create'` and `after_json={"value": name, "confidence": ...}`. Every scalar field update emits `change_kind='set'` with the new value and confidence.

## What would invalidate this article

- Adding a new entity kind to the load stage (events, states).
- Changing the confidence-delta threshold.
- Curated records becoming mergeable under any condition.
- Citation accumulation being added to this stage.
- Adding a place-variants table (would require match-by-variant logic like persons).
