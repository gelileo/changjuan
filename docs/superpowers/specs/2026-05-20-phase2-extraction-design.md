# changjuan Phase 2 — Stage 3 Extraction (Claude-Code-Skill-Driven)

**Date:** 2026-05-20
**Status:** Draft for review
**Scope:** Phase 2 of the changjuan tooling project: golden chapter 1 annotation, Claude-Code-skill-driven stage 3 extraction, stage 7 candidate loaders for non-Person kinds, stage 4 relative-date dereferencing, sampling QA harness, and a focused flush of the Phase 1 deferred backlog. Stage 5 (Link & dedup), stage 6 (Cross-canon), and stage 8 (Curation UI) are out of scope.

This spec layers on top of the founding design at [`2026-05-20-changjuan-design.md`](2026-05-20-changjuan-design.md). Where they conflict, this spec governs Phase 2. Where they don't, the founding spec governs.

---

## 1. Scope & Success Criteria

### In scope (Phase 2)

- **Stage 3 (Extract)** for 东周列国志, driven by a Claude Code skill rather than an Anthropic SDK call. One skill invocation per chapter; skill produces a YAML output file; a Python CLI verb validates + loads it into `candidate_*` tables.
- **Golden chapter 1** (Western Zhou collapse — 周王-anchored dates, event-heavy, people-light) hand-annotated as YAML matching the canonical schema. Lives under `tests/golden/ch01/`.
- **Golden precision/recall harness** — pure code, compares extracted candidates to the golden YAML, returns per-entity-type P/R + a mismatch report. Drives the prompt-iteration loop and gates Phase 2 acceptance.
- **Sampling QA harness** — 5% deterministic sample re-evaluated by a separate `changjuan-verify-sample` skill with a focused yes/no/partial prompt. Verdicts persist to the `qa_samples` table and `pipeline_runs.stats_json.claim_defensible_sample`. Phase 2 builds the harness; corpus-wide value lands later.
- **Stage 7 module split** — `pipeline/stage7_load.py` becomes a package; `load_candidate_events / places / states / *_relations` ship with field-level merge semantics matching `load_candidate_persons` from Phase 1.
- **`entity_citations` accumulation** — every create/update writes a citation row; never overwrites.
- **Stage 4 extension** — `relative_to_prior_event` dereferencing within a chunk (walkback) + explicit `relative_anchor_event_id` cross-chunk anchor honored when set.
- **`pipeline/confidence.py`** — minimal deterministic scorer stub (function of citation quote length + justification non-empty + base offset). Returns floats ∈ [0.7, 0.95] for stage 3 records.
- **`changjuan re-extract` CLI verb** — `re-extract --chapter N --prompt-version <v> [--reload-only]`. Loads an existing YAML or instructs the user to invoke the corresponding skill version.
- **`changjuan extract` CLI verb** — repurposed as a non-LLM pre-flight checklist (corpus present, chunks present, latest skill present, schema-yaml-not-drifted) printing the copy-paste-ready skill invocation.
- **`changjuan extract-load` CLI verb** — Python loader/validator that consumes the skill's YAML, applies the two static invariants, computes confidence, and writes `candidate_*` rows + `candidate_facts`.
- **`changjuan eval --chapter N` CLI verb** — runs the golden precision/recall harness, prints the report, exits non-zero on threshold breach.
- **`changjuan list-unresolved-dates [--chapter N]`** + **`changjuan resolve-relative-date --event-id <id> --anchor-event-id <id>`** — minimal curator path for cross-chunk relative date anchoring (no UI; CLI + audit_log).
- **`changjuan qa-sample <pipeline_run_id>`** + **`changjuan qa-load --run-id <id> --qa-file <p>`** — sampling QA harness CLIs.
- **Phase-1 backlog flush** — items #1, #2, #3, #5, #6, #7, #8, #9, #10 from `scripts/phase2-prep.sh::PHASE1_DEFERRED`. Only #4 (`explicit_reign_other` date parsing) stays deferred.
- **Knowledge articles** — `concepts/pipeline/extraction.md` (new), `concepts/pipeline/incremental.md` (new); extensions to `dates-and-reigns.md`, `load-and-merge.md`, `confidence-and-invariants.md`.

### Out of scope (Phase 2 — deferred to Phase 3+)

