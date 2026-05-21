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
