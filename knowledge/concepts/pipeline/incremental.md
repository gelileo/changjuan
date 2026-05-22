---
title: Incremental extraction — re-extract semantics and prompt-version accumulation
type: concept
area: pipeline
updated: 2026-05-22
status: thin
load_bearing: true
references:
  - concepts/pipeline/extraction.md
  - concepts/pipeline/load-and-merge.md
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/cli.py
  - .claude/skills/changjuan-extract/**
  - .claude/skills/changjuan-extract-v*/**
---

## Why incremental extraction matters

The corpus is 108 chapters. Chapters are extracted independently — you can extract chapter 1 today, chapters 2–5 next week, and re-extract chapter 27 next month after fixing a prompt, and the canonical store accumulates correctly. The pipeline is designed so that no prior curator work is ever silently destroyed. This property is load-bearing: without it, improving a prompt version would force the curator to re-review every previously curated entity.

Three mechanisms make incremental extraction safe:

1. Every candidate write is tagged with a `pipeline_run_id` that encodes the chapter, prompt version, and timestamp.
2. Stage 7's field-level merge semantics accumulate findings rather than replacing them — citations always accumulate, scalars merge by a confidence-wins rule, and `curated` records are never silently overwritten.
3. Conflicts (same field, different value, similar confidence across runs) are surfaced via `conflicts` rows for curator triage; the curator resolves via the curation UI (Phase 3+).

## `re-extract` semantics

```
changjuan re-extract --chapter N --prompt-version <v>
```

The verb re-loads an existing extraction YAML at `data/extractions/ch{N:02d}/extract-{v}.yaml` as a **new** `pipeline_run_id` (`run:re-extract-ch{N}-{v}-{timestamp}`). It does not invoke the LLM skill again — it only re-runs the Python validator/loader against the already-written YAML. This is useful when:

- A validator bug is fixed and existing YAML output needs to be re-processed.
- The same YAML is being re-loaded after schema changes to candidate tables.

The generated `pipeline_run_id` is fresh, so stage 7's merge semantics treat the reload as a new run. Scalar disagreements with prior runs are surfaced via Conflict rows; new variants accumulate; citations from both runs appear in `entity_citations`. `curated` records remain untouched — the merge rule for `provenance='curated'` fields is always "emit Conflict, preserve existing".

This is the founding spec's §7.3 promise: improving a prompt is always safe — re-extraction adds findings, never destroys curator work.

## Prompt-version-via-skill-directory convention

Each prompt iteration lives in its own skill directory:

```
.claude/skills/changjuan-extract/       # v1 (no suffix)
.claude/skills/changjuan-extract-v2/    # v2
.claude/skills/changjuan-extract-v3/    # v3
```

The `--prompt-version` CLI argument matches the directory suffix: no suffix maps to `v1`; `-v2` suffix maps to `v2`; etc. The `audit_log.actor` convention (from spec §7.4) records `extract@v1`, `extract@v2`, etc., making the full field-level history queryable by prompt version.

`changjuan re-extract --chapter N --prompt-version v2` correspondingly expects the YAML at `data/extractions/ch{N:02d}/extract-v2.yaml` (written by the `/changjuan-extract-v2 chapter:N` skill invocation).

## Missing-file user-instruction path

When `data/extractions/ch{N:02d}/extract-{v}.yaml` does not exist, `re-extract` prints an actionable instruction and exits non-zero (code 1):

```
Extraction file not found: data/extractions/ch01/extract-v2.yaml

Skill `.claude/skills/changjuan-extract-v2/` has not been run for chapter 1.
Invoke in Claude Code first:
  /changjuan-extract-v2 chapter:1
```

This design keeps the error human-actionable without requiring the user to remember the skill naming convention. The exit code is non-zero so scripted pipelines surface the condition immediately.

## Conflict-on-divergence behavior

Stage 7's existing merge semantics apply without modification when `re-extract` loads a second (or third) run for the same chapter. When the v2 extraction produces a different value for a scalar field (e.g., a different `gender` for the same canonical Person) compared to v1:

- If v2's confidence is higher than v1's by more than `_SIMILAR_CONFIDENCE_DELTA = 0.1` **and** the existing field is `auto` → v2 wins; an `audit_log` entry records the update.
- If confidences are similar (within 0.1) → a `conflicts` row is emitted with both variants; neither silently overwrites the other; `current_best_variant_idx` is set to the higher-confidence one.
- If the existing field is `curated` → regardless of confidence, a `conflicts` row is emitted and the curator's value is preserved.

The curator resolves open `conflicts` rows via the curation UI (planned for Phase 3+). The `field_history` view reconstructs the full timeline of any field's values across all pipeline runs.

## `curated` records never silently overwritten

This rule is enforced by `pipeline/stage7_load/` for every entity kind and every scalar field. Re-extraction is therefore safe to run at any time — even after extensive curator review. The worst outcome is an additional Conflict row for the curator to triage, never silent data loss.

The invariant is tested implicitly by the stage 7 scalar merge tests; the `re-extract` CLI path is tested in `tests/unit/test_re_extract.py`.

## `golden-eval` and `pipeline_runs`

`changjuan golden-eval --chapter N` uses `pipeline_runs` to find the most-recent `stage='extract-load'` run for the given chapter (matched via `json_extract(scope_json, '$.chapter')`). It then reads all `candidate_*` rows tagged with that `pipeline_run_id` to build the candidate set for P/R scoring. This means `golden-eval` is always scoped to the outputs of a single extraction batch — it does not aggregate across runs. When multiple runs exist for a chapter, only the latest is evaluated unless `--pipeline-run-id` is passed explicitly.

The candidate SELECT statements include the `id` column (full format: `cand:per:run:extract-ch1-v1-<ts>:p1`). The chunk-local suffix (`p1`, `s1`, `pl1`, `e1`) is extracted via `split(":")[-1]` and stored as the `id` field in the candidate dict. This is required for the P/R harness's name-lookup maps to resolve cross-entity id refs. See `concepts/pipeline/extraction.md` for the full chunk-local id explanation.

## `qa-sample` / `qa-load` and `pipeline_runs`

The `qa-sample <pipeline_run_id>` verb enumerates scalar facts for a given run (falling back from `candidate_facts` to direct `candidate_*` table scanning) and emits a deterministic 5% sample for the `changjuan-verify-sample` skill. `qa-load` ingests the returned verdicts into `qa_samples` and patches `pipeline_runs.stats_json.claim_defensible_sample`. These verbs are post-extraction QA tools — they operate on an already-loaded run and do not re-trigger extraction or affect the `curated`-never-overwritten contract. See `concepts/runtime/cli.md` for the full verb documentation.

## Iteration history

Each v{N} skill directory under `.claude/skills/changjuan-extract*/` represents a discrete prompt-iteration step. The `system-prompt.md` content evolves between versions; the directory structure, the SKILL.md operational shell, and the regenerated `extraction-schema.yaml` stay mechanically equivalent (the canonical schema is the Python source in `pipeline/schemas/extract_output.py`).

- **v1** (`changjuan-extract`) — initial draft drawing from the golden Ch.1 README's decisions log (committed in Task 27).
- **v2** (`changjuan-extract-v2`) — adds a top-level `§⓪ v2 修订要点` section to `system-prompt.md` with 7 revision rules grounded in the v1 baseline analysis (see `knowledge/log.md`, 2026-05-21). Targets the systematic deviations v1 showed against golden Ch.1: event under-segmentation, role-vocabulary literalness, unnamed-person naming-suffix convention, over-conservative inferred facts, reign-year over-use, missing `variants[]` annotations on封号-form canonical_names, and missing `event_relation: causes` chains.

The pre-flight `changjuan extract --chapter N` always points at the *latest* version (alphabetical sort over the `changjuan-extract*` glob) — so as new vN directories land, the user's slash-command updates automatically. Older versions remain available for `re-extract --prompt-version v1` to reload prior YAMLs from `data/extractions/`.

## What would invalidate this article

- Changing the YAML output path convention (`data/extractions/ch{N:02d}/extract-{v}.yaml`) in the skill or the CLI.
- Changing the skill directory naming scheme (currently `changjuan-extract[-v{N}]`).
- Changing the `pipeline_run_id` format generated by `re-extract`.
- Changing how stage 7 handles `curated` records (the "never silently overwrite" rule).
- Adding a `--reload-only` flag or other modes to the `re-extract` verb.
