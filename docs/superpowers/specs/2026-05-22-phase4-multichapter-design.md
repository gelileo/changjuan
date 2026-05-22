# changjuan Phase 4 — Multi-Chapter Runs (Ch.2-5) + Reign-Table Expansion

**Date:** 2026-05-22
**Status:** Draft for review
**Scope:** Unlock chapters 2-5 by extending the date parser to non-鲁/周 reign anchors, building reign tables for the states those chapters reference, and exercising the existing extract → link → load pipeline at multi-chapter scale. Smoke test + spot-check sampling for quality; no new per-chapter goldens.

Layered on:
- Founding spec `2026-05-20-changjuan-design.md`
- Phase 2 spec `2026-05-20-phase2-extraction-design.md` (Stage 3, sampling QA, Ch.1 golden)
- Phase 3 spec `2026-05-21-phase3-linker-design.md` (Stage 5, regression set)

Where they conflict, this spec governs Phase 4.

---

## 1. Scope & Success Criteria

### In scope (Phase 4)

- **Reign tables for every Eastern-Zhou state referenced in Ch.2-5.** Stored as YAML at `data/reigns/<state>.yaml`. Produced by a new Claude Code skill `changjuan-extract-reigns`, hand-verified by the curator before commit. Expected coverage: ~8-12 states (the discovery script in §3 determines the exact list).
- **`explicit_reign_other` date parser support** in `pipeline/dates.py`. Reads `data/reigns/<state>.yaml`; resolves `{state_id, ruler_ref, reign_year}` triples to absolute BCE years. Behaviors for missing tables, ambiguous ruler refs, and out-of-range reign years are defined in §6.
- **`changjuan-extract-reigns` skill** at `.claude/skills/changjuan-extract-reigns/`. One state per invocation; emits draft YAML to stdout for human review.
- **Discovery script** `scripts/discover-states.py` — scans Ch.2-5 chapter text in `corpus.sqlite` for known state names; emits the worklist for §5b.
- **End-to-end runs on Ch.2, Ch.3, Ch.4, Ch.5** via the existing `extract → /changjuan-extract-v2 → link → load` pipeline. No pipeline shape changes.
- **Spot-check sampling QA** for the new chapters: reuse Phase 2's `changjuan qa-sample` + `changjuan-verify-sample` skill + `changjuan qa-load`. Bar: `mismatch_rate ≤ QA_MISMATCH_THRESHOLD` (0.10) across the new chapters.
- **Phase 4 acceptance script** `scripts/phase4-prep.sh` modeled after `phase3-prep.sh`. Phase 4-specific sections enumerated in §7.
- **Knowledge articles** — extend `concepts/data-model/dates-and-reigns.md` for `explicit_reign_other`; new article `concepts/pipeline/reign-extraction.md` (or skill-specific equivalent); update `concepts/runtime/cli.md` if any new verbs land.

### Out of scope (deferred to Phase 5+)

- **Chapters 6-108.** Phase 4 validates the multi-chapter approach on a bounded subset.
- **LLM judge for Stage 5 ambiguous cases.** Still gated on the curator UI per PHASE3_DEFERRED #1.
- **Curator UI (Stage 8).** PHASE3_DEFERRED #4.
- **Linker for events / places / states / relations.** Phase 3's name-match safety net handles cross-chapter dedup for non-person entities in Phase 4's scope. Linker breadth is Phase 5+ work.
- **Cross-chunk relative-date automation.** Phase 2's manual `changjuan resolve-relative-date` CLI suffices.
- **Per-chapter goldens for Ch.2-5.** Spot-check is the only quality signal.
- **Cross-canon checks at scale.** Phase 2's opt-in `--with-canon-check` exists but Phase 4 does not exercise it system-wide.
- **Adding 左传 / 史记 as corpora.** Phase 4's skill uses the LLM's training knowledge of Eastern-Zhou chronology; user verifies against the references of their choice during review.

### Success criteria

