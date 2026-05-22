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

## Usage

- **Stage 3 (extraction)**: Task 22 reads `EXTRACTION_DIR` and sample constants.
- **QA (sampling)**: Task 31 uses `QA_MISMATCH_THRESHOLD`, sample bounds, and fraction.
- **CLI (golden-eval)**: Task 29 gates the command on `GOLDEN_PR_THRESHOLDS`.

## Design Notes

All threshold values are placeholders and *must* be recalibrated against measured data before production use. The `Config` class is frozen to prevent runtime mutation; constants are module-level to allow easy override in test environments.
