---
title: Confidence as a computed score; extraction invariants
type: concept
area: verification
updated: 2026-05-20
status: thin
load_bearing: true
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

## Why this shape, not the alternatives

The naive path is to trust the LLM's reported probability. Rejected because pipeline merge decisions (especially stage 5 linking) require calibrated confidence and LLM self-report isn't. Computing it ourselves means we know what knobs to turn. The naive path on invariants is to treat verbatim-quote as sufficient. Rejected because the more common LLM failure isn't a fabricated quote but a wrong claim derived from a real one — the sampling QA exists to catch that, and being honest about which layer does the work prevents misallocated effort.

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