1. `data/reigns/` contains hand-verified YAMLs for every state referenced in Ch.2-5 (discovered via §3).
2. `pipeline/dates.py` resolves `explicit_reign_other` for any ruler reference present in those YAMLs.
3. Ch.2, Ch.3, Ch.4, Ch.5 each complete the full `extract → /changjuan-extract-v2 → link → load` pipeline without crashes / schema violations / orphan FKs.
4. `dates_out_of_range` counter is 0 across the four new chapters, or each instance is documented in the closeout log.
5. Spot-check `mismatch_rate ≤ 0.10`.
6. Ch.1 golden P/R still green (non-regression).
7. `phase2-prep.sh` + `phase3-prep.sh` + `phase4-prep.sh` all green.
8. Pre-commit hooks clean.

---

## 2. Build Sequence (Approach A — state-by-state)

Four sub-phases, with the work-shape pattern from Phase 2/3 (small commits, verification gates).

### Phase 4a — Infrastructure (~3 commits)

1. **Discovery script.** `scripts/discover-states.py` — reads `corpus.sqlite` documents for chapters 2-5, scans text for state-name occurrences using a hard-coded canonical list (周, 鲁, 晋, 齐, 楚, 秦, 宋, 郑, 卫, 陈, 蔡, 曹, 燕, 吴, 越, 申, plus any others the user adds). Output: sorted TSV `state_id\tcount\tchapters_referenced`.
2. **Date parser extension.** Implement `explicit_reign_other` resolution in `pipeline/dates.py`. Behavior in §6. Unit tests against a synthetic reign YAML.
3. **Reign-extract skill.** `.claude/skills/changjuan-extract-reigns/SKILL.md` + supporting files. One state per invocation. Spec in §4.

### Phase 4b — Reign-table production (1 commit per state, ~8-12 commits)

For each state in the discovery worklist:

4. Run `/changjuan-extract-reigns state:<state_id>` → draft YAML.
5. User reviews against references of their choice (Wikipedia, baike, history references). Corrects any date errors. Confirms ruler list completeness.
6. Commit the corrected YAML to `data/reigns/<state>.yaml`.

States may be processed in any order; failures don't block siblings.

### Phase 4c — Multi-chapter runs (1 commit per chapter, ~4 commits)

For N ∈ {2, 3, 4, 5}:

7. `uv run changjuan extract --chapter N` (pre-flight).
8. `/changjuan-extract-v2 chapter:N` (existing skill; writes candidate_* rows).
9. `uv run changjuan link <pipeline_run_id>` (Phase 3 linker).
10. `uv run changjuan load <pipeline_run_id>` (Phase 2 loader; honors `match_target_id`).
11. Run smoke checks (§7) on the loaded data. If green, commit the run's artifacts (the pipeline_run row + any new article touches the same-task rule requires).

If a chapter surfaces a missing reign table, add the state to the Phase 4b queue, complete it, and re-run the chapter.

### Phase 4d — Closeout (~2 commits)

12. **Spot-check sampling.** `changjuan qa-sample <run_id_per_chapter>` → YAML → `/changjuan-verify-sample` → `changjuan qa-load`. Aggregate mismatch rate across the four new runs.
13. **`scripts/phase4-prep.sh`** acceptance script + Phase 4 complete log entry in `knowledge/log.md`.

Estimated total: 16-20 commits.

---

## 3. Discovery Script

### Purpose

Determine which states Phase 4b must produce reign tables for, before any extraction begins.

### Inputs

`corpus.sqlite` (existing). Specifically: `chunks.text` for chunks belonging to documents with `chapter_num ∈ {2, 3, 4, 5}`.

### Logic

Hard-coded set of canonical state names:

```python
STATE_NAMES = {
    "周": "sta:zhou",
    "鲁": "sta:lu",
    "晋": "sta:jin",
    "齐": "sta:qi",
    "楚": "sta:chu",
    "秦": "sta:qin",
    "宋": "sta:song",
    "郑": "sta:zheng",
    "卫": "sta:wei",
    "陈": "sta:chen",
    "蔡": "sta:cai",
    "曹": "sta:cao",
    "燕": "sta:yan",
    "吴": "sta:wu",
    "越": "sta:yue",
    "申": "sta:shen",
    # extend as Phase 4 progresses
}
```

For each chapter, count substring occurrences of each state name (single-character; trivial regex). Emit TSV.

### Output

