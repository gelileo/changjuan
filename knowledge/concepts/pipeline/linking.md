---
title: Stage 5 — Link & Dedup
type: concept
area: pipeline
updated: 2026-05-22
implemented: Phase 3 Tasks 5-13; Phase 4 Task 7 (candidate_pool state-id resolution); Phase 5 Tasks 1-6 (merge module)
status: thin
load_bearing: true
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
  - concepts/pipeline/load-and-merge.md
  - concepts/runtime/cli.md
affects:
  - pipeline/stage5_link/**
  - tests/golden/merge_regression.yaml
  - tests/golden/regression_loader.py
---

## What stage 5 does

Stage 5 (`pipeline/stage5_link/linker.py::link_run`) walks every `candidate_persons` row for a `pipeline_run_id`, builds a candidate pool of plausible match targets (both same-run siblings and existing canonical persons), scores each target using a deterministic surface-feature formula, and dispatches by threshold. The result is either a `match_target_id` written onto the candidate (auto-merge path) or a `merge_candidates` row (curator queue path). Candidates that score below both thresholds are left unmodified; stage 7 will mint new canonical Persons for them.

The linker processes candidates in `ORDER BY id` for determinism and tracks an `already_matched` set so the same sibling pair is not matched in both directions.

## Why deterministic-only in Phase 3

The spec proposes an LLM judge as a second pass that resolves ambiguous pairs the surface scorer can't decide confidently. That step is deferred to Phase 4 for two reasons:

1. **No curator UI yet.** The LLM judge's output needs human comparison of before/after entity graphs to validate its decisions. Stage 8's curation UI (the Streamlit app) is the natural home for this workflow; it doesn't exist yet.
2. **Baseline first.** Before adding an LLM pass, Phase 3 establishes a regression set that pins the deterministic scorer's behavior. The LLM judge will be validated against that baseline, not introduced simultaneously with it.

## Candidate pool pre-filter

`pipeline/stage5_link/candidate_pool.py::candidate_pool` avoids an O(N²) exhaustive comparison by pre-filtering via SQL name-overlap. A target enters the pool only if it shares at least one name string (canonical_name or any variant) with the query candidate. Names that share no characters are never scored. The pool includes both canonical `persons` rows (cross-run targets) and same-run `candidate_persons` siblings.

### Phase 4 state_id resolution

Candidate `state_id` is a local extraction id (e.g. `s1`) only meaningful within one run; canonical persons store canonical state ids (e.g. `sta:zhou`). Without resolution, a Ch.N candidate referencing the same state as a Ch.M canonical Person would score `state_agreement: different` and the match would land below the queue threshold even when the names point at the same state. `_resolve_state_local_to_canonical` (called from `_load_candidate` and applied to same-run candidates in the pool) joins `candidate_states` → `states` on `name` to convert `s1` → `sta:zhou` before scoring. Already-canonical values (containing `:`) pass through unchanged; values with no matching canonical state resolve to None (`one_null` rather than `different`).

## Feature dimensions and scoring formula

`pipeline/stage5_link/scoring.py::person_match_score` computes five dimensions and returns `{"score": float, "features": dict}`.

| Dimension | Classification | Score contribution |
|---|---|---|
| `variant_overlap` | strong (canonical appears in other's variants, or canonicals identical) | +0.50 |
| | partial (any other name-set intersection) | +0.20 |
| | none | **HARD VETO → 0.0** |
| `state_agreement` | same | +0.20 |
| | different | −0.40 |
| | one_null | 0 |
| `clan_agreement` | same | +0.10 |
| | different | −0.20 |
| | one_null | 0 |
| `social_category_agreement` | same | +0.10 |
| | different | −0.10 |
| | one_null | 0 |
| `temporal_proximity` | compatible (all dates within 200-year era window, no death-before-birth gap >150yr) | +0.10 |
| | conflict | −0.30 |
| | unknown (no date data on either side) | 0 |

The raw sum is clamped to `[0, 1]` (floated, then `max(0.0, min(1.0, ...))` applied). Hard veto on `variant_overlap == "none"` returns 0.0 immediately — no amount of state or clan agreement can rescue a pair with no name overlap.

## Threshold dispatch

Thresholds live in `pipeline/config.py` alongside a recalibration history comment:

- `LINKER_AUTO_MERGE_THRESHOLD = 0.75` — the minimum score for automatic merging. Rationale: strong variant (+0.50) + state agreement (+0.20) = 0.70, just below threshold; adding one more positive signal (e.g. same clan, +0.10) reaches 0.80, comfortably above.
- `LINKER_QUEUE_THRESHOLD = 0.40` — the minimum score to enter the curator queue. Rationale: partial variant (+0.20) + state agreement (+0.20) = 0.40 exactly, the minimum plausible evidence worth human review.

Dispatch:

| Score range | Action |
|---|---|
| `>= 0.75` | `UPDATE candidate_persons SET match_target_id = <target_id>` + `audit_log` row (`actor='link@v1'`) |
| `0.40 – 0.74` | `INSERT INTO merge_candidates` with `surface_features_json` |
| `< 0.40` | No action — candidate will become a new canonical Person at load |

## Merge regression set

`tests/golden/merge_regression.yaml` pins 10 person pairs (5 same-person, 5 different-person) drawn from historical sources (《史记·晋世家》, 《左传》, etc.). The `@pytest.mark.regression` test in `tests/integration/test_link_regression.py` asserts:

- Every `same_person_pairs` entry scores `>= LINKER_AUTO_MERGE_THRESHOLD`.
- Every `different_person_pairs` entry scores `< LINKER_AUTO_MERGE_THRESHOLD`.

`tests/golden/regression_loader.py` parses the YAML and hydrates each pair into the dict shape that `person_match_score` expects. Changing the scoring formula or thresholds in `pipeline/config.py` without updating the regression set will cause this test to fail — that is the intended behavior.

## `match_target_id` lifecycle

`link_run` sets `candidate_persons.match_target_id` to one of:

- A canonical `per:` id (cross-run: the candidate matches an existing canonical Person).
- A same-run sibling `candidate_persons.id` (intra-run: two candidates from the same extraction refer to the same person).

Stage 7's `load_candidate_persons` honors this column as the first match check, before falling back to canonical_name equality and variant lookup. For `cand:` sibling ids, Stage 7 resolves them through `local_canonical_map` — a per-load-pass in-memory dict that maps each processed candidate id to the canonical id it was assigned. Cross-run chain resolution works because candidates are processed in `ORDER BY id`, so earlier siblings are already in the map when later siblings attempt resolution. See [`concepts/pipeline/load-and-merge.md`](load-and-merge.md) for the full resolution order and fallback chain.

The `match_target_id` column is never cleared by Stage 7. If `link_run` wrote it but `load_candidate_persons` is never called, there is no side-effect — the column is read-only from Stage 7's perspective.

## `merge_candidates` queue

When a pair scores in the queue band (`[0.40, 0.75)`), the linker inserts a `merge_candidates` row with:

- `kind = 'person'`
- `candidate_a_id` — the query candidate's id
- `candidate_b_id` — the best-scoring target's id
- `score` — numeric score
- `surface_features_json` — JSON object `{"features": {...five dimensions...}, "score": float}`, providing the full feature breakdown for triage
- `status = 'open'`

The curator UI (Stage 8, Streamlit) will consume this table, present both candidates side-by-side with the feature breakdown, and let the reviewer accept or reject each merge. An accepted merge writes `match_target_id` manually; a rejected merge updates `status` to `'rejected'`. Neither path exists yet in Phase 3 — the table is populated but not yet consumed.

## Cross-run vs intra-run pair handling

Two mechanisms together prevent double-counting:

- **`already_matched` set** (linker, intra-run): when candidate A is auto-merged into sibling B, B's id is added to `already_matched`. When the loop reaches B, it is skipped. This prevents B from being matched back into A or a third candidate that would create a conflicting chain.
- **`local_canonical_map`** (Stage 7, intra-run): tracks which canonical id each candidate received during the current load pass. When a later sibling has `match_target_id = <earlier sibling id>`, the map resolves the chain: `cand:earlier → per:canonical`. This handles cases where A matches B and B matches C — all three should resolve to the same canonical.

Cross-run pairs (current candidate vs. existing canonical) are handled straightforwardly: the target_id is already a `per:` id, and Stage 7 queries `persons` directly.

## Merge actions (Phase 5)

`pipeline.stage5_link.merge` provides the decision actions invoked by the
curator UI: `accept_merge`, `reject_merge`, `defer_merge`, `split_person`.
Each function takes a sqlite Connection and performs its DB writes in a
single transaction. The audit_log row is atomic with the data change.
Detailed semantics live in the Phase 5 design spec (`docs/superpowers/specs/2026-05-22-phase5-curator-ui-design.md` §3, §4).

### `accept_merge` algorithm

In one transaction: validate `status='open'`, fold NULL canonical slots
from candidate (raise on non-NULL disagreement), fold variants (UNIQUE
constraint dedups), retarget the 5 person-FK columns, delete candidate
row, flip `merge_candidates` status, write record-level audit_log row.
Spec §3 has the full step-by-step.

### PK-collision rules (Phase 5 Task 3)

`accept_merge` resolves PK collisions before retargeting:
- `event_participants` `(event_id, person_id, role)` — higher-confidence wins; on a tie the canonical survives (candidate is the loser).
- `person_relations` self-loops (relation from/to merged pair) — deleted; audit_log captures full row.
- `person_states` `(person_id, state_id, role, COALESCE(from_date_json,''))` — higher-confidence wins; on a tie the canonical survives.
- `entity_citations` `(entity_kind, entity_id, citation_id)` — candidate row dropped; audit_log entry carries `entity_id` + `citation_id` (not just `{"duplicate":true}`).

Each resolution writes an `audit_log` row with `change_kind='merge_collision_resolved'`.

Task 3 follow-up fixes tie-break + audit-completeness minors.

### Field-level edits (Phase 5 Task 4)

`accept_merge(conn, mc_id, edits={field_name: new_value, ...})` applies
the listed edits to the canonical row BEFORE the field-level NULL fold,
so the fold sees the curator's intended values. Each edit produces a
field-level `audit_log` row with the §5 shape `{value, confidence,
source_excerpt}` for both `before_json` and `after_json`.

Editable fields: `gender`, `birth_date_json`, `death_date_json`, `notes`,
`state_id`, `clan_name`, `canonical_name`. Other field names raise
`MergeError`.

### `reject_merge` and `defer_merge`

`reject_merge(conn, mc_id, *, note=None)` flips `merge_candidates.status` to
`'rejected'`, sets `resolved_at`, and writes an `audit_log` row with
`change_kind='merge_rejected'` and `after_json={"note": <note>}`.

`defer_merge(conn, mc_id)` is a no-op from the DB's perspective — the
curator's cursor advances in Streamlit memory. Kept as a function so the
UI dispatch layer is uniform.

Reject-memory (preventing the next linker run from re-flagging a rejected
pair) is deferred to Phase 6.

### `split_person` (manual escape hatch)

`split_person(conn, person_id, *, variants_to_extract, note=None)` creates
a new person row and moves the listed variants from the source row to it.
Relations on the source row stay put — the new row starts relation-less.
Validates that all listed variants exist on the source row; raises
`SplitValidationError` otherwise.

The new person row is minted with `confidence=1.0` and `provenance='curated'`
(the curator is asserting a distinct identity) and takes its `canonical_name`
from the first peeled variant. The curator can edit these via the curation UI.
An `audit_log` row with `change_kind='split'` is written, with `before_json`
capturing the source person snapshot and `after_json` carrying the new id,
source id, peeled variants, and optional note.

### candidate_persons-side A handling (Phase 5.1)

In the live DB, `merge_candidates.candidate_a_id` points at `candidate_persons.id`, not `persons.id`. Phase 5.1 extends `accept_merge` to detect this automatically: it checks `persons` first; if the candidate is not found there it falls back to `candidate_persons` via the internal helper `_candidate_persons_snapshot`.

**Behavior when A is in `candidate_persons`:**

- **Snapshot**: `_candidate_persons_snapshot` reads the `candidate_persons` row and returns a persons-compatible dict. It drops candidate-only columns (`social_category`, `pipeline_run_id`, `chunk_id`, `quote`, `variants_json`, `match_target_id`). `state_id` values matching the local-extraction pattern (`s\d+`, e.g. `s1`) or absent from the `states` table are replaced with `NULL` so they are never folded into the canonical row.
- **NULL-fold**: same as the persons path.
- **Variant fold**: variants come from `candidate_persons.variants_json` (a JSON array of `{variant, kind}` objects). Each variant is inserted into `person_variants` via `INSERT OR IGNORE`, deduped against the `UNIQUE(person_id, variant, kind)` constraint.
- **FK retarget**: skipped. No `persons`-FK columns point at `candidate_persons` ids. `relations_retargeted = 0`.
- **Cleanup**: the `candidate_persons` row is NOT deleted (it is the historical extraction record). Instead, `candidate_persons.match_target_id` is set to `canonical_id` so Stage 7 and future linker runs know this candidate has been merged.
- **Audit log**: written the same way as the persons path. `before_json` holds the candidate snapshot sourced from `candidate_persons`.

The integration smoke's `_promote_merge_candidates_to_persons` workaround has been removed; `accept_merge` handles `candidate_persons`-side A natively.

## What would invalidate this article

- Changing any weight or classification threshold in `pipeline/stage5_link/scoring.py`.
- Changing the `LINKER_AUTO_MERGE_THRESHOLD` or `LINKER_QUEUE_THRESHOLD` values or their dispatch semantics in `pipeline/config.py`.
- Adding an LLM judge pass (would require a new section on the two-pass architecture and the comparison UI workflow).
- Extending `candidate_pool` to include non-person entities (places, states) — scoring dimensions would differ.
- Adding a `merge_candidates` consumer to the curation UI (would activate the Stage 8 section as a live path).
- Changing `match_target_id` semantics in Stage 7 (e.g. supporting cross-run `cand:` references).
- Adding new scoring dimensions beyond the five listed above.
- Changing the `already_matched` strategy (e.g. symmetric pair exclusion instead of target-side exclusion).
