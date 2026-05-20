# Knowledge Base Index

Grouped by subject area. Each article is a standalone reference. Connections at the bottom analyze how multiple concepts interact.

For the underlying design spec, see [`docs/superpowers/specs/2026-05-20-changjuan-design.md`](../docs/superpowers/specs/2026-05-20-changjuan-design.md). The articles below are durable per-concept distillations of decisions captured there.

## changjuan (this repo)

### data-model

| Article | Summary | Updated |
| --- | --- | --- |
| [Knowledge graph — entities, relations, citations](concepts/data-model/knowledge-graph.md) | Six-entity model (Person, State, Place, Event, Citation, Conflict) + structured Date + name variants. Family deferred to a relation kind. Every relation row carries its own citation. | 2026-05-20 |

### pipeline

| Article | Summary | Updated |
| --- | --- | --- |
| [Automation-first pipeline architecture](concepts/pipeline/architecture.md) | 9-stage sequential ETL with three LLM stages (extract, link, cross-canon). Load-bearing principle: pipeline produces a complete usable graph without curation; curation is retrospective, never a gate. | 2026-05-20 |

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
