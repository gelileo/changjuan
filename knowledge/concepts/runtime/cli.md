---
title: changjuan CLI commands
type: concept
area: runtime
updated: 2026-05-21
status: current
load_bearing: false
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/dates-and-reigns.md
affects:
  - pipeline/cli.py
  - tests/unit/test_resolve_relative_date_cli.py
  - tests/unit/test_extract_preflight.py
  - tests/unit/test_re_extract.py
  - tests/unit/test_golden_eval_cli.py
  - tests/unit/test_qa_cli.py
---

## What this is

The `changjuan` command is a typer-based CLI exposing one subcommand per pipeline stage that has a stable user-facing surface. Phase 1 wires `ingest`, `chunk`, `load`, `export`. Phase 2 adds `extract` (pre-flight), `extract-load`, `list-unresolved-dates`, and `resolve-relative-date` — `extract` is a non-LLM checklist that gates entry to stage 3; `extract-load` is a thin wrapper around stage-3 extraction; the latter two are the curator triage surface for cross-chunk relative-date anchoring.

## Subcommands

### Pipeline stages

- **`changjuan ingest [--repo-root PATH]`** — Stage 1: reads the dongzhoulieguozhi JSON from `corpora/dongzhoulieguozhi/json/东周列国志.json` and inserts one row per chapter into `corpus.sqlite`. Exits 1 with a clear message if the corpus file is absent.
- **`changjuan chunk [--repo-root PATH]`** — Stage 2: splits all unchunked documents into paragraph-aware overlapping chunks and writes them to `corpus.sqlite`.
- **`changjuan extract --chapter N [--repo-root PATH]`** — Stage 3 pre-flight (non-LLM). Verifies: `corpus.sqlite` exists; chapter N has >1 chunk (post _PARA_SEP fix regression guard); at least one `.claude/skills/changjuan-extract*/` directory exists; the required files (`SKILL.md`, `system-prompt.md`, `extraction-schema.yaml`) are present; and `extraction-schema.yaml` matches the canonical `EXTRACT_OUTPUT_SCHEMA` Python object. If all checks pass, prints a copy-paste `/<skill-name> chapter:N` invocation and the follow-up `extract-load` command. Exits 1 if any check fails; all check results are printed with ✓/✗ prefix for easy triage.
- **`changjuan extract-load --chapter N --extraction-file PATH --prompt-version V [--pipeline-run-id ID] [--repo-root PATH]`** — Stage 3: validates a skill-produced extraction YAML file, runs all extraction invariants per record, and writes passing records to `candidate_persons`, `candidate_events`, `candidate_places`, `candidate_states`, and `candidate_relations`. Auto-generates a `pipeline_run_id` (format: `run:extract-ch<chapter>-<prompt_version>-<timestamp>`) if `--pipeline-run-id` not supplied. Returns per-entity-kind counts and lists up to 10 invariant violations (or count if >10). Invariant failures prevent a record from being written but do not cause the command to exit non-zero.
- **`changjuan load <pipeline_run_id> [--repo-root PATH]`** — Stage 7: promotes all five entity-kind candidates matching the given `pipeline_run_id` into canonical entities with field-level merge semantics (curated-never-overwritten, higher-confidence-wins, Conflict on disagreement). Load order: places + states first (other entity types reference them via foreign keys), then persons, events, and finally all six relation kinds. Returns counts for each entity kind loaded.
- **`changjuan export <version> [--repo-root PATH]`** — Stage 9: freezes a versioned export bundle at `data/exports/changjuan-export-<version>/`, containing `manifest.json` and a `candidate_*`-stripped SQLite snapshot.

### Sampling QA verbs (Phase 2)

- **`changjuan qa-sample <pipeline_run_id> [--repo-root PATH]`** — Emits the deterministic 5% sample of scalar facts for the given `pipeline_run_id` as YAML on stdout. The `changjuan-verify-sample` skill consumes this output. The verb first checks `candidate_facts` (stage 3 per-field justifications); if that table is empty for the run, it falls back to enumerating scalar fields directly from `candidate_persons`, `candidate_events`, `candidate_places`, and `candidate_states` (any non-null scalar field becomes one fact). Sampling is bounded by `config.QA_SAMPLE_FLOOR` (30) and `config.QA_SAMPLE_CEILING` (250) and is fully deterministic — same `pipeline_run_id` always produces the same sample.

- **`changjuan qa-load --run-id ID --qa-file PATH [--verifier-model MODEL] [--repo-root PATH]`** — Loads a verifier-verdict YAML (produced by the `changjuan-verify-sample` skill) into `qa_samples`. For each verdict, inserts a row with a UUID `id`, the `pipeline_run_id`, `record_kind`, `record_id`, `field`, `verdict`, and `verifier_model` (default: `claude-opus-4-7`). After loading, computes `mismatch_rate = (no + 0.5 * partial) / total` and patches `pipeline_runs.stats_json.claim_defensible_sample` with `{sample_size, yes, partial, no, mismatch_rate}`. If `mismatch_rate > config.QA_MISMATCH_THRESHOLD` (0.10), appends `"claim_defensible_mismatch_rate"` to `stats_json.thresholds_breached` (idempotent — no duplicate appends). Prints a summary line on success.

### Evaluation verbs (Phase 2)