```
state_id    count    chapters
sta:zhou    47       2,3,4,5
sta:jin     31       2,3,4,5
sta:qi      18       2,3,4
sta:zheng   12       2,4
...
```

User filters to states with `count ≥ 3` and produces YAMLs for that worklist. (The threshold of 3 is the curator's heuristic for "actually referenced" vs "incidentally mentioned"; can be adjusted if Ch.2-5's actual data warrants it. The user may also add states with `count < 3` if domain knowledge says they have date-anchored references.) States already in `data/reigns/` (鲁, 周 from Phase 2) are skipped.

### Limitations

- A single-character state name like "陈" matches both the state and the verb "陈" (to display / state). The discovery script over-counts; the user filters during review. False positives are tolerable since they only add unneeded reign tables, never miss needed ones.
- "周" appears in many compound terms (周边, 周遭). Same over-count tolerance.

---

## 4. Reign-Extract Skill

### Skill location

`.claude/skills/changjuan-extract-reigns/SKILL.md`. Mirrors `changjuan-extract-v2`'s shape.

### Invocation

```
/changjuan-extract-reigns state:sta:jin
```

### Skill behavior

Uses the LLM's training knowledge of Eastern-Zhou chronology. The skill prompt instructs the model to:

1. Enumerate ALL rulers for the specified state during the Eastern-Zhou period (770-221 BCE), in chronological order.
2. For each ruler, emit a YAML record with fields specified in §5.
3. Cite sources (typically 史记 chapter name + 左传 cross-references). Citations are freeform strings — the spec does not constrain their format.
4. When uncertain about a specific date, mark the entry with `confidence: low` and explain in `notes`.
5. Do not invent rulers or compress reigns. If the state's chronology has gaps, leave them; the user can fill in during review.

The skill writes the YAML to `/tmp/changjuan-reigns-<state>.yaml` (a stable predictable path so the user can find the draft). The user reviews, edits if needed, then `git mv /tmp/changjuan-reigns-<state>.yaml data/reigns/<state>.yaml` (replacing `:` in the state id with `_` for filesystem safety, e.g. `sta:jin` → `sta_jin.yaml`) and commits.

### No DB writes

The skill never touches `corpus.sqlite` or `changjuan.sqlite`. Output is YAML on disk only. The user's review + commit is what activates the data.

---

## 5. Reign YAML Schema

```yaml
state_id: sta:jin
state_name: 晋
sources:
  - 《史记·晋世家》
  - 《左传》
rulers:
  - id: 晋武公
    posthumous_name: 武公
    given_name: 称
    reign_start_bce: 715
    reign_end_bce: 677
    sources:
      - 《史记·晋世家》
    confidence: high
    notes: |
      曲沃武公; 678 BCE 取代晋宗主. Reign here counts from 曲沃 takeover.
  - id: 晋献公
    posthumous_name: 献公
    given_name: 诡诸
    reign_start_bce: 676
    reign_end_bce: 651
    sources:
      - 《史记·晋世家》
      - 《左传·僖公九年》
    confidence: high
    notes: ""
```

### Field definitions

| Field | Required | Type | Meaning |
|---|---|---|---|
| `state_id` | yes | string | Canonical state id (e.g., `sta:jin`) |
| `state_name` | yes | string | Display name (e.g., `晋`) |
| `sources` | yes | list[string] | Top-level citations for the state's reign data |
| `rulers` | yes | list[object] | Chronological list of rulers |
| `rulers[].id` | yes | string | Preferred reference name (often the posthumous title prefixed with state) |
| `rulers[].posthumous_name` | optional | string | 谥号 (e.g., `文公`) |
| `rulers[].given_name` | optional | string | 本名 (e.g., `重耳`) |
| `rulers[].reign_start_bce` | yes | int | BCE year reign began (inclusive) |
| `rulers[].reign_end_bce` | yes | int | BCE year reign ended (inclusive) |
| `rulers[].sources` | optional | list[string] | Per-ruler citations |
| `rulers[].confidence` | optional | enum(`high`, `medium`, `low`) | Curator's confidence in the dates; default `high` |
| `rulers[].notes` | optional | string | Any caveats |

