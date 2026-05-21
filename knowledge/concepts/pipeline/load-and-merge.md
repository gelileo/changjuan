---
title: Stage 7 load-and-merge semantics
type: concept
area: pipeline
updated: 2026-05-21
implemented: Task 20 (variant-aware matching); Phase 1 code-review fixes; Task 5 Phase 2 (citation accumulation); Task 16 Phase 2 (load_candidate_places); Task 17 Phase 2 (load_candidate_states); Task 18 Phase 2 (load_candidate_events + merge_date_field); Task 19 Phase 2 (load_candidate_relations)
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

## States

`pipeline/stage7_load/states.py::load_candidate_states` mirrors `places.py` exactly, adapted for the `states` table. Candidates are matched against existing canonical `states` rows by `name` equality only. If no match exists, a new State is created with id `sta:<slug>`, using the same SHA-256 hex-suffix collision guard.

Scalar fields merged: `type`, `ruling_clan`, `founded_date_json`, `ended_date_json`. For the date JSON fields (`founded_date_json`, `ended_date_json`), the same opaque-string merge rule applies as for other scalars: skip if `None`; set unconditionally if existing value is `None`; otherwise apply the `_SIMILAR_CONFIDENCE_DELTA = 0.1` threshold using per-field confidence from `audit_log`. A dedicated `merge_date_field` helper (Task 18) will later provide semantic date-aware merging; for now the simple higher-confidence-wins rule is used. The `state_capitals` relation table (a separate join table between states and places) is not populated here — that is handled in Task 19 (`load_candidate_relations`). Citation accumulation works identically: `record_citation(conn, "state", state_id, chunk_id)` is called for every candidate. Every create emits `audit_log` with `change_kind='create'`; every field update emits `change_kind='set'`.

## Events

`pipeline/stage7_load/events.py::load_candidate_events` introduces a **composite match key**: `(type, year_bce, primary_place_id)`. Two candidates with the same event type, year extracted from `date_json`, and primary place collapse into one canonical event.

`year_bce` is extracted from the candidate's `date_json` column via Python JSON parsing (`_year_bce_from_date_json`). SQLite `json_extract` is used in the match query to locate an existing event by composite key.

**ID format:** `evt:<slug>-<year>bce` when a year is present (e.g. `evt:战-632bce`); `evt:<slug>` when no year. Slug is derived from `type` via `_slugify`. SHA-256 6-char suffix collision guard applies as with persons/places/states.

**Scalar fields merged:** `type`, `outcome`, `summary`, `primary_place_id`. These use the same merge rule as persons: skip if None; set unconditionally if existing is None; emit Conflict if curated; apply `_SIMILAR_CONFIDENCE_DELTA = 0.1` threshold for auto provenance — emit Conflict if new confidence is not clearly higher.

**date_json is merged via `merge_date_field` (spec §7.2)**: a more-precise date (point > circa > range per `_PRECISION_RANK`) wins over a less-precise one, even if it arrives at slightly lower confidence (within `_SIMILAR_CONFIDENCE_DELTA`). On equal precision, higher confidence wins; on tie, the current value is kept.

## `merge_date_field` helper

`pipeline/stage7_load/helpers.py::merge_date_field` is the shared date-merge helper introduced in Task 18. Signature:

```python
def merge_date_field(
    current: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any] | None:
```

Each argument is `{"value": DateDict, "confidence": float}` or `None`. The function returns the winner dict (or None if both are None).

`_PRECISION_RANK = {"point": 3, "circa": 2, "range": 1}`. A higher rank = more precise. The rule:
1. If `new_prec > cur_prec` AND `new_conf >= cur_conf - _SIMILAR_CONFIDENCE_DELTA` → new wins.
2. If `cur_prec > new_prec` AND `cur_conf >= new_conf - _SIMILAR_CONFIDENCE_DELTA` → current wins.
3. Otherwise: higher confidence wins; tie → current wins.

This helper is designed to be re-used by any future loader that merges date fields (e.g. states' `founded_date_json`/`ended_date_json`, persons' `birth_date_json`/`death_date_json`).

## Relations

`pipeline/stage7_load/relations.py::load_candidate_relations` dispatches to six kind-specific loaders in order: event_participants, event_places, event_relations, person_relations, person_states, state_capitals. Returns total candidate rows processed.

All six relation kinds are **append-mostly**: the unique tuple key deduplicates canonical rows; citations accumulate across runs via `record_citation`.

### entity_citations extension

`entity_citations.entity_kind` CHECK constraint (schema Task 19) was extended to include all six relation kinds alongside the four entity kinds. Relation rows have composite PKs (no surrogate `id`); citation tracking uses a synthetic `entity_id` string formed by joining the composite key parts with `:` — e.g. `evt:1:per:a:主将` for an event_participant row.

### Per-kind unique keys

| Kind | Canonical table | Unique key | Candidate table |
|---|---|---|---|
| event_participant | `event_participants` | `(event_id, person_id, role)` | `candidate_event_participants` |
| event_place | `event_places` | `(event_id, place_id, role)` | `candidate_event_places` |
| event_relation | `event_relations` | `(from_event_id, to_event_id, kind)` | `candidate_event_relations` |
| person_relation | `person_relations` | `(from_person_id, to_person_id, kind)` | `candidate_person_relations` |
| person_state | `person_states` | `(person_id, state_id, role, from_date_json)` | `candidate_person_states` |
| state_capital | `state_capitals` | — | _no staging table; stub returns 0_ |

### person_relation contradiction detection

For **directional** relation kinds (`parent`, `child`, `killed_by`, `ruler`, `minister`, `mentor`), when the incoming candidate `(A, B, kind)` would create a new canonical row and the inverse `(B, A, kind)` already exists, a `conflicts` row is emitted with `subject_kind='person_relation'`, `field='directionality'`, and `resolution_rule='manual_review'`. Both the existing and new rows are retained; the conflict flags the contradiction for human review.

Non-directional kinds (`spouse`, `sibling`, `ally`, `rival`, `clan_member`) do not trigger contradiction detection.

### Candidate column naming convention

Candidate relation tables use `candidate_*_id` column names (e.g. `candidate_event_id`, `candidate_person_id`) rather than bare `event_id`/`person_id`. The loader treats these values as canonical IDs — upstream linking (stage 5) is responsible for resolving candidate IDs to canonical ones before this stage runs.

### Confidence and provenance

Candidate relation tables do not carry a `confidence` column. All promoted rows receive `confidence=0.9` and `provenance='auto'`.

## What would invalidate this article

- Changing the confidence-delta threshold.
- Curated records becoming mergeable under any condition.
- Citation accumulation being added to this stage.
- Adding a place-variants or state-variants table (would require match-by-variant logic like persons).
- Changing the `_PRECISION_RANK` mapping or adding new uncertainty levels.
- Wiring `merge_date_field` into states/persons date fields (currently those use plain higher-confidence-wins).
- Adding a `candidate_state_capitals` staging table (would activate the stub).
- Adding new directional person_relation kinds to `_DIRECTIONAL_PERSON_RELATION_KINDS`.