- **Stage 5 (Link & dedup)** — the spec's highest-stakes stage. Phase 2's candidate_* rows land in canonical via Phase 1's stage-7 exact-canonical-name matching only; 重耳 and 晋文公 stay as separate Persons until Phase 3 ships the linker.
- **Stage 6 (Cross-canon)** — needs 左传/史记 corpora first.
- **Stage 8 (Curation Streamlit app)** — Phase 2 reaches its curator surface via CLI only.
- **Ch.~40 golden annotation** — bundled with Phase 3 stage-5 work where people-density matters.
- **`explicit_reign_other` (#4)** — Ch.1 (Western Zhou collapse) is 周王-anchored; 晋/齐/楚 reign systems become important from Ch.~10 onward.
- **Full-corpus production run** — Phase 2 runs against Ch.1 only.
- **Cross-chunk relative date *automation*** — Phase 2 provides a *manual* path (CLI + schema field); automation is Phase 3+ if a pattern emerges.

### Success criteria

1. `changjuan extract --chapter 1` returns ✓ for all pre-flight checks against the real Ch.1 chunks.
2. `/changjuan-extract chapter:1` in Claude Code produces `data/extractions/ch01/extract-v1.yaml` and, as its final step, runs `changjuan extract-load --chapter 1 --extraction-file ... --prompt-version v1` to populate `candidate_*` tables.
3. The verbatim-quote invariant and per-field justification static check pass on the loaded records; any failures are recorded in `pipeline_runs.stats_json.invariant_violations`.
4. `changjuan eval --chapter 1` reports per-entity-type precision/recall ≥ the targets defined in Section 6 (or recalibrated targets, recorded inline).
5. `changjuan re-extract --chapter 1 --prompt-version v2` produces a second pipeline_run; stage 7's merge semantics apply; scalar disagreements with v1 become Conflict rows; new variants accumulate; `entity_citations` carries citations from both runs.
6. The sampling QA harness runs end-to-end on Ch.1's extraction: 5% sample selected deterministically, `/changjuan-verify-sample` produces verdicts, `changjuan qa-load` writes to `qa_samples` and updates `stats_json.claim_defensible_sample.mismatch_rate`.
7. The full test suite is green (`uv run pytest -q`), all four pre-commit hooks clean, `phase2-prep.sh` reports the new Phase-2 acceptance section green.
8. `concepts/pipeline/extraction.md` and `concepts/pipeline/incremental.md` exist with `affects:` globs covering every new file in `pipeline/` and `.claude/skills/`.

---

## 2. Build Sequence

Approach B (annotate-first): the golden chapter is annotated early so the canonical schema gets exercised before any prompt exists, surfacing schema bugs at the cheapest fix point. The Phase-1 backlog is split: *blocking* prereqs ship at the start; *cleanup* items flush at the end.

### Step 1 — Blocking prerequisites (no LLM yet)

1. **`_PARA_SEP` chunking fix (#1)** — change `pipeline/stage2_chunk.py` regex to `r"\r?\n+"`; add a regression test seeded with single-`\n`-separated paragraphs asserting >>1 chunks. Re-chunk the corpus. Record new chunk count baseline in `knowledge/log.md`. Update `concepts/pipeline/architecture.md`.
2. **Stage 7 module split (#5)** — `pipeline/stage7_load.py` → `pipeline/stage7_load/{persons,audit,helpers,citations}.py`. Pure refactor; public API stable; all Phase 1 tests still pass.
3. **Citation accumulation in stage 7 (#7)** — `citations.py:record_citation(conn, entity_kind, entity_id, citation_id)` idempotent insert into `entity_citations`; called from every create/update path in `persons.py`. Tests assert that re-loading the same candidate produces one canonical row but two `entity_citations` rows.

### Step 2 — Golden Ch.1 annotation infrastructure

4. Create `tests/golden/ch01/{persons,events,places,states,citations,relations}.yaml` by hand, reading the now-correctly-chunked Ch.1 text.
5. **`tests/golden/loader.py`** — loads + schema-validates the YAML; asserts every referenced `citation_id` exists in `citations.yaml`; asserts every referenced `chunk_id` exists in `corpus.sqlite`; validates Date dicts against the `inference_kind` enum.
6. **`tests/golden/precision_recall.py`** — pure code; given a golden set and a candidate set, returns per-entity-type P/R + a mismatch report. Tested with synthetic inputs first.

### Step 3 — Python LLM-adjacent infrastructure (no SDK)

7. **`pipeline/schemas/extract_output.py`** — canonical extraction-output schema as a Python dict (the source of truth).
8. **`pipeline/confidence.py` stub (#6)** — `score_extraction_record(record) -> float` in [0.7, 0.95]; function of citation quote length + justification completeness + base offset. Update `concepts/verification/confidence-and-invariants.md`.

### Step 4 — Stage 3 loader/validator (the Python half)

9. **`pipeline/stage3_extract.py`** — `load_extraction(conn, chapter_num, extraction_file, *, prompt_version, pipeline_run_id)`. Reads YAML; validates schema, verbatim-quote, justification-substring, chunk-local id resolution, citation FK integrity, `inference_kind` allowlist; calls `pipeline.dates.resolve_relative_dates`; computes confidence; writes `candidate_*` rows + `candidate_facts`; records a `pipeline_runs` row.
10. **`changjuan extract-load` CLI verb** — thin wrapper over `load_extraction`.
11. **`changjuan extract` CLI verb** — pre-flight checklist (no LLM); prints copy-paste skill invocation.
12. **Knowledge article** — create `concepts/pipeline/extraction.md` with `affects:` globs covering `pipeline/stage3_extract.py`, `pipeline/schemas/extract_output.py`, `pipeline/confidence.py`, `.claude/skills/changjuan-extract*/**`.

### Step 5 — Stage 7 candidate loaders + Stage 4 relative-date wiring

13. **`pipeline/stage7_load/{events,places,states,relations}.py`** — field-level merge semantics matching `persons.py`. Each module gets its own test file.
14. **`pipeline/dates.py:resolve_relative_dates`** — within-chunk walkback + honor explicit `relative_anchor_event_id` when present. Cycle detection; offset parsing from `original` ("其年"=0, "明年"=+1, "其后N年"=+N). Invoked by `stage3_extract.py` after YAML parsing, before candidate writes.
15. **Cross-chunk manual anchor CLIs** — `changjuan list-unresolved-dates [--chapter N]` and `changjuan resolve-relative-date --event-id <id> --anchor-event-id <id>`. Both write `audit_log` entries with `actor='curator:<user>'`.

### Step 6 — Claude Code skill + prompt iteration loop

16. **`.claude/skills/changjuan-extract/`** — `SKILL.md` (frontmatter + outline), `system-prompt.md` (Chinese instructions), `extraction-schema.yaml` (regenerated from `pipeline/schemas/extract_output.py` by a pre-commit hook), `examples/` (few-shot drawn from golden Ch.1).
17. **First extraction run** — invoke `/changjuan-extract chapter:1` in Claude Code; skill produces `data/extractions/ch01/extract-v1.yaml` and chains to `changjuan extract-load`. Record baseline P/R via `changjuan eval --chapter 1`.
18. **Iteration loop** — adjust skill → bump to `changjuan-extract-v2` directory → invoke → eval. Repeat until P/R hits the Section 6 targets. Record each iteration's P/R in `knowledge/log.md`.
19. **`changjuan re-extract` CLI verb** — reload-only mode + missing-file user-instruction path. Tested against the v1 → v2 flow.
20. **Knowledge article** — create `concepts/pipeline/incremental.md` covering re-extract semantics, prompt-version-via-skill-directory convention, Conflict-on-divergence.

### Step 7 — Sampling QA harness

21. **`pipeline/qa_sampling.py`** — deterministic sampler (stable hash of `pipeline_run_id`, `record_id`, `field`); 5% target with floor=30, ceiling=250.
22. **`.claude/skills/changjuan-verify-sample/SKILL.md`** + verifier prompt.
23. **`changjuan qa-sample <pipeline_run_id>`** + **`changjuan qa-load --run-id <id> --qa-file <p>`** CLIs.
24. **Wire into `pipeline_runs.stats_json`** — `claim_defensible_sample = {sample_size, yes, partial, no, mismatch_rate}`; append `"claim_defensible_mismatch_rate"` to `thresholds_breached` when `mismatch_rate > config.QA_MISMATCH_THRESHOLD` (default 0.10).

### Step 8 — Backlog flush

25. Reign-year boundary tests (#2) — 鲁僖公33年→627, 鲁文公1年→626, 鲁庄公32年→662 against the existing parser.
26. `stage1_ingest` insert-count fix (#3) — return actual inserts, not `len(rows)`.
27. Chunking edge-case tests (#9) — empty paragraphs, oversized single paragraph.
28. `test_load_updates_scalar_when_new_confidence_higher` branch coverage fix (#10) — actually exercise the `>+δ` branch.
29. Remove flushed items from `scripts/phase2-prep.sh::PHASE1_DEFERRED`; create `PHASE2_DEFERRED` array with the Phase 3 starter backlog (Section 7).

### Step 9 — Phase 2 acceptance

30. Extend `scripts/phase2-prep.sh` with new sections 11–14 (golden P/R, QA harness wired, re-extract semantics, backlog state).
31. Run the script; confirm all green.
32. Append "[2026-MM-DD] Phase 2 complete" to `knowledge/log.md` with the golden P/R baseline + Phase 3 starter backlog.

### Parallelism notes for the plan stage

- Steps 1, 2, 3 are sequential (1 must land before 2 — the YAML chunk_ids depend on the re-chunked corpus).
- Step 4 (loader/validator) and Step 5 (stage 7 loaders + relative dates) can interleave once Step 3 is done.
- Step 2 (golden annotation) can run in parallel with Steps 3–5 once Step 1 lands. The annotator can be a separate Claude session.
- Step 6 (iteration loop) is the longest single step. It cannot start until Steps 2–5 are done.
- Step 7 (QA harness) is independent of Step 6's prompt tuning; can run in parallel.
- Step 8 (backlog flush) is intentionally last to avoid distracting from the core Phase 2 mission.

---

## 3. Golden Ch.1 Annotation System

### Directory layout

```text
tests/golden/
├── __init__.py
├── loader.py
├── precision_recall.py
└── ch01/
    ├── README.md             # annotation conventions, decisions log, source edition
    ├── persons.yaml
    ├── states.yaml
    ├── places.yaml
    ├── events.yaml
    ├── citations.yaml
    └── relations.yaml
```

Citations are written once in `citations.yaml` with stable ids (e.g., `cit:ch01-p3-001`) and referenced by id from the other files. Relations live in a typed-envelope file (every record has a `kind:` field) so all relation kinds share one file.

### YAML record shape (sketches)

`persons.yaml`:
```yaml
- id: per:zhou-you-wang
  canonical_name: 周幽王
  variants:
    - { variant: 宫涅, kind: 本名 }
    - { variant: 幽王,  kind: 谥号 }
  gender: male
  death_date:
    year_bce: 771
    uncertainty: point
    original: 周幽王十一年
    inference_kind: explicit_reign_zhou
  state_id: sta:zhou
  citations: [cit:ch01-p2-003, cit:ch01-p4-008]
```

`events.yaml`:
```yaml
- id: evt:quan-rong-attack-haojing-771bce
  type: 攻陷
  date:
    year_bce: 771
    uncertainty: point
    inference_kind: explicit_reign_zhou
  outcome: 西周亡
  summary: 犬戎攻入镐京，杀周幽王于骊山下
  primary_place_id: pla:haojing
  citations: [cit:ch01-p5-014]
```

`citations.yaml`:
```yaml
- id: cit:ch01-p2-003
  chunk_id: chk:ch01-002
  paragraph: 2
  span: [120, 168]
  quote: "幽王无道，宠褒姒，废申后及太子宜臼"
```

`relations.yaml` (typed envelope):
```yaml
- kind: event_participant
  event_id: evt:quan-rong-attack-haojing-771bce
  person_id: per:zhou-you-wang
  role: 死
  citation_id: cit:ch01-p5-014
```

### Cross-chunk relative-date anchors in the golden

A golden event may set an explicit anchor that crosses chunk boundaries:

```yaml
- id: evt:foo-five-years-later
  type: 朝聘
  date:
    original: 其后五年
    inference_kind: relative_to_prior_event
    relative_anchor_event_id: evt:zhou-you-wang-killed-771bce   # cross-chunk
  citations: [cit:ch01-p12-042]
```

The loader resolves anchors transitively (anchor's anchor → ...) and rejects cycles. The skill itself is told *not* to attempt cross-chunk anchoring — those cases get `relative_anchor_event_id: null` in the skill's output and surface in the post-extraction `changjuan list-unresolved-dates` queue.

### Loader behavior (`tests/golden/loader.py`)

```python
def load_golden(chapter: str) -> GoldenSet:
    """Load all YAML files under tests/golden/{chapter}/, validate, return typed dict."""
```

Validation:
1. Each file parses as YAML (safe loader).
2. Every referenced `citation_id` exists in `citations.yaml`.
3. Every referenced `chunk_id` exists in `corpus.sqlite` (test-time check).
4. Date dicts match the `inference_kind` enum from `pipeline/dates.py`.
5. Relative-date anchors exist and don't cycle.
6. Mismatches raise structured errors so the annotator can fix.

### Precision/recall harness (`tests/golden/precision_recall.py`)

```python
def compute_pr(golden: GoldenSet, candidates: CandidateSet) -> PRReport:
    """Per-entity-type precision/recall + a free-text mismatch report.

    Matching rules:
      Person:     variant overlap (canonical_name in candidate.variants[] or vice versa)
                  AND state_id agreement (or both missing)
      Event:      type match + date.year_bce within ±1 year + primary_place_id match
      Place:      name match (canonical or any variant)
      State:      name match
      Relations:  tuple match on (kind, from, to, role)
    """
```

Returns:
- `per_entity_type` dict matching `stats_json.extraction.per_entity_type` shape (precision, recall, tp, fp, fn).
- `mismatches`: list of `(kind, expected, actual_or_none, reason)` — the iteration-loop targets.

### Where the harness runs

- `@pytest.mark.golden` in `tests/integration/test_golden_ch01.py`. Excluded from default pytest runs (slower; depends on corpus.sqlite + a recorded extraction fixture).
- `changjuan eval --chapter N` CLI verb for the interactive prompt-iteration loop. Same pure-code core; different presentation.

### Annotation conventions (recorded in `tests/golden/ch01/README.md`)

- Source edition: pinned via the `dongzhoulieguozhi` repo's SHA at annotation time.
- Tie-breaking rules for variant kinds (本名/字/谥号/封号/别名) — pick consistently; note the rule.
- What counts as an event vs. a narrative aside — judgment calls go in the decisions log.
- Decisions log: append-only list of judgment calls; becomes the skill's later instruction-tuning material.

### Golden treats variants as separate Persons in Phase 2

Phase 2's stage-7 loader matches only by canonical_name. 重耳 and 晋文公 land as two separate Persons. The golden YAML reflects this reality: the annotator records them as separate `per:*` ids with overlapping variant lists. Phase 3's stage-5 linker is what merges them; the golden gets updated to reflect the merge at that point. The Phase 2 golden is honest about Phase 2's actual capability.

---

## 4. Stage 3 Architecture — Claude-Code-Skill-Driven

### Why this shape

This project has no `ANTHROPIC_API_KEY` available; the curator works through a Claude Code subscription. Stage 3 is therefore a **Claude Code skill** that does the LLM-judgment work, plus a **Python loader/validator** that consumes the skill's output. No Anthropic SDK is integrated into the codebase.

This trade has real consequences:
- ✅ No API key management, no SDK dependency, no prompt-caching machinery, no retry/backoff.
- ✅ The skill can use TodoWrite, read existing canonical entities, ask clarifying questions when sources are ambiguous — none of which a stateless API call can do.
- ✅ Iteration cycle: edit skill `.md` → invoke skill in Claude Code → review → repeat.
- ⚠️ Batch processing of many chapters is manual — one skill invocation per chapter. For Phase 2 (Ch.1 only) this doesn't matter; for Phase 3+ full-corpus runs, this is the price.
- ⚠️ The "different model" defense for sampling QA (spec § 3 — Opus 4.7 verifier vs. Sonnet 4.6 extractor) is downgraded to "different prompt only," because a Claude Code session has one active model at a time. The spec's escape hatch ("a different model **or** a different prompt template") makes this acceptable; documented as a known limitation in `concepts/verification/confidence-and-invariants.md`.

### The two-actor architecture

1. **Claude Code skill** (`.claude/skills/changjuan-extract/`) — does the LLM judgment work. Reads chunks, performs extraction following the system prompt + schema, writes one YAML output file, chains to the CLI loader as its final step.
2. **Python loader/validator** (`pipeline/stage3_extract.py`) — pure deterministic code. Reads the YAML, runs invariant checks, writes `candidate_*` rows, computes confidence.

The skill is the entry point; the CLI is the contract.

### Module + skill layout

```text
.claude/
└── skills/
    ├── changjuan-extract/
    │   ├── SKILL.md
    │   ├── system-prompt.md
    │   ├── extraction-schema.yaml          # regenerated from Python schema; pre-commit asserts no diff
    │   └── examples/                       # few-shot drawn from golden Ch.1
    └── changjuan-verify-sample/
        ├── SKILL.md
        └── verifier-prompt.md

pipeline/
├── stage3_extract.py                       # YAML → validate → candidate_* rows
├── confidence.py
├── qa_sampling.py
└── schemas/
    └── extract_output.py                   # canonical schema as a Python dict (source of truth)

data/
└── extractions/                            # gitignored; agent output lives here
    └── ch01/
        ├── extract-v1.yaml
        └── extract-v2.yaml
```

### Single source of truth for the extraction schema

`pipeline/schemas/extract_output.py` defines the canonical Python dict. A pre-commit hook regenerates `.claude/skills/changjuan-extract/extraction-schema.yaml` from it and asserts no diff — the skill and the validator can never drift.

### The extraction skill (`.claude/skills/changjuan-extract/SKILL.md`)

Frontmatter (sketch):
```yaml
---
name: changjuan-extract
description: Extract structured entities (persons, events, places, states, relations) from one chapter of 东周列国志 into a YAML file matching the canonical schema. Use when the user asks to extract chapter N, run stage 3 on a chapter, or re-extract a chapter with a new prompt version.
---
```

Body (outline; the file is written out in detail in step 16):
1. **Inputs the agent gathers itself**: chapter number from invocation; chunks for that chapter queried from `data/corpus.sqlite`; the canonical schema from `extraction-schema.yaml`; the system prompt from `system-prompt.md`; the `prompt_version` from the skill's directory name suffix.
2. **Extraction work**: for each chunk, identify persons/events/places/states/relations; each record carries a chunk-local id (`p1`, `e1`, …), a citation block with verbatim quote, and per-field justification quotes.
3. **Output**: accumulate all records into `data/extractions/ch{N}/extract-{prompt_version}.yaml`, format matching the golden YAML layout from Section 3.
4. **Final step (chained)**: invoke `uv run changjuan extract-load --chapter {N} --extraction-file data/extractions/ch{N}/extract-{prompt_version}.yaml --prompt-version {prompt_version}`. On validation failure, report errors and stop.
5. **Reporting**: print a summary (counts per entity type, chunks the agent struggled with, the CLI load result).

The annotator's **decisions log** from `tests/golden/ch01/README.md` is the source material for the system prompt — every "what counts as an event" / "tie-breaking rule" gets encoded as guidance. The skill is the prompt.

### Re-extraction = skill versioning

Each prompt iteration is a new skill directory:
```
.claude/skills/changjuan-extract/             # = v1
.claude/skills/changjuan-extract-v2/          # = v2
.claude/skills/changjuan-extract-v3/          # = v3
```

The CLI's `--prompt-version` matches the directory suffix. The `audit_log.actor` uses `extract@v1` / `extract@v2` per the founding spec's convention (§ 7.4). `changjuan re-extract --chapter 1 --prompt-version v2` either:
- (a) loads an existing `data/extractions/ch01/extract-v2.yaml` if present (useful when fixing a validator bug without re-running the agent); or
- (b) exits non-zero with a clear instruction to invoke `/changjuan-extract-v2 chapter:1` in Claude Code first.

### CLI surface

- `changjuan extract --chapter N` — **non-LLM pre-flight checklist.** Verifies: corpus.sqlite present; chapter N has chunks (>1 after the `_PARA_SEP` fix); latest `.claude/skills/changjuan-extract*/` exists with SKILL.md + system-prompt.md + extraction-schema.yaml; extraction-schema.yaml matches `pipeline/schemas/extract_output.py`. Prints ✓/✗ and the copy-paste skill invocation. Exits non-zero on any failure.
- `changjuan extract-load --chapter N --extraction-file <path> --prompt-version <v>` — Python loader. Reads YAML, validates, writes candidate_* rows.
- `changjuan re-extract --chapter N --prompt-version <v> [--reload-only]` — described above.
- `changjuan eval --chapter N` — golden P/R harness.

### `pipeline/stage3_extract.py` — what the loader does

```python
def load_extraction(
    conn: Connection,
    chapter_num: int,
    extraction_file: Path,
    *,
    prompt_version: str,
    pipeline_run_id: str,
) -> LoadStats:
    """Validate the skill's YAML output and write candidate_* rows.

    Steps:
      1. Read YAML, parse into typed dicts using the same loader as tests/golden/loader.py.
      2. For each record, verify:
           - The chunk_id exists in corpus.sqlite.
           - The citation.quote is a verbatim substring of chunk.text (NFC-normalized).
           - Every scalar field's justification_quote is non-empty and substring of citation.quote.
           - The inference_kind is in the Phase 2 allowlist (rejects explicit_reign_other).
      3. Resolve relative dates: walkback within-chunk, plus explicit relative_anchor_event_id.
      4. Compute confidence per record via pipeline.confidence.score_extraction_record.
      5. Insert candidate_persons / candidate_events / candidate_places / candidate_states /
         candidate_*_relations rows, all tagged with pipeline_run_id and prompt_version.
      6. Populate candidate_facts with per-field justifications.
      7. Write a pipeline_runs row: stage='extract-load', prompt_version=prompt_version,
         stats_json={counts, invariant_violations, ...}.
    """
```

Per-record invariant violations don't halt the load — they're recorded in `pipeline_runs.stats_json.invariant_violations` and the offending record is excluded from the candidate write. Fail-soft. Subsequent runs can fix the failed records.

### The two static invariants

1. **Verbatim-quote invariant** — `citation.quote in chunk.text` after Unicode NFC normalization on both sides.
2. **Per-field justification static check** — every scalar field's `justification_quote` is non-empty AND `in record.citation.quote`.

Both raise `InvariantError` per-record; the loader logs and skips. The deeper claim-defensible verification is the sampling QA's job (Section 6).

### Confidence scoring (`pipeline/confidence.py`)

```python
def score_extraction_record(record: ExtractedRecord) -> float:
    base = 0.7
    citation_bonus = min(len(record.citation.quote) / 100, 0.15)
    justification_completeness = 0.10 if all_scalar_fields_have_justification(record) else 0.0
    return min(base + citation_bonus + justification_completeness, 0.95)
```

Hardcoded ceiling at 0.95 — stage 3 never claims 1.0; that's reserved for curated records. The function is the registered entry point so callers don't change when scoring gets smarter in later phases.

### Knowledge article

`concepts/pipeline/extraction.md` (new) covers:
- The skill-driven architecture and why (no API key requirement; subscription-bundled).
- The skill/loader contract (skill produces YAML; loader validates + persists).
- The two static invariants and where each is enforced.
- The chunk-local id scheme.
- Prompt versioning via skill directory naming.
- The "different prompt only" sampling QA limitation.

`affects:` globs: `.claude/skills/changjuan-extract*/**`, `pipeline/stage3_extract.py`, `pipeline/confidence.py`, `pipeline/schemas/extract_output.py`.

---

## 5. Stage 7 / Stage 4 Extensions + `re-extract` + Cross-Chunk Manual Anchor

All deterministic Python; unaffected by the skill-driven pivot.

### Stage 7 module split

```text
pipeline/stage7_load/
├── __init__.py            # re-exports the public API
├── persons.py             # moved from current stage7_load.py
├── events.py              # NEW
├── places.py              # NEW
├── states.py              # NEW
├── relations.py           # NEW
├── audit.py               # existing _audit helper, now shared
├── helpers.py             # _slugify, _create_*, citation FK resolution, date-merge helper
└── citations.py           # NEW — entity_citations accumulator
```

The split is the first commit of Step 5; pure refactor, all existing tests green, public API stable.

### Field-level merge semantics (uniform across kinds)

Phase 1's `persons.py` already implements citation accumulation, variant union, scalar update under `auto`/`curated` rules, and Conflict emission. The new loaders apply the same rules:

| Kind | Scalar fields needing merge | Relation-ish fields |
|---|---|---|
| Events | type, outcome, summary, primary_place_id, date_json | event_participants, event_places, event_relations |
| Places | name, type, lat, lon, coord_confidence, modern_equiv | (none) |
| States | name, ruling_clan, type, founded_date_json, ended_date_json | state_capitals |
| Relations | (relations themselves are append-mostly) | unique-key `(kind, from, to, role)` |

Date fields follow the spec § 7.2 rule: a more-precise Date (range → point, or tighter `uncertainty`) wins over a less-precise one even at slightly lower confidence. Logic centralized in `helpers.py:merge_date_field`.

### `entity_citations` accumulation

`citations.py:record_citation(conn, entity_kind, entity_id, citation_id)` — idempotent INSERT. Called from every `_create_*` and every `_update_*` path. Never overwrites. Tests assert that re-loading the same candidate produces one canonical row but two `entity_citations` rows.

### Stage 4 — `relative_to_prior_event` dereferencing

Phase 1 already shipped the parsing primitive: `pipeline/dates.py:parse_date(original, anchor=None)` resolves a relative reference against a provided anchor for the fixed token set in `_RELATIVE_OFFSETS` (其年, 明年, 次年, 去年, 前年, 是岁, 是年, 是+season). The offsets are in BCE arithmetic — "明年" = −1 because BCE years decrease as time advances.

**What Phase 2 adds on top of the parser:**

`pipeline/dates.py:resolve_relative_dates(records, db)`:

1. If `relative_anchor_event_id` is explicitly set → look up that event's `year_bce` (in the same candidate batch, or in canonical events). Apply the offset (resolution order below).
2. Else → walk back through this chunk's prior records in source order; build a rolling anchor; pass it into `parse_date(original, anchor=...)` for the current record.
3. If neither resolves → `year_bce` stays null; confidence reduced.

**Offset resolution for the explicit-anchor path**:
- If `original` is a token in the existing `_RELATIVE_OFFSETS` table (e.g., "明年") → use that offset (−1 in BCE arithmetic).
- Else if a curator-supplied `--offset N` accompanies the resolve CLI invocation → use `−N` (curator specifies calendar-years-later; we negate for BCE).
- Else → error with a clear message ("can't determine offset; either supply --offset or extend _RELATIVE_OFFSETS").

Cycle detection: resolution rejects with a clear error if an anchor's anchor (transitively) points back to the record being resolved.

Invoked by `pipeline/stage3_extract.py` after YAML parsing, before candidate writes. So `candidate_events` rows land with resolved `year_bce` values where possible.

**Test buckets** (`tests/unit/test_dates_relative.py`):
1. Single relative record after a resolved one → copies year via existing `parse_date(anchor=...)` path.
2. Cascading relatives from one anchor (其年 → 明年 → 又明年).
3. Relative with no prior in-chunk anchor and no explicit anchor → null `year_bce`, reduced confidence.
4. Relative after another unresolved relative → null `year_bce`.
5. Explicit `relative_anchor_event_id` (known-token `original`) → uses table offset, overrides walkback.
6. Explicit `relative_anchor_event_id` + curator `--offset N` (unknown-token `original` like "其后五年") → uses curator offset.
7. Dangling anchor (id doesn't exist) → error.
8. Anchor-chain (anchor's anchor) → resolves transitively.
9. Anchor cycle → rejected with clear error.

Cross-chunk *automatic* dereferencing is explicitly out of scope; flagged in `concepts/data-model/dates-and-reigns.md` with a Phase 3+ promotion path. Extending `_RELATIVE_OFFSETS` to cover numeric patterns like "其后N年" / "前N年" is also deferred — the manual CLI path covers the need for Phase 2.

### Cross-chunk manual anchor — schema + CLIs

**Schema extension:** the structured `Date` dict gets one optional field:

```json
{
  "year_bce": null,
  "uncertainty": "point",
  "original": "其后五年",
  "inference_kind": "relative_to_prior_event",
  "relative_anchor_event_id": "evt:zhou-you-wang-killed-771bce"
}
```

Explicit anchor wins over walkback. The schema change is additive; existing date_json values without the field continue to work.

**The skill is told NOT to attempt cross-chunk anchoring.** When it sees a relative reference whose anchor is in a prior chunk, it sets `inference_kind: relative_to_prior_event`, leaves `relative_anchor_event_id: null`, records the `original` phrase, and notes the case in its output report so the curator triages it.

**CLI verbs:**

- `changjuan list-unresolved-dates [--chapter N]` — lists candidate events with `inference_kind = relative_to_prior_event` AND `year_bce IS NULL` AND `relative_anchor_event_id IS NULL`, sorted by chapter + paragraph. Shows event id, the `original` Chinese phrase, surrounding chunk text excerpt, and nearby events that might be the anchor.
- `changjuan resolve-relative-date --event-id <id> --anchor-event-id <id> [--offset N]` — sets `relative_anchor_event_id` on the event's `date_json`, re-runs the offset-resolution path described under *Stage 4* above, writes the new `year_bce` + reduced confidence into the canonical row. `--offset` is the curator-supplied calendar-years-later when `original` is not a known token in `_RELATIVE_OFFSETS`. Emits an `audit_log` entry with `actor='curator:<user>'` so it's reversible and shows up in `field_history`. Exits non-zero with a clear message if either id doesn't exist, the anchor itself has no resolved `year_bce`, or the offset can't be determined.

### The `re-extract` CLI verb

```
changjuan re-extract --chapter N --prompt-version <v> [--reload-only]
```

- If `data/extractions/ch{N}/extract-{v}.yaml` exists → re-run `extract-load` only. Creates a new `pipeline_run_id` tagged with `prompt_version=<v>`.
- If the file does not exist → print: `"Skill .claude/skills/changjuan-extract-{v}/ has not been run yet for chapter {N}. Invoke /changjuan-extract-{v} chapter:{N} in Claude Code first."` and exit non-zero.
- The reload path triggers stage 7's existing merge semantics: scalar disagreements between v1 and v2 candidates become Conflict rows; new variants accumulate; citations accumulate via `entity_citations`; `curated` records remain untouched.

This is the founding spec's § 7.3 promise made real: **improving a prompt is always safe — re-extraction adds findings, never destroys curator work.** Tested end-to-end in `tests/integration/test_re_extract_accumulates.py`.

### Knowledge article updates

- `concepts/pipeline/load-and-merge.md` — extended with new entity loaders + citation accumulation.
- `concepts/data-model/dates-and-reigns.md` — extended with `relative_to_prior_event` semantics + cross-chunk anchor + cycle prevention + offset-parsing convention.
- `concepts/pipeline/incremental.md` (new) — re-extract semantics, prompt-version-via-skill-directory convention, `pipeline_run_id` lineage, Conflict-on-divergence behavior.

---

## 6. QA & Testing Strategy

Three layers of quality signal, each catching a different failure mode. Tests follow the founding spec's two buckets: **blocking** (CI-fail) and **tracked metrics** (block stage-9 freeze only).

### Layer 1 — Static invariants (blocking)

Run by `pipeline/stage3_extract.py` on every YAML the skill produces.

| Check | What it catches |
|---|---|
| Verbatim-quote invariant | Fabricated quotes; quotes from the wrong chunk |
| Per-field justification static check | Empty justifications; justifications not in the quote |
| JSON Schema validation | Type errors, missing required fields, unknown enums, malformed dates |
| Chunk-local id resolution | An event referencing `p7` when only `p1`-`p5` were declared |
| Citation FK integrity | A citation pointing to a chunk_id that doesn't exist |
| `inference_kind` allowlist | Skill produces `explicit_reign_other` (out of Phase 2 scope) |

Violations record into `pipeline_runs.stats_json.invariant_violations`; the offending record is skipped; the rest of the load continues.

### Layer 2 — Golden Ch.1 precision/recall (blocking once thresholds set)

The primary Phase 2 quality signal. `tests/golden/precision_recall.py` consumes the golden YAML + a candidate set and returns per-entity-type P/R + a mismatch report.

**The iteration CLI:**
```
changjuan eval --chapter 1
```

Runs load chunks → load candidates → compare-to-golden → print report.

**Threshold targets (placeholders; recalibrated after Step 6's first measurement):**

| Entity | Precision | Recall | Rationale |
|---|---|---|---|
| Person | ≥ 0.90 | ≥ 0.85 | Variant-rich; should be cheap to get right. |
| Event | ≥ 0.80 | ≥ 0.70 | Hardest; type/outcome judgments vary. |
| Place | ≥ 0.85 | ≥ 0.75 | Usually unambiguous. |
| State | ≥ 0.95 | ≥ 0.90 | Small closed set (~15 states). |
| Relations (all kinds) | ≥ 0.75 | ≥ 0.65 | Compound entity errors. |

Thresholds live in `pipeline/config.py`. The plan stage explicitly includes the calibration step.

**Where it runs:**
- `@pytest.mark.golden` in `tests/integration/test_golden_ch01.py`. Skipped without `--run-golden` flag.
- `changjuan eval --chapter N` for interactive iteration.

### Layer 3 — Sampling QA harness (tracked metric)

Phase 2 builds the harness; Phase 2's primary signal is Layer 2 (golden P/R). The harness's value pays off in Phase 3+ when extraction runs against non-golden chapters.

**The verify skill** (`.claude/skills/changjuan-verify-sample/SKILL.md`):
- Frontmatter declares the skill's purpose: given a `pipeline_run_id`, re-evaluate the deterministic 5% sample.
- For each `(quote, field, value)` triple: yes / no / partial verdict, with a brief reason.
- Writes to `data/qa/{pipeline_run_id}.yaml`. Final step: `changjuan qa-load --run-id <id> --qa-file <path>`.

**Deterministic sampler** (`pipeline/qa_sampling.py`):
- Stable hash of `(pipeline_run_id, record_id, field)` → in-sample / out-of-sample.
- 5% target, floor=30, ceiling=250.
- Reproducible: the same `pipeline_run_id` always gets the same sample.

**CLIs:**
- `changjuan qa-sample <pipeline_run_id>` — prints the sample list (run before the verify skill so the agent sees what to verify).
- `changjuan qa-load --run-id <id> --qa-file <p>` — ingests skill output; writes `qa_samples` rows; updates `pipeline_runs.stats_json.claim_defensible_sample = {sample_size, yes, partial, no, mismatch_rate}`.

**Threshold:** if `mismatch_rate > config.QA_MISMATCH_THRESHOLD` (default 0.10), append `"claim_defensible_mismatch_rate"` to `pipeline_runs.stats_json.thresholds_breached`. This blocks future stage-9 freezes (Phase 3+ concern).

**Known limitation (Phase 2):** verifier uses the *same model* as the extractor (Claude Code session has one active model at a time). Decorrelation by prompt only, not by model. Documented in `concepts/verification/confidence-and-invariants.md`.

### Unit tests — per-module coverage

New files under `tests/unit/`:
- `test_stage7_load_events.py`
- `test_stage7_load_places.py`
- `test_stage7_load_states.py`
- `test_stage7_load_relations.py`
- `test_stage7_citations.py` (accumulation, idempotence)
- `test_dates_relative.py` (within-chunk + cross-chunk anchor + cycles)
- `test_confidence.py` (stub behavior)
- `test_stage3_validator.py` (verbatim, justification, schema, chunk-local id, citation FK)
- `test_golden_loader.py` (schema validation, citation-id integrity, chunk-id FK)
- `test_precision_recall.py` (synthetic golden + candidates, P/R math)
- `test_qa_sampling.py` (determinism, floor/ceiling, 5% target)
- `test_re_extract.py` (reload-only mode, prompt_version handling, missing-file error)
- `test_extract_load.py` (end-to-end YAML → candidate_* rows with golden Ch.1 fixture)
- `test_extract_preflight.py` (pre-flight CLI verb checklist)

The existing `tests/unit/test_stage7_load.py` is split per the module restructure.

### Integration tests

- `tests/integration/test_golden_ch01.py` — `@pytest.mark.golden`. Loads golden YAML; loads candidates from a recorded extraction fixture at `tests/fixtures/ch01-extraction-vN.yaml` (committed so CI doesn't need to invoke the skill); runs precision/recall; asserts thresholds. Note: this is the committed fixture path; runtime skill outputs live in the gitignored `data/extractions/` per Section 4.
- `tests/integration/test_re_extract_accumulates.py` — `@pytest.mark.integration`. Synthetic two-version flow: extract → load → re-extract → assert variants accumulated, scalar disagreements became Conflicts, citations both present, `curated` field untouched.

### `phase2-prep.sh` extensions

New sections in the readiness check:
- § 11. Golden Ch.1 — runs `changjuan eval --chapter 1` if a recorded extraction exists; reports P/R per entity type, pass/fail vs thresholds.
- § 12. QA sampling harness — runs `changjuan qa-load --dry-run` to validate the qa_samples machinery is wired.
- § 13. Re-extract semantics — runs `tests/integration/test_re_extract_accumulates.py` and reports.
- § 14. Phase 1 deferred backlog — after the flush, should print "1 item remaining" (#4 only).

Summary section gets a Phase-2-specific block showing golden P/R per entity type alongside the existing pass/warn/fail counts.

### Deliberately not tested in Phase 2

- **The skill itself.** Can't unit-test an LLM-driven Claude Code skill in pytest. The test for the skill is "does its output, fed into the validator + golden harness, hit the thresholds?" — Layer 2.
- **Stage 5 (linking) behavior.** Phase 2's candidate_* rows land in canonical via Phase 1's exact-canonical-name match. 重耳 / 晋文公 stay separate. The golden YAML reflects this.
- **Cross-canon validation** (stage 6). Out of scope.
- **Streamlit curator UI** (stage 8). Out of scope.

---

## 7. Definition of Done & Phase 3 Backlog

### Acceptance checklist

Phase 2 is done when **all** of these are green:

**Code & infrastructure**
- `_PARA_SEP` chunking fix landed; `changjuan ingest && changjuan chunk` against the real corpus produces >>108 chunks; new chunk-count baseline recorded in `knowledge/log.md`.
- `pipeline/stage7_load/` is a package; old monolith deleted; public API stable; Phase 1 tests still green.
- `pipeline/stage7_load/citations.py` populates `entity_citations` on every create/update.
- `pipeline/stage7_load/{events,places,states,relations}.py` implement field-level merge.
- `pipeline/dates.py` resolves `relative_to_prior_event` within-chunk + honors explicit `relative_anchor_event_id`.
- `pipeline/confidence.py` exposes `score_extraction_record` returning [0.7, 0.95].
- `pipeline/stage3_extract.py` loads + validates skill-produced YAML and writes candidate_* rows.
- `pipeline/schemas/extract_output.py` is the canonical extraction schema; pre-commit regenerates `extraction-schema.yaml` and asserts no diff.

**Skills**
- `.claude/skills/changjuan-extract/` discoverable in Claude Code; `/changjuan-extract chapter:1` works end-to-end.
- `.claude/skills/changjuan-verify-sample/` exists.

**CLI**
- `changjuan extract --chapter N` pre-flight returns ✓ for chapter 1; prints copy-paste skill invocation.
- `changjuan extract-load --chapter N --extraction-file <path> --prompt-version <v>` validates + loads.
- `changjuan re-extract --chapter N --prompt-version <v>` works for both reload-only and missing-file paths.
- `changjuan eval --chapter 1` runs golden P/R; prints report; exits non-zero on threshold breach.
- `changjuan list-unresolved-dates [--chapter N]` lists candidates for cross-chunk anchor annotation.
- `changjuan resolve-relative-date --event-id <id> --anchor-event-id <id> [--offset N]` sets anchor + recomputes year_bce + writes audit_log.
- `changjuan qa-sample <pipeline_run_id>` + `changjuan qa-load --run-id <id> --qa-file <p>` work.

**Golden Ch.1**
- `tests/golden/ch01/*.yaml` exist and load cleanly via the loader.
- `tests/golden/ch01/README.md` records the annotation conventions + decisions log + source edition SHA.
- Golden precision/recall meets the placeholder thresholds (or recalibrated thresholds, recorded inline).

**Tests + hooks**
- All unit tests green; count is significantly higher than Phase 1's 59.
- Integration tests green: `test_golden_ch01.py`, `test_re_extract_accumulates.py`.
- All four pre-commit hooks clean.
- `./scripts/validate-articles` clean.

**Knowledge / living docs**
- `concepts/pipeline/extraction.md` (new) and `concepts/pipeline/incremental.md` (new) shipped with `affects:` globs covering every new file.
- `concepts/data-model/dates-and-reigns.md`, `concepts/pipeline/load-and-merge.md`, `concepts/verification/confidence-and-invariants.md` extended.
- `CLAUDE.md`'s article-mapping table includes new rows for all new modules + skill files.
- `knowledge/log.md` has a "[2026-MM-DD] Phase 2 complete" entry summarizing what shipped, the golden P/R baseline, and the Phase 3 starter backlog.

**Phase-prep script**
- `scripts/phase2-prep.sh::PHASE1_DEFERRED` reduced to one entry (#4 only).
- `scripts/phase2-prep.sh` extended with sections 11–14; all green.

### Phase 3 starter backlog (recorded as `PHASE2_DEFERRED` at Phase 2 close)

1. **Stage 5 (Link & dedup)** — the spec's highest-stakes stage. With Phase 2's golden + extraction working, Phase 3's first job is the linker so 重耳 / 晋文公 actually merge.
2. **`explicit_reign_other` date parsing (#4)** — needed when extraction expands beyond Ch.1.
3. **Reign tables for non-鲁/周 states** — curation task; sources from 杨伯峻 chronology.
4. **Ch.~40 golden annotation** — people-dense ground truth for stage 5 calibration.
5. **Curator UI (Stage 8)** — first queue: merge candidates from stage 5.
6. **Cross-chunk relative-date automation** — if a pattern emerges that the chunk-walkback couldn't catch.

Phase 3's spec gets written when Phase 2 ships, informed by what was learned from the golden iteration loop.

### Anti-patterns to resist near Phase 2 close

- **Don't tune the prompt past diminishing returns.** Once P/R hits the threshold, stop. The remaining gain is smaller than Phase 3's linker payoff.
- **Don't merge variants in Phase 2.** If the golden P/R suffers because stage-7-only matching can't merge 重耳 / 晋文公, update the golden to reflect Phase 2's reality (variants stay separate). The merge is stage 5's job.

---

*End of Phase 2 spec. Next step: writing-plans skill to produce the task-by-task implementation plan.*