Multiple rulers may share a `posthumous_name` (e.g., 晋武公 of 曲沃 and a later 晋武公). The resolver matches `ruler_ref` against `id`, `posthumous_name`, AND `given_name`; if multiple rulers match, the resolver returns null + warning (per §6).

---

## 6. Date Parser: `explicit_reign_other` Resolution

### Existing state

`pipeline/dates.py` (Phase 2) handles `explicit_reign_lu` and `explicit_reign_zhou` against hard-coded reign tables for 鲁 and 周. The `explicit_reign_other` inference_kind is allowlisted in the schema but the resolver is a stub returning null.

### Phase 4 contract

```python
def resolve_explicit_reign_other(
    date_dict: dict,
    state_id: str,
    ruler_ref: str,
    reign_year: int,
) -> int | None:
    """Resolve a non-鲁/周 reign-anchored date to a BCE year.

    Input: a Date dict with `inference_kind == "explicit_reign_other"`,
    plus the extracted state_id (e.g. "sta:jin"), the ruler_ref string
    (e.g. "晋文公" or "重耳"), and the reign_year (1-indexed).

    Returns: absolute BCE year, or None on failure (with structured warning).
    """
```

### Resolution algorithm

1. Load `data/reigns/<state_id_slugified>.yaml` (e.g., `sta:jin` → `data/reigns/sta_jin.yaml`).
   - **Missing file** → log warning `reign_table_missing` with `state_id`; return None.
2. For each ruler in `rulers[]`, check if `ruler_ref` matches `id`, `posthumous_name`, OR `given_name`.
   - **Zero matches** → log warning `ruler_ref_not_found` with `state_id` + `ruler_ref`; return None.
   - **Multiple matches** → log warning `ruler_ref_ambiguous` with the matched ruler ids; return None.
   - **Exactly one match** → continue.
3. Compute `year_bce = reign_start_bce - (reign_year - 1)`. (Year 1 is the inception year; BCE years count backward.)
4. Bounds check: if `year_bce < reign_end_bce` (reign year exceeds reign length), log warning `reign_year_out_of_range` with the computed year; **return the year anyway**. Rationale: hiding the value loses information; downstream tools can flag the warning.
5. Return `year_bce`.

### Warnings surface

All four warning kinds go through `structlog`. The `dates_out_of_range` counter is incremented in `pipeline_runs.stats_json` for category 4. Categories 1-3 are logged but not counted (they produce null dates that show up in existing `unresolved` counts).

### Caching

YAML files are small (~5-50 rulers per state); the parser loads them on demand and caches in-process. No persistent cache; restarts re-read.

---

## 7. Smoke Checks + `phase4-prep.sh`

### Per-chapter smoke checks (Phase 4c step 11)

Run after each chapter's `load`:

| Check | Tool | Pass condition |
|---|---|---|
| Schema integrity | `PRAGMA integrity_check` | Returns "ok" |
| FK orphans | SQL counts on each canonical table joining to its expected parents | All counts = 0 |
| Stage 7 actually ran | `pipeline_runs` has a row for the chapter's `extract-load` stage | Yes |
| Persons populated | `SELECT COUNT(*) FROM persons WHERE pipeline_run_id = ?` | > 0 |
| Events with dates | `% of canonical events where date_json.year_bce IS NOT NULL` | ≥ 50% (heuristic — adjust per chapter if real value differs and is explained) |
| `dates_out_of_range` | `pipeline_runs.stats_json` counter | 0 (or documented exceptions) |

### `scripts/phase4-prep.sh` sections

1. **Phase 2 + Phase 3 still pass.** Both prior prep scripts green.
2. **Date parser tests pass.** `uv run pytest tests/unit/test_dates_reign_other.py`.
3. **Discovery script reproduces its worklist.** Re-running `scripts/discover-states.py` for Ch.2-5 emits a list; every state in the list has a `data/reigns/<state>.yaml`.
4. **All four new chapters loaded.** Five `pipeline_run` rows in stage `extract-load` for chapters 1-5 (Ch.1 from Phase 2, Ch.2-5 from Phase 4).
5. **No FK orphans, no dates_out_of_range across Ch.2-5.**
6. **Ch.1 golden still green.** `uv run changjuan golden-eval --chapter 1`.
7. **Spot-check QA.** `qa_samples` rows for all four new runs. `mismatch_rate` computed as `(no_count + 0.5 * partial_count) / total_count` over the union of `qa_samples` rows across the four new `pipeline_run_id`s. Bar: `≤ QA_MISMATCH_THRESHOLD` (0.10).
8. **PHASE4_DEFERRED backlog.** Print the deferral list (carries 6 items: chapters 6-108, LLM judge, curator UI, linker breadth, cross-chunk date automation, cross-canon at scale).

