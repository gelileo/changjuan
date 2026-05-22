# Knowledge Base Index

Grouped by subject area. Each article is a standalone reference. Connections at the bottom analyze how multiple concepts interact.

For the underlying design spec, see [`docs/superpowers/specs/2026-05-20-changjuan-design.md`](../docs/superpowers/specs/2026-05-20-changjuan-design.md). The articles below are durable per-concept distillations of decisions captured there.

## changjuan (this repo)

### data-model

| Article | Summary | Updated |
| --- | --- | --- |
| [Knowledge graph — entities, relations, citations](concepts/data-model/knowledge-graph.md) | Six-entity model (Person, State, Place, Event, Citation, Conflict) + structured Date + name variants. Family deferred to a relation kind. Every relation row carries its own citation. | 2026-05-20 |
| [Dates, reigns, and inference kinds](concepts/data-model/dates-and-reigns.md) | Structured Date dict with `inference_kind` (explicit_reign_lu/zhou, relative_to_prior_event, era_only, unknown). Bundled reign table for 鲁公 and 周王 (722–468 BCE / 770–476 BCE). | 2026-05-20 |

### pipeline

| Article | Summary | Updated |
| --- | --- | --- |
| [Automation-first pipeline architecture](concepts/pipeline/architecture.md) | 9-stage sequential ETL with three LLM stages (extract, link, cross-canon). Load-bearing principle: pipeline produces a complete usable graph without curation; curation is retrospective, never a gate. | 2026-05-20 |
| [Stage 3 extraction — Claude-Code-skill-driven architecture](concepts/pipeline/extraction.md) | Two-actor design: Claude Code skill produces YAML; Python loader/validator persists. Four static invariants, chunk-local id scheme, prompt-versioning via skill directory naming, "different prompt only" sampling-QA limitation. | 2026-05-21 |
| [Incremental extraction — re-extract semantics and prompt-version accumulation](concepts/pipeline/incremental.md) | `re-extract` CLI verb reloads existing YAML as a new `pipeline_run_id`. Stage 7 merge semantics accumulate findings across runs; `curated` records never silently overwritten; missing-file path prints exact slash-command to invoke in Claude Code. | 2026-05-21 |
| [Stage 5 — Link & Dedup](concepts/pipeline/linking.md) | Deterministic surface-feature linker: five dimensions (variant_overlap, state_agreement, clan_agreement, social_category_agreement, temporal_proximity), weighted-sum scoring with hard-veto on no-variant-overlap, threshold dispatch (auto-merge / queue / skip), match_target_id lifecycle, merge_candidates queue. | 2026-05-22 |
| [Stage 7 load-and-merge semantics](concepts/pipeline/load-and-merge.md) | Promotes `candidate_persons` into canonical `persons` with field-level merge semantics. match_target_id-first resolution via local_canonical_map, confidence-delta threshold, Conflict emission, citation accumulation, variant union, audit log, places/states/events/relations loaders. | 2026-05-22 |
| [Reign-Extraction Skill — Stage Pre-3 Reign-Table Production](concepts/pipeline/reign-extraction.md) | `.claude/skills/changjuan-extract-reigns/` produces draft per-state reign YAMLs from LLM training knowledge of Eastern-Zhou chronology. One state per invocation; output to /tmp for user review before commit to `data/reigns/`. Pre-stage-3 input to `pipeline/dates.py::resolve_explicit_reign_other`. | 2026-05-22 |

### curation

| Article | Summary | Updated |
| --- | --- | --- |
| [Curation app — Streamlit retrospective review](concepts/curation/streamlit-app.md) | Single-page Streamlit app (local, read/write `changjuan.sqlite`) presenting three review queues: Person merge candidates, open Conflicts, low-confidence extractions. All decisions write to `audit_log`; fully reversible. Phase 1 status: placeholder only — Phase 2 build target. | 2026-05-20 |

### runtime

| Article | Summary | Updated |
| --- | --- | --- |
| [changjuan CLI commands](concepts/runtime/cli.md) | Typer-based CLI with one subcommand per pipeline stage: `ingest`, `chunk`, `load`, `export`. Each takes `--repo-root` for non-cwd execution. | 2026-05-20 |

### verification

| Article | Summary | Updated |
| --- | --- | --- |
| [Confidence as a computed score; extraction invariants](concepts/verification/confidence-and-invariants.md) | Confidence is deterministic, not LLM self-report. Two-layer extraction invariant: verbatim (real backstop) + per-field justification (gameable generation-time nudge); 5% sampling QA is the actual claim verification, sized by a binomial power calculation. | 2026-05-20 |
| [Testing conventions, golden chapters, and fixtures](concepts/verification/testing.md) | Pytest is the only runner; unit tests use `tmp_path` and never touch `data/` or `corpora/`; integration tests behind `@pytest.mark.integration` against golden chapter fixtures. | 2026-05-20 |

## External Systems

| Article | Summary | Updated |
| --- | --- | --- |
| _(populate as source corpora are integrated — 东周列国志 already in `corpora/`; 左传 and 史记 to be added)_ | | |

## Connections

| Article | Summary | Updated |
| --- | --- | --- |
| _(populate as cross-cutting articles emerge)_ | | |
