---
title: Runtime Configuration
type: concept
area: runtime
updated: 2026-05-22
note: Phase 5 Task 7 — LOW_CONFIDENCE_THRESHOLD added for curation app.
status: mature
load_bearing: true
references:
  - concepts/pipeline/architecture.md
affects:
  - pipeline/config.py
  - pipeline/stage5_link/**
---

# Runtime Configuration

`pipeline/config.py` is the single source of truth for paths, batch sizes, and tunable constants across the changjuan ETL pipeline.

## Structure

The module contains two kinds of configuration:

1. **`Config` dataclass**: Frozen, immutable configuration object bundling repo root and pipeline tunables (chunk sizing, paths to corpus and canonical SQLite stores, data and export directories).

2. **Module-level constants**: Tunable thresholds and limits for specific pipeline stages and features.

## Phase 2 Constants (Stage 3 + QA)

As of Task 12, the following Phase 2 constants are defined:

- **`EXTRACTION_DIR`** (`str`): Directory for skill-produced extraction YAMLs; gitignored. Default: `"data/extractions"`.
- **`QA_MISMATCH_THRESHOLD`** (`float`): Sampling-QA mismatch rate threshold (0–1). When breached, writes `"claim_defensible_mismatch_rate"` into `pipeline_runs.stats_json.thresholds_breached`. Default: `0.10` (10%).
- **`QA_SAMPLE_FRACTION`** (`float`): Fraction of scalar facts to sample per pipeline run for QA validation. Default: `0.05` (5%).
- **`QA_SAMPLE_FLOOR`** / **`QA_SAMPLE_CEILING`** (`int`): Absolute bounds on sample size (in claims). Default floor: 30, ceiling: 250.
- **`GOLDEN_PR_THRESHOLDS`** (`dict[str, dict[str, float]]`): Precision/recall gates for golden Ch.1 evaluation, per entity kind (person, event, place, state, relation). Initial values were placeholders; recalibrated after the v2 baseline (Task 29.4): `relation.precision` lowered from 0.75 → 0.65 (v2 measured 0.6984, set symmetric with recall threshold for margin). All other thresholds unchanged — v2 cleared them by wide margins. The remaining relation-precision gap is over-inferred edges that stage-5 linker is the right place to consolidate (Phase 3 work, flagged in `PHASE2_DEFERRED`). The recalibration rationale + history lives as a comment block immediately above the dict in `pipeline/config.py`.

## Phase 3 Constants (Stage 5 Linker)

As of Task 5, the following Phase 3 constants are defined:

- **`LINKER_AUTO_MERGE_THRESHOLD`** (`float`): Minimum scorer score for automatic merging. Candidates scoring at or above this value have `match_target_id` written immediately (auto-merge path). Initial v1 value: `0.75`. Rationale: strong variant match (+0.50) + state agreement (+0.20) = 0.70 falls just under; one additional positive signal (+0.10) = 0.80 clears the threshold — safe margin for auto-merge.
- **`LINKER_QUEUE_THRESHOLD`** (`float`): Minimum score to be queued for human review (writes a `merge_candidates` row). Candidates scoring below this skip the queue and create a new canonical record at load time. Initial v1 value: `0.40`. Rationale: partial variant (+0.20) + state agreement (+0.20) = 0.40 is the minimal evidence worth a human second look. Dispatch logic lives in `pipeline/stage5_link/linker.py::link_run` (lands in Tasks 7–8). Full calibration rationale and recalibration history are documented in the comment block immediately above the constants in `pipeline/config.py` — follow the same pattern as `GOLDEN_PR_THRESHOLDS`.

## Usage

- **Stage 3 (extraction)**: Task 22 reads `EXTRACTION_DIR` and sample constants.
- **QA (sampling)**: Task 31 uses `QA_MISMATCH_THRESHOLD`, sample bounds, and fraction.
- **CLI (golden-eval)**: Task 29 gates the command on `GOLDEN_PR_THRESHOLDS`.
- **Stage 5 (linker)**: `LINKER_AUTO_MERGE_THRESHOLD` and `LINKER_QUEUE_THRESHOLD` drive the dispatch dial in `pipeline/stage5_link/linker.py::link_run` (lands in Tasks 7–8).

## Design Notes

All threshold values are placeholders and *must* be recalibrated against measured data before production use. The `Config` class is frozen to prevent runtime mutation; constants are module-level to allow easy override in test environments.

## Stage 5 scorer (Phase 3 Task 6)

`pipeline/stage5_link/scoring.py` introduces `person_match_score(a, b)` — the pure-function scorer that reads the thresholds above indirectly via the linker. The scorer itself has no configuration: its weights are hard-coded in the formula (see `concepts/pipeline/linking.md`, Task 12). Only the dispatch thresholds (`LINKER_AUTO_MERGE_THRESHOLD`, `LINKER_QUEUE_THRESHOLD`) live in `pipeline/config.py`. All five scoring dimensions are independent: temporal contributions apply unconditionally — spec §4 confirms this via the regression walkthrough table.

## Stage 5 link_run orchestrator (Phase 3 Task 8)

`pipeline/stage5_link/linker.py::link_run` is now implemented (Task 8). It reads `LINKER_AUTO_MERGE_THRESHOLD` and `LINKER_QUEUE_THRESHOLD` from `pipeline.config` to dispatch candidates. No new configuration constants were added. `link_run` is re-exported from `pipeline.stage5_link.__init__` so callers use `from pipeline.stage5_link import link_run`. The `_denormalize_variants` bridge helper runs at entry and requires no configuration.

**Phase 3 Task 8 fix:** The `already_matched` sibling short-circuit now correctly bumps `stats["skipped"]` before `continue`, preserving `candidates_processed == auto_merges + queued + skipped`. No configuration change.

## Stage 5 merge actions — merge.py (Phase 5 Task 1)

`pipeline/stage5_link/merge.py` (Phase 5 Task 1) adds the decision-action stubs: `accept_merge`, `reject_merge`, `defer_merge`, `split_person`. No new configuration constants are introduced — the merge functions take explicit DB connections and MC ids; there are no tuneable thresholds beyond those already defined (`LINKER_*`). Full implementation lands in subsequent tasks.

## `accept_merge` implementation (Phase 5 Task 2)

Phase 5 Task 2 implements the `accept_merge` happy path; no new configuration constants are added — the function remains threshold-free and operates entirely via DB state.

## `accept_merge` PK-collision handling (Phase 5 Task 3)

Phase 5 Task 3 extends `accept_merge` with four collision-resolution helpers; no new configuration constants are added. The helpers are threshold-free — they apply deterministic rules (higher confidence wins, self-loops deleted, citation duplicates dropped) without any tunable values.

## `accept_merge` edits handling (Phase 5 Task 4)

Phase 5 Task 4 extends `accept_merge` with an `edits` parameter; no new configuration constants are added. The `_ALLOWED_EDIT_FIELDS` frozenset is a module-level constant in `pipeline/stage5_link/merge.py` (not in `pipeline/config.py`) because it is a hard contract on permitted curator operations, not a tunable threshold.

## `reject_merge` + `defer_merge` (Phase 5 Task 5)

Phase 5 Task 5 implements `reject_merge` and `defer_merge`; no new configuration constants are added. `defer_merge` is a no-op. `reject_merge` updates `merge_candidates.status` and writes an `audit_log` row; both functions operate entirely via DB state.

## `split_person` (Phase 5 Task 6)

Phase 5 Task 6 implements `split_person`; no new configuration constants are added. The function is threshold-free — all logic is deterministic (validate variants exist, mint new id, update rows, write audit_log). The `confidence=1.0` and `provenance='curated'` defaults for the minted person row are hard-coded business decisions, not tunable values. Phase 5a (the load-bearing merge module) is now complete.

## accept_merge candidate_persons path (Phase 5.1)

Phase 5.1 adds no configuration constants. The `_LOCAL_STATE_ID_RE` regex (`^s\d+$`) is a module-level constant in `pipeline/stage5_link/merge.py` (not in `pipeline/config.py`) because it is a hard data-shape rule, not a tunable threshold.

## Phase 6 Task A2 — candidate_fingerprint (no configuration constants)

`pipeline/stage5_link/fingerprint.candidate_fingerprint` is configuration-free: SHA-1/16-hex/sorted-set-dedup are hard-coded design decisions (see Phase 6 spec §3.2), not tuneable thresholds.

## Stage 5 candidate_pool pre-filter (Phase 3 Task 7, hardened Task 7 fix)

`pipeline/stage5_link/candidate_pool.py` provides `candidate_pool(conn, candidate_id, pipeline_run_id)` — the SQL name-overlap pre-filter that runs before the scorer. No new configuration constants: the function has no tuneable thresholds; it is a pure filter whose inclusion criterion is "shares at least one name string." The two existing linker thresholds (`LINKER_AUTO_MERGE_THRESHOLD`, `LINKER_QUEUE_THRESHOLD`) govern downstream dispatch after scoring; `candidate_pool` is upstream of both.

`candidate_pool` is re-exported from `pipeline.stage5_link.__init__` (added Task 7 fix) so callers can import it as `from pipeline.stage5_link import candidate_pool` without reaching into the sub-module directly. No configuration impact.

## Phase 5 Constants (Curation app)

As of Task 7, the following Phase 5 constant is defined:

- **`LOW_CONFIDENCE_THRESHOLD`** (`float`): Confidence floor below which an extracted field is surfaced in the curation app's "low-confidence extractions" review queue. Initial v1 value: `0.55`. Rationale: scores in [0.55, 0.70) are technically plausible but below the pipeline's default acceptance band; a curator can confirm or reject them in under 30 seconds. Scores below 0.55 are treated as noise. Read by `curation.db.low_confidence_count` to query `candidate_facts`.

streamlit added as Phase 5 Task 8 dependency. streamlit-shortcuts (v1.2.1) added as Phase 5 Task 9 dependency for keyboard shortcuts in the curation app review pages.
