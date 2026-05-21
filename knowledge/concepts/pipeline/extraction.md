---
title: Stage 3 extraction — Claude-Code-skill-driven architecture
type: concept
area: pipeline
updated: 2026-05-21
status: thin
load_bearing: true
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
  - concepts/data-model/dates-and-reigns.md
  - concepts/pipeline/load-and-merge.md
  - concepts/verification/confidence-and-invariants.md
affects:
  - .claude/skills/changjuan-extract*/**
  - pipeline/stage3_extract.py
  - pipeline/schemas/extract_output.py
  - pipeline/confidence.py
  - tests/golden/loader.py
  - tests/golden/precision_recall.py
---

## What stage 3 does

Stage 3 (Extract) reads chunked corpus text and produces five kinds of structured candidates: persons, events, places, states, and relations. Every record is tagged with a `pipeline_run_id` and a `prompt_version` so the same corpus text can be extracted multiple times at different prompt versions, with results accumulating safely in the `candidate_*` tables. Stage 7 (`load`) later promotes candidates into canonical entities with field-level merge semantics.

## Why the skill-driven architecture

This project has no `ANTHROPIC_API_KEY` available. The curator works through a Claude Code subscription. Stage 3 is therefore split across two actors rather than being a Python subprocess that calls the Anthropic SDK directly.

The benefits of this shape:

- No API key management, SDK dependency, prompt-caching machinery, or retry/backoff code in the Python codebase.
- The skill can use TodoWrite, read existing canonical entities, and ask clarifying questions when sources are ambiguous — none of which a stateless API call can do.
- The iteration cycle is: edit skill `.md` files → invoke skill in Claude Code → review output → repeat. No deploy step.

The trade-off: batch processing many chapters is manual — one skill invocation per chapter. For Phase 2 (Ch.1 only) this does not matter. For Phase 3+ full-corpus runs, this is the price.

## The two-actor architecture

**Actor 1 — Claude Code skill** (`.claude/skills/changjuan-extract/`): does the LLM judgment work. Reads chunks from `corpus.sqlite`, performs extraction following `system-prompt.md` and `extraction-schema.yaml`, writes one YAML output file to `data/extractions/ch{N:02d}/extract-{version}.yaml`, then chains to the Python loader as its final step.

**Actor 2 — Python loader/validator** (`pipeline/stage3_extract.py`): pure deterministic code. Reads the YAML, runs invariant checks, writes `candidate_*` rows and a `pipeline_runs` row, computes confidence. The skill is the entry point; the Python loader is the contract.

## Data flow

1. Run `changjuan extract --chapter N` — non-LLM pre-flight: checks corpus present, chapter has chunks (>1), latest skill directory exists with the three required files, `extraction-schema.yaml` matches the Python schema.
2. Invoke `/changjuan-extract chapter:N` in Claude Code.
3. Skill reads chunks for chapter N from `corpus.sqlite`, writes `data/extractions/ch{N:02d}/extract-v1.yaml`.
4. Skill chains `uv run changjuan extract-load --chapter N --extraction-file ... --prompt-version v1`.
5. `extract-load` schema-validates the YAML against `EXTRACT_OUTPUT_SCHEMA`, runs per-record invariants, writes `candidate_*` rows, and records a `pipeline_runs` row with `stats_json.invariant_violations`.
6. Stage 7 (`changjuan load <pipeline_run_id>`) promotes candidates into canonical entities.

## The four static invariants

`pipeline/stage3_extract.py::validate_record` enforces these on every record before the candidate write. Violations are recorded in `pipeline_runs.stats_json.invariant_violations` and the offending record is skipped; the rest of the load continues (fail-soft).

1. **Citation chunk_id matches target chunk** — `citation.chunk_id` must equal the chunk's `id` in the chapter lookup.
2. **Verbatim-quote (NFC substring)** — `citation.quote` must be an NFC-normalized substring of `chunk.text`. Catches fabricated quotes or quotes from the wrong chunk.
3. **Per-field justification non-empty and substring of quote** — every value in `record.justifications` must be non-empty and an NFC-normalized substring of `citation.quote`. The static check catches the empty-justification case; the [sampling QA harness](../verification/confidence-and-invariants.md) catches subtler misattributions.
4. **Date `inference_kind` in Phase 2 allowlist** — accepts `explicit_reign_lu`, `explicit_reign_zhou`, `relative_to_prior_event`, `era_only`, `unknown`. Rejects `explicit_reign_other`, which is deferred to Phase 3 (#4 backlog item).
5. **Chunk-local id resolution** — `primary_place_id` and `state_id` values that contain no `:` (chunk-local refs like `pl3`) must be present in the set of ids declared by other records in the same YAML payload.

## The chunk-local id scheme

Within a single extraction YAML, entity ids are simple local references: `p1`, `p2`, … for persons; `e1`, `e2`, … for events; `pl1`, `pl2`, … for places; `s1`, `s2`, … for states. Relations reference entities by these same local ids. The validator rejects dangling references at load time (invariant 5 above).

Global canonical ids (`per:zhou-xuan-wang`, `pla:haojing`, etc.) are minted by stage 5 (the linker, Phase 3). Stage 3 produces candidates only — all ids in the output YAML are scoped to that YAML's chunk set.

## Prompt versioning via skill directory naming

Each prompt iteration is a new directory:

```
.claude/skills/changjuan-extract/       # v1
.claude/skills/changjuan-extract-v2/    # v2
.claude/skills/changjuan-extract-v3/    # v3
```

The `--prompt-version` flag on `extract-load` matches the directory suffix (empty suffix → `v1`). `audit_log.actor` records `extract@v1`, `extract@v2`, etc., per the spec's §7.4 convention.

`changjuan re-extract --chapter N --prompt-version v2` either reloads an existing `data/extractions/ch{N:02d}/extract-v2.yaml` (useful when fixing a validator bug without re-running the agent) or exits with a message to invoke `/changjuan-extract-v2 chapter:N` in Claude Code first.

## Single source of truth for the extraction schema

`pipeline/schemas/extract_output.py::EXTRACT_OUTPUT_SCHEMA` is the canonical Python dict. `scripts/regen-extraction-schema` materializes it into `.claude/skills/changjuan-extract/extraction-schema.yaml`. A local pre-commit hook runs the regenerator on every commit that touches either file and asserts no diff — the skill and the Python validator can never drift. The `changjuan extract` pre-flight verb also compares the two and fails if they diverge. (Regenerator and hook implemented in Task 26; YAML seeded alongside that commit.)

## Confidence scoring

`pipeline/confidence.py::score_extraction_record` is the registered entry point. v1 stub formula:

```
base = 0.70
citation_bonus = min(len(citation.quote) / 100, 0.15)
justification_bonus = 0.10  # if all scalar fields have non-empty justifications
score = min(base + citation_bonus + justification_bonus, 0.95)
```

The 0.95 ceiling reserves 1.0 for curated records. Stage 3 never claims 1.0. Future phases tune weights against sampling-QA reliability diagrams; the function signature is stable so callers do not change.

## Sampling QA "different prompt only" limitation

The spec's ideal decorrelation for sampling QA is Opus 4.7 verifier vs. Sonnet 4.6 extractor — different models reduce correlated errors. A Claude Code session has one active model at a time, so Phase 2's sampling QA harness (`.claude/skills/changjuan-verify-sample/`) uses the same model as the extractor, decorrelated by prompt only. The spec's escape hatch ("a different model **or** a different prompt template") makes this acceptable. This is a documented Phase 2 limitation; it can be promoted to full model-level decorrelation if Claude Code gains per-skill model configuration.

## Skill files (Task 27)

The v1 skill directory is now fully populated at `.claude/skills/changjuan-extract/`:

- `SKILL.md` — operational instructions for the Claude Code agent (how to query chunks,
  emit chunk-local ids, chain `fill-spans` and `extract-load`, hard constraint list).
- `system-prompt.md` — comprehensive Chinese-language extraction rules (~1000 words).
  Covers entity definitions, scope rules, variant folding, `social_category` enum,
  date handling (`inference_kind` allowlist), citation and justification mechanics,
  relation coverage strategy, and a minimum-valid YAML inline example.
- `extraction-schema.yaml` — generated YAML mirror of `EXTRACT_OUTPUT_SCHEMA` (Task 26).
- `examples/ch01-excerpt.md` — fully worked few-shot example from chunk `chk:dzl:1:14`
  (Ch.1 paragraphs 14–19: 785 BCE events — 宣王梦 / 杜伯被斩 / 左儒自刎 / 隰叔奔晋).

The system prompt is the primary iteration surface for Phase 2. Edit
`system-prompt.md` and re-invoke the skill; the Python validator and its invariants
do not change between prompt iterations.

## Chunk-local ids and the P/R harness

The chunk-local id scheme creates a cross-id-space mismatch when comparing extraction output against the golden chapter annotations. Golden files use canonical-style ids (`sta:zhou`, `pla:qian-mu`, `per:zhou-xuan-wang`); the skill output uses chunk-local ids (`s1`, `pl1`, `p1`). The `tests/golden/precision_recall.py` harness resolves this by building per-side name-lookup maps (`{id → name}` for places/states, `{id → canonical_name}` for persons, `{id → type}` for events) and comparing resolved names rather than raw ids. The `golden_eval_cmd` in `pipeline/cli.py` includes the chunk-local suffix (extracted via `full_id.split(":")[-1]`) as the `id` field in each candidate dict so the lookup maps have the correct keys.

## What would invalidate this article

- Adding an `ANTHROPIC_API_KEY` to the project and wiring a direct SDK call (would eliminate the two-actor split).
- Changing the invariant list in `validate_record`.
- Renaming the skill directory naming convention (would break `--prompt-version` inference).
- Changing the confidence scoring formula in `confidence.py`.
- Introducing `explicit_reign_other` support (Phase 3 backlog item #4 — would update the allowlist).