---

## 8. Knowledge Articles

### New

- **`concepts/pipeline/reign-extraction.md`** (~400-600 words) — what the skill produces, the YAML schema, the curator review pattern, the cross-validation expectation. Affects glob: `.claude/skills/changjuan-extract-reigns/**`, `data/reigns/**`.

### Updated

- **`concepts/data-model/dates-and-reigns.md`** — add `explicit_reign_other` resolution semantics (formerly stub). Reference `concepts/pipeline/reign-extraction.md`. Update `affects:` glob if needed.
- **`concepts/verification/testing.md`** — new section for the date parser tests + discovery script tests.
- **`concepts/runtime/cli.md`** — no new verbs in Phase 4 (skill, not CLI). But if a smoke-check helper script becomes a CLI verb, document.
- **`knowledge/log.md`** — entries per task per the same-task rule.

### CLAUDE.md mapping additions

```
| `data/reigns/**` or `.claude/skills/changjuan-extract-reigns/**` | `concepts/pipeline/reign-extraction.md` |
| `pipeline/**/date*.py` (extended) | `concepts/data-model/dates-and-reigns.md` |
```

The second row may already exist from Phase 1 — verify.

---

## 9. Definition of Done

### Code + data

- `pipeline/dates.py` resolves `explicit_reign_other` per §6.
- `scripts/discover-states.py` exists and runs.
- `.claude/skills/changjuan-extract-reigns/` exists.
- `data/reigns/` contains YAMLs for every state in the Ch.2-5 worklist (hand-verified).

### Validation

- Five `pipeline_run` rows in `extract-load` stage (chapters 1-5).
- Smoke checks pass for each new chapter.
- Spot-check `mismatch_rate ≤ 0.10`.
- Ch.1 golden P/R still green.

### Tests

- New unit tests for `explicit_reign_other` and discovery script.
- Updated `tests/integration/test_link_ch01.py` still passes (Phase 3 non-regression).
- All Phase 2 + Phase 3 tests still pass.

### Acceptance

- `scripts/phase4-prep.sh` runs green.
- `scripts/phase2-prep.sh` + `scripts/phase3-prep.sh` still green.
- Pre-commit hooks clean.
- `knowledge/log.md` has Phase 4 complete entry.

### PHASE4_DEFERRED (Phase 5+ backlog)

1. Chapters 6-108 (the remaining 103).
2. LLM judge for merge_candidates (still deferred).
3. Curator UI (Stage 8) — Streamlit; first queue: merge_candidates from Stage 5.
4. Linker for events / places / states / relations (Phase 3 was persons-only; Phase 4 used name-match safety net).
5. Cross-chunk relative-date automation (Phase 2's manual CLI still suffices).
6. Cross-canon checks at scale (Phase 2's opt-in `--with-canon-check` not exercised system-wide in Phase 4).

---

## 10. Anti-patterns to resist

- **Don't auto-commit the skill's output.** Hand verification is the load-bearing safety net for reign data. Skipping review here would propagate date errors across every event using that reign.
- **Don't iterate Phase 4 to "while we're at it" land linker breadth or the curator UI.** Both are real Phase 5+ work with their own design questions.
- **Don't bring 左传 / 史记 into the corpora just for reign data.** The skill uses training knowledge; the corpora are for the source text being processed, not reference material.
- **Don't lower the QA mismatch threshold to ship Phase 4.** If `mismatch_rate > 0.10`, iterate the extraction skill prompt; don't accept lower quality.
- **Don't skip the Ch.1 non-regression check.** Phase 4 must preserve Phase 2's quality bar on the chapter that has a golden.

---

*End of Phase 4 spec. Next step: writing-plans skill to produce the task-by-task implementation plan.*
