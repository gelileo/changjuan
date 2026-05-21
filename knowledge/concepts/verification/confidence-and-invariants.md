---
title: Confidence as a computed score; extraction invariants
type: concept
area: verification
updated: 2026-05-21
status: thin
load_bearing: true
affects:
  - pipeline/confidence.py
  - pipeline/qa_sampling.py
  - .claude/skills/changjuan-verify-sample/**
references:
  - concepts/data-model/knowledge-graph.md
  - concepts/pipeline/architecture.md
---

## What this is

Two intertwined load-bearing decisions about how `changjuan` knows what it knows.

**Confidence is a deterministic score computed by the pipeline, not the LLM's self-report.** A self-reported `0.8` from a structured-extraction model means "looked confident in the answer," not "right 80% of the time." Using model self-report as the primary signal would push subtle errors into auto-merge decisions in stage 5, which is where errors compound silently across the graph. We compute confidence ourselves from surface features — citation strength, name-variant overlap, `state_id` agreement, temporal/spatial proximity, `inference_kind` for dates — with the LLM judge as one weighted input among others.

**The project enforces two extraction invariants, and is explicit that they are NOT equal rigor:**

1. **Verbatim-quote invariant.** Every extracted record's `quote` is a literal substring of its source `chunk`. Enforced at stage-3 output validation. Catches fabricated source spans.
2. **Claim-defensible-from-quote.** Layered:
   - **Per-field justification** — stage 3 prompts the model for a substring of the quote that supports each field's value. Treat this layer as a *generation-time nudge that produces a verifiable artifact*; the artifact itself is gameable (the model can quote a substring that mentions the right entity rather than one that supports the specific value). The static check catches the trivially-empty case, not the trivially-bad case.
   - **Sampling QA — the actual backstop.** A deterministic 5% sample per chapter is re-evaluated by a different model answering "does this quote support this field?" Verdict distributions land in `pipeline_runs.stats_json.claim_defensible_sample`; threshold breach blocks the stage-9 freeze. Sample size set by a binomial power calculation: detect a 5pp regression with α=0.05, β=0.2 (~180 verifications corpus-wide).

## Stage-3 confidence stub (Phase 2)

`pipeline/confidence.py::score_extraction_record` is the registered entry point
for stage-3 confidence scoring. v1 stub: base 0.70 + citation-quote-length
bonus (max +0.15) + justification-completeness bonus (+0.10 when every scalar
field has a non-empty justification_quote). Ceiling 0.95 — 1.0 is reserved
for curated records.

Future phases tune the weights against sampling-QA reliability diagrams
(see `pipeline_runs.stats_json.confidence_calibration`). The function signature
is stable so callers don't change when scoring gets smarter.

### Sampling QA harness (Phase 2)

`pipeline/qa_sampling.py::select_sample` produces a deterministic 5% sample
keyed by `hash(pipeline_run_id, record_id, field)` — same input always yields
the same sample. Bounded by `config.QA_SAMPLE_FLOOR` (30) and
`QA_SAMPLE_CEILING` (250).

The verifier is the `.claude/skills/changjuan-verify-sample/` skill — a
separate Claude Code skill with a focused yes/no/partial prompt. The
operational flow:

1. `uv run changjuan qa-sample <pipeline_run_id>` emits the sample triples
   as YAML on stdout.
2. `/changjuan-verify-sample` (in Claude Code) consumes that, judges each
   triple, writes verdicts to `data/qa/{run_id}.yaml`.
3. `uv run changjuan qa-load --run-id <id> --qa-file <p>` ingests verdicts
   into the `qa_samples` table and updates
   `pipeline_runs.stats_json.claim_defensible_sample` with
   `{sample_size, yes, partial, no, mismatch_rate}`.

Mismatch rate exceeding `config.QA_MISMATCH_THRESHOLD` (default 0.10)
appends `"claim_defensible_mismatch_rate"` to
`pipeline_runs.stats_json.thresholds_breached` — blocking future stage-9
freezes (Phase 3+ concern).

## Why this shape, not the alternatives

The naive path is to trust the LLM's reported probability. Rejected because pipeline merge decisions (especially stage 5 linking) require calibrated confidence and LLM self-report isn't. Computing it ourselves means we know what knobs to turn. The naive path on invariants is to treat verbatim-quote as sufficient. Rejected because the more common LLM failure isn't a fabricated quote but a wrong claim derived from a real one — the sampling QA exists to catch that, and being honest about which layer does the work prevents misallocated effort.

### Known limitation: Phase 2 verifier uses same model as extractor

The spec's full design called for a *different* model (Opus 4.7) verifying
Sonnet 4.6's extractions for shared-bias decorrelation. In the Claude Code
subscription model, a session has one active model at a time. Phase 2 falls
back to "different prompt only" decorrelation, per the spec's escape hatch
("a different model **or** a different prompt template"). Different-model
decorrelation can be added later if Claude Code gains per-skill model
configuration; for now the verifier prompt is deliberately structured
differently (yes/no/partial focused) from the extraction prompt to wring
some decorrelation out of the prompt alone.

## What would invalidate this article

- LLMs shipping a verifiably-calibrated structured-extraction confidence (none have today).
- The 5% sampling rate stopping achieving its power target (tracked in `stats_json`).
- Future LLM behaviour where per-field justifications stop being gameable in the way described — the framing would soften from "generation-time nudge" to "secondary verification."

## First commitments (true once code lands)

- Confidence scoring: `pipeline/confidence.py`, weights in a YAML config.
- 5% sample constant in `pipeline/config.py` with the power calculation as a comment; raise the constant if target effect size shrinks.
- `pipeline_runs.stats_json.thresholds_breached` is the canonical gate for stage-9 freeze.
- Per-stage reliability diagrams emitted to `data/exports/diagnostics/` on every run.
- `qa_samples` table in `data/changjuan.sqlite` holds the sampling-QA verdicts.
