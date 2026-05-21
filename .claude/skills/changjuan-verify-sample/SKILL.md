---
name: changjuan-verify-sample
description: Verify a deterministic 5% sample of stage-3 extraction claims. For each (quote, field, value) triple, judge yes/no/partial whether the quote supports the value. Use after stage-3 extraction completes (per pipeline_run_id) to check claim quality.
---

# changjuan-verify-sample — Sampling QA Verifier Skill

This skill performs the sampling QA layer of the changjuan pipeline. It takes
the deterministic 5% sample emitted by `changjuan qa-sample`, judges each
`(quote, field, value)` triple with a focused yes/no/partial verdict, writes
the verdicts to `data/qa/{RUN_ID}.yaml`, then loads them back into the
database.

**Phase 2 limitation:** the extractor and the verifier run within the same
Claude Code session (same active model). Decorrelation is by prompt only, not
by model — this is the spec's "different prompt template" escape hatch. The
verifier prompt is structurally distinct from the extraction prompt to wring
some decorrelation out of the single-model constraint.

## Pre-flight

Read `verifier-prompt.md` (sibling file in this skill directory) before
judging anything. The verifier prompt governs all judgment criteria, examples,
and output format.

## Steps

### 1. Obtain the sample list

Run the sampler CLI to emit the triples for the given run:

```bash
uv run changjuan qa-sample <RUN_ID>
```

The CLI prints a YAML list of objects to stdout. Each object has:

```yaml
- pipeline_run_id: run:extract-ch01-v1-20260521T120000
  record_id: cand:per:run:test:p1
  field: canonical_name
  value: 周宣王
  quote: 立太子靖为王，是为宣王
  chunk_id: chk:dzl:1:0
```

Optionally pipe to a file for easier handling:

```bash
uv run changjuan qa-sample <RUN_ID> > /tmp/qa-sample.yaml
```

(Task 33 implements the `qa-sample` verb.)

### 2. Read verifier-prompt.md

Open `.claude/skills/changjuan-verify-sample/verifier-prompt.md` and apply
its judgment criteria to every triple from step 1.

### 3. Judge each triple

For each triple, apply the verifier prompt to produce a verdict:

- **yes** — the quote unambiguously supports the field value. A reasonable
  annotator reading only this quote would write the same value.
- **partial** — the quote is related to the claim and consistent with it,
  but does not unambiguously specify the value. The extractor's inference
  required background knowledge or a slight stretch.
- **no** — the quote does not support the field value. The extractor made
  an unsupported leap.

Add a single short Chinese sentence for `reason`.

**The contract:** judge only the quote string and the field+value claim. Do
not invoke the extraction skill, do not re-read corpus chunks, do not import
outside historical knowledge as positive evidence. The question is strictly:
"given this quote alone, does it support this field value?"

### 4. Write verdicts to YAML

Create the output directory and write one verdict record per triple:

```bash
mkdir -p data/qa
# write verdicts to:
# data/qa/<RUN_ID>.yaml
```

Output format (one record per triple, same order as the sample list):

```yaml
- record_kind: person
  record_id: cand:per:run:test:p1
  field: canonical_name
  verdict: yes
  reason: 引文明确写出"是为宣王"，与canonical_name直接对应

- record_kind: event
  record_id: cand:evt:run:test:e1
  field: outcome
  verdict: partial
  reason: 引文支持事件类型但未细化结果

- record_kind: person
  record_id: cand:per:run:test:p2
  field: gender
  verdict: no
  reason: 引文未提及性别，female无引文支持
```

**Constraints:**
- One verdict per triple — no missing or duplicate entries.
- `verdict` ∈ exactly `{yes, no, partial}`.
- `reason`: exactly one short Chinese sentence (≤ 30 characters); stored for
  curator review, not for downstream computation.
- `record_kind` must match the kind implied by the `record_id` prefix
  (`cand:per:*` → `person`; `cand:evt:*` → `event`; `cand:pla:*` → `place`;
  `cand:sta:*` → `state`; `cand:rel:*` → `relation`).

### 5. Load verdicts into the database

```bash
uv run changjuan qa-load --run-id <RUN_ID> --qa-file data/qa/<RUN_ID>.yaml
```

This writes `qa_samples` rows and updates
`pipeline_runs.stats_json.claim_defensible_sample`.

(Task 33 implements the `qa-load` verb.)

### 6. Report summary

Print a summary after the load completes:

- Total triples sampled.
- Verdict breakdown: yes / partial / no counts.
- Mismatch rate: `(no + 0.5 × partial) / total` (rounded to 2 decimal places).
- Threshold status: PASS if mismatch_rate ≤ 0.10, BREACH if > 0.10.

Example:

```
Sampled: 47
  yes:     38  (80.9%)
  partial:  7  (14.9%)
  no:       2   (4.3%)
Mismatch rate: 0.074 — PASS (threshold: 0.10)
```

## Constraints

- One verdict per triple — no missing entries.
- `verdict` ∈ exactly `{yes, no, partial}`.
- `reason`: 1 short Chinese sentence; stored for curator review.
- Verifier reads ONLY the quote string + chunk reference (if available). Do
  not invoke the extraction skill, do not re-read corpus chunks. The contract
  is "given just this quote and this field+value, does the quote support it?"
- When uncertain between `yes` and `partial`, prefer `partial`.
- When uncertain between `partial` and `no`, prefer `partial` only if the
  quote is genuinely related to the claim; otherwise `no`.