- **`changjuan golden-eval --chapter N [--pipeline-run-id ID] [--repo-root PATH]`** — Loads the golden YAML set for chapter N from `tests/golden/ch{N:02d}/`, queries `pipeline_runs` for the most recent `stage='extract-load'` run whose `scope_json.chapter = N`, fetches all candidate rows (persons, events, places, states, and all five candidate relation tables), runs `tests/golden/precision_recall.compute_pr`, and prints per-entity-type P/R lines with ✓/✗ vs `GOLDEN_PR_THRESHOLDS`. Exits non-zero if any kind falls below threshold. `--pipeline-run-id` overrides the auto-lookup.

  Candidate-to-dict mapping:
  - **persons** — `id` (chunk-local suffix, e.g. `p1`), `canonical_name`, `state_id`, `social_category`, `variants=[]` (candidate_person_variants is Phase-3 only).
  - **events** — `id` (chunk-local suffix, e.g. `e1`), `type`, `date.year_bce` (parsed from `date_json`), `primary_place_id`.
  - **places** — `id` (chunk-local suffix, e.g. `pl1`), `name`.
  - **states** — `id` (chunk-local suffix, e.g. `s1`), `name`.
  - **relations** — union of `candidate_event_participants` (kind=event_participant), `candidate_event_places` (kind=event_place), `candidate_event_relations` (kind=<relation kind>), `candidate_person_relations` (kind=<relation kind>), `candidate_person_states` (kind=person_state). `candidate_state_capitals` has no candidate table (Task 19 stub). All FK columns (`candidate_event_id`, `candidate_person_id`, etc.) are stripped to chunk-local suffix (last `:` segment) before insertion into the relation dict.

  The `id` field (chunk-local suffix) is required so that `precision_recall.compute_pr` can build per-side name-lookup maps. The golden uses canonical-style ids (`sta:zhou`, `pla:qian-mu`); the skill emits chunk-local ids (`s1`, `pl1`). Matching via name (not raw id) bridges the two id-spaces. The chunk-local suffix is extracted via `row_id.split(":")[-1]` — e.g. `cand:per:run:extract-ch1-v1-20260521T204317:p1` → `p1`.

### Curator triage verbs (Phase 2)

- **`changjuan list-unresolved-dates [--repo-root PATH] [--chapter N]`** — Lists all canonical `events` whose `date_json` has `inference_kind = 'relative_to_prior_event'`, `year_bce = null`, and no `relative_anchor_event_id`. These are relative-date references whose anchor event lived in a prior extraction chunk and could not be resolved automatically. Output is tab-separated `event_id\toriginal_text`, one row per unresolved event. Exits 0 with a "(no unresolved relative dates)" message when none remain.

- **`changjuan resolve-relative-date --event-id ID --anchor-event-id ID [--offset N] [--repo-root PATH] [--actor LABEL]`** — Manually resolves a cross-chunk relative date by:
  1. Setting `relative_anchor_event_id` in the event's `date_json` to the supplied anchor.
  2. Calling `resolve_relative_dates` to recompute `year_bce` from the anchor's resolved year plus the token offset (or `--offset` when the original text is not a known token like 明年/次年).
  3. Persisting the updated `date_json` to `events`.
  4. Writing an `audit_log` entry with `change_kind = 'curator_override'` and `actor` defaulting to `curator:default`.

  Exits 1 with a clear error if the event or anchor is not found, the anchor has no resolved `year_bce`, or the offset cannot be determined.

  The `--offset` flag is calendar-years-later (positive = forward in time). For BCE arithmetic: `year_bce_result = anchor_year_bce - offset`.

- **`changjuan re-extract --chapter N --prompt-version V [--repo-root PATH]`** — Reload-only mode: re-loads an existing `data/extractions/ch{N:02d}/extract-{V}.yaml` as a **new** `pipeline_run_id` without invoking the LLM skill again. Useful when a validator bug is fixed and existing YAML needs re-processing. Auto-generates a fresh `pipeline_run_id` (`run:re-extract-ch{N}-{V}-{timestamp}`), delegates to `load_extraction`, and reports per-entity-kind written counts. When the YAML file does not exist, prints an actionable message with the exact slash-command to invoke in Claude Code first (`/<skill-dir> chapter:N`) and exits non-zero (code 1). The `--prompt-version` flag follows the skill-directory naming convention (`v1` → `changjuan-extract/`; `v2` → `changjuan-extract-v2/`). See [`concepts/pipeline/incremental.md`](../pipeline/incremental.md) for full re-extract semantics.

## Why this shape, not the alternatives

A single `changjuan run` mega-command was considered and rejected — it would hide the cost profile of each stage and make resumption harder. Separate subcommands match the stage-checkpointed pipeline model directly: each stage runs independently, each can be re-run without re-executing earlier stages, and the user can inspect intermediate outputs between stages.

The `list-unresolved-dates` / `resolve-relative-date` pair is deliberately not automatic: the skill explicitly does not attempt cross-chunk anchoring because the correct anchor requires curator judgment. The CLI surfaces the triage work; `audit_log` entries make every resolution reversible and attributable.

`golden-eval` is named with a hyphen (not `eval`) to avoid colliding with Python's `eval` builtin; the spec's `eval` shorthand is interchangeable with `golden-eval` everywhere.

## Design commitments

- All commands take `--repo-root` to allow non-cwd execution (testing, multiple checkouts).
- `load` takes a required `pipeline_run_id` positional — promotion is always scoped to a specific extraction batch.
- `export` takes a required `version` positional — export bundles are always versioned at the bundle dirname.
- `resolve-relative-date` always writes an `audit_log` entry — resolutions are auditable even if the curator corrects a previous resolution.

## What would invalidate this article

- A stage acquiring more than one user-facing verb (e.g., separate `link` and `link-rescue`).
- The pipeline becoming agentic (one command, no stages).
- Automatic cross-chunk anchoring being added (would retire the curator verbs or demote them to override-only).
