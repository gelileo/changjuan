# changjuan Phase 3 — Stage 5 (Link & Dedup) for Persons

**Date:** 2026-05-21
**Status:** Draft for review
**Scope:** Phase 3 of the changjuan tooling project: Stage 5 (the linker) for Person entities only, deterministic surface-feature matching, merge regression set, and stage-7 integration via a new `match_target_id` column. LLM judge, non-Person entities, Ch.40 golden, curator UI, date-parser expansion, and multi-chapter runs are all out of scope.

Layered on the founding spec at [`2026-05-20-changjuan-design.md`](2026-05-20-changjuan-design.md) (notably §3 — "highest-stakes stage", §6 — merge regression set, §7.1 — surface features + LLM-judge contract). Where they conflict, this spec governs Phase 3.

---

## 1. Scope & Success Criteria

### In scope (Phase 3)

- **Stage 5 (Link & dedup) for Person entities only** — deterministic surface-feature matching (variant overlap + state_id agreement + social_category agreement + clan_name agreement + temporal proximity). No LLM judgment.
- **`pipeline/stage5_link/` package** — pure-Python scorer + relevance-filtered candidate pool + orchestrator. Walks `candidate_persons` rows for a given `pipeline_run_id`; for each candidate, finds plausible match targets (canonical persons + other same-run candidates), computes a deterministic match score, and dispatches by threshold:
  - **Auto-merge** (score ≥ `LINKER_AUTO_MERGE_THRESHOLD`): writes a `match_target_id` hint on the candidate row + an `audit_log` entry tagged `actor='link@v1'`.
  - **Queue** (`LINKER_QUEUE_THRESHOLD` ≤ score < auto): writes a `merge_candidates` row with full `surface_features_json` for human triage.
  - **Skip** (score < `LINKER_QUEUE_THRESHOLD`): no action; candidate becomes a new canonical Person at load time.
- **`changjuan link <pipeline_run_id>` CLI verb** — thin wrapper around `link_run`. New workflow position: between `extract-load` and `load`.
- **Schema change** — adds `match_target_id TEXT` (nullable, no FK) to `candidate_persons`.
- **Stage 7 integration** — `pipeline/stage7_load/persons.py::load_candidate_persons` checks `match_target_id`: if set and target exists, merge into that canonical; if set and target missing, log warning + fall through to canonical_name match (existing safety net); if null, fall through unchanged.
- **Merge regression set** — `tests/golden/merge_regression.yaml` with ≥5 known same-person pairs + ≥5 known different-person pairs (canonical 重耳/晋文公 case, 公子重耳 across states, etc.). CI test enforces correct bucket dispatch on every run.
- **Thresholds in `pipeline/config.py`** — `LINKER_AUTO_MERGE_THRESHOLD = 0.75` and `LINKER_QUEUE_THRESHOLD = 0.40` initial values; comment block above the constants documents v1 calibration + recalibration policy.
- **Knowledge articles** — `concepts/pipeline/linking.md` (new); extensions to `knowledge-graph.md` (match_target_id field), `load-and-merge.md` (stage-7 integration), `runtime/cli.md` (link verb).
- **`scripts/phase3-prep.sh`** — Phase 3 acceptance checker; mirrors phase2-prep.sh's structure.

### Out of scope (deferred to Phase 4+)

- **LLM judge for ambiguous cases** (founding spec §7.1's "LLM judge for ambiguous cases" path). Deferred until the curator UI exists for "with judge" vs "without judge" comparison.
- **Linker for events / places / states / relations.** Persons is the hard case + highest impact. Other kinds keep their current stage-7 behavior (exact-name match).
- **Ch.~40 golden annotation.** Phase 3's regression set is the linker's validation surface, not a chapter golden.
- **`explicit_reign_other` date parsing + reign tables for 晋/齐/楚/秦/宋/郑/卫…** — Phase 4 work, required to extract chapters 2+.
- **Curator UI (Stage 8).** Until then, `merge_candidates` is triaged via SQL/CLI.
- **Cross-chunk relative-date automation.** Phase 2's manual CLI path suffices.
- **Multi-chapter extraction runs.** Phase 3 still operates on Ch.1's existing v2 candidates + any synthetic candidates the regression set seeds.

### Success criteria

1. `pipeline/stage5_link/__init__.py` exports `link_run` and `person_match_score`.
2. `changjuan link <pipeline_run_id>` runs without crashing against Ch.1's existing v2 candidate_persons.
3. The merge regression set (≥10 pairs total) loads; the linker reproduces every decision (≥5 same → auto-merge; ≥5 different → NOT-auto-merge). Any miss = test failure.
4. Integration test `test_link_ch01.py` (`@pytest.mark.golden`): running `link` then `load` on Ch.1's v2 candidates yields **exactly 13 canonical persons** (Ch.1 golden's count). No false-positive merges within a single chapter's candidates.
5. Stage 7's behavior with `match_target_id = NULL` is identical to its Phase 2 behavior (backwards compatible).
6. Phase 2 full acceptance still passes: 173 tests + 5 pre-commit hooks + phase2-prep.sh.
7. `phase3-prep.sh` reports green.
8. Living-docs: 1 new article + 3 updated + CLAUDE.md row addition; pre-commit drift-check clean.

---

## 2. Build Sequence

Eight steps, each one commit (or a small group). All work on `main`. Mirrors Phase 2's pattern.

### Step 1 — Schema addition

1. Add `match_target_id TEXT` (nullable, no FK, no default) to `candidate_persons` in `pipeline/schemas/canonical_schema.sql`.
2. Update `concepts/data-model/knowledge-graph.md` with the new field's role.

### Step 2 — Regression-set infrastructure

3. Create `tests/golden/merge_regression.yaml` skeleton (empty same/different lists with documented schema in a header comment).
4. Create `tests/golden/merge_regression_README.md` (or extend `tests/golden/ch01/README.md`) with conventions + sources cited.
5. Implement `tests/golden/regression_loader.py` — parses + validates the YAML, returns typed dicts.
6. Add unit test for the loader against a synthetic fixture.

### Step 3 — Regression set curation *(human task)*

7. Curator fills in ≥5 same-person + ≥5 different-person pairs. Each pair includes both persons' canonical_name, variants[], state_id, social_category, clan_name, optional dates, a rationale sentence, and a source citation.
8. Run `tests/golden/regression_loader.py` against the populated YAML to confirm structural validity.

### Step 4 — Person scoring formula

9. Implement `pipeline/stage5_link/scoring.py::person_match_score(a, b) -> dict` per Section 4 of this spec. Pure-function, fully unit-testable.
10. Unit tests against synthetic pairs covering: hard-veto (variant_overlap none), each positive contribution, each negative contribution, score clamping to [0, 1].
11. Initial threshold constants in `pipeline/config.py` (`LINKER_AUTO_MERGE_THRESHOLD = 0.75`, `LINKER_QUEUE_THRESHOLD = 0.40`).

### Step 5 — Candidate pool + linker orchestrator

12. Implement `pipeline/stage5_link/candidate_pool.py::candidate_pool(conn, candidate_id, pipeline_run_id) -> list[dict]` — variant-overlap pre-filter + state pre-filter + era pre-filter.
13. Implement `pipeline/stage5_link/linker.py::link_run(conn, pipeline_run_id) -> LinkStats`.
14. Unit tests against synthetic DB state covering: auto-merge writes match_target_id + audit_log; queue writes merge_candidates row with surface_features_json; skip leaves no trace; cross-run resolution via the chain.

### Step 6 — CLI verb + stage-7 integration

15. `changjuan link <pipeline_run_id>` CLI verb in `pipeline/cli.py` (thin shim).
16. Modify `pipeline/stage7_load/persons.py::load_candidate_persons` to honor `match_target_id`: if set and target canonical exists → merge into it; if set but target missing → log warning + fall through; if null → existing canonical_name-match logic unchanged.
17. Update `concepts/runtime/cli.md` (link verb) and `concepts/pipeline/load-and-merge.md` (match_target_id integration).
18. Integration test: synthetic candidates with match_target_id pre-set → stage 7 merges to the right canonical.

### Step 7 — Knowledge article + regression test

19. Create `concepts/pipeline/linking.md` per Section 5 of this spec.
20. Update CLAUDE.md's article-mapping table with `pipeline/stage5_link/**` → `concepts/pipeline/linking.md`.
21. Add `@pytest.mark.regression` test `tests/integration/test_link_regression.py` — loads regression set, runs scorer on each pair, asserts correct bucket dispatch.
22. Recalibrate thresholds in `pipeline/config.py` if any regression pair lands in the wrong bucket; document the recalibration in the config comment block.

### Step 8 — Phase 3 acceptance

23. Add integration test `tests/integration/test_link_ch01.py` (`@pytest.mark.golden`): running `link` then `load` on Ch.1's existing v2 candidates yields exactly 13 canonical persons.
24. Create `scripts/phase3-prep.sh` analogous to phase2-prep.sh. New sections cover: Stage 5 module + CLI present, regression set ≥10 pairs, regression test green, Ch.1 link-then-load preserves 13 persons, PHASE3_DEFERRED summary.
25. Run `scripts/phase2-prep.sh` and `scripts/phase3-prep.sh` together; both green.
26. Append "Phase 3 complete" log entry to `knowledge/log.md`.

### Parallelism notes for the plan stage

- Steps 1, 2 independent; can interleave.
- Step 3 (regression curation) is human; can run in parallel with Steps 1, 2, 4, 5 once a few example pairs are sketched.
- Step 4 depends on Step 2; blocks Step 5 orchestrator.
- Steps 6 and 7 independent; can interleave.
- Step 8 waits on everything.

---

## 3. Merge Regression Set + Validation Infrastructure

### File layout

```text
tests/golden/
├── merge_regression.yaml         # the curated pairs
├── merge_regression_README.md    # conventions, decisions log, sources cited
└── regression_loader.py          # parser + validator
```

### YAML schema

Two top-level lists: `same_person_pairs` and `different_person_pairs`. Each pair has `rationale`, `source`, `person_a`, `person_b`. Each person carries: `canonical_name`, optional `variants[]`, `state_id`, `social_category`, `clan_name`, optional `birth_date`/`death_date` (using the canonical Date dict shape).

```yaml
same_person_pairs:
  - rationale: 重耳 (公子) and 晋文公 are the same person across his exile and ruler phases
    source: 《史记·晋世家》/《左传·僖公二十三年》
    person_a:
      canonical_name: 重耳
      variants:
        - { variant: 公子重耳, kind: 别名 }
      state_id: sta:jin
      social_category: noble
      clan_name: 姬
      death_date: { year_bce: 628, uncertainty: point, inference_kind: explicit_reign_other }
    person_b:
      canonical_name: 晋文公
      variants:
        - { variant: 重耳, kind: 本名 }
        - { variant: 文公, kind: 谥号 }
      state_id: sta:jin
      social_category: royalty
      clan_name: 姬
      death_date: { year_bce: 628, uncertainty: point, inference_kind: explicit_reign_other }

different_person_pairs:
  - rationale: 公子重耳 of 晋 vs. unrelated 公子重耳 mentioned in 卫 chronicles
    source: hypothetical disambiguation case
    person_a:
      canonical_name: 重耳
      state_id: sta:jin
      social_category: noble
    person_b:
      canonical_name: 重耳
      state_id: sta:wei
      social_category: noble
```

### Curation targets (suggested 10 pairs)

**Same-person (5):**
1. **重耳 ↔ 晋文公** — canonical hard case; spec §6 names it explicitly.
2. **管仲 ↔ 管夷吾** — 字 vs 本名 variant matching.
3. **重耳 ↔ 公子重耳** — short-form fold across chapters.
4. **太子宜臼 ↔ 周平王** — pre-coronation vs post-coronation name.
5. **小白 ↔ 齐桓公** — 本名 vs 谥号.

**Different-person (5):**
1. **公子重耳 (晋) ↔ 公子重耳 (卫)** — same name, different states.
2. **召公奭 (西周) ↔ 召虎 (周宣王朝)** — same lineage, different historical figures with ~200-year gap.
3. **申侯 (西周) ↔ 申侯 (春秋)** — same title, different eras.
4. **太子宜臼 ↔ 太子伯服** — different sons of 周幽王.
5. **晋文公 ↔ 晋灵公** — different 晋 rulers, both 谥号, both 姬 clan.

### `regression_loader.py` contract

```python
def load_regression_set(
    path: Path = Path("tests/golden/merge_regression.yaml"),
) -> RegressionSet:
    """Load + validate the merge regression set. Raises GoldenLoadError on schema violations.

    Validates per pair:
      - both person_a and person_b present
      - both have non-empty canonical_name
      - if social_category set, value is in the canonical 11-value enum
      - if dates set, inference_kind is in the Phase 2 allowlist (Phase 3 may extend
        once explicit_reign_other lands)
    """
```

### Regression test (`tests/integration/test_link_regression.py`)

Two pytests, marked `@pytest.mark.regression`:

- `test_known_same_pairs_score_above_auto_merge_threshold`: for every pair in `same_person_pairs`, assert `person_match_score(a, b)["score"] >= LINKER_AUTO_MERGE_THRESHOLD`. Failure prints the offending pair's rationale + features.
- `test_known_different_pairs_score_below_auto_merge_threshold`: for every pair in `different_person_pairs`, assert score < auto threshold. Failure prints rationale + features.

Marker `@pytest.mark.regression` excludes from `pytest -q` default but is always run in `phase3-prep.sh`.

### Curation rationale

10 pairs is small enough to hand-curate in 1–2 hours, large enough to cover the failure modes the founding spec names. Specifically:
- The 重耳/晋文公 case (spec §6) — validates variant chains across life phases.
- 公子重耳 across states — validates state_id veto.
- 召公奭 / 召虎 (200y gap) — validates temporal_proximity penalty.
- 太子宜臼/太子伯服 — validates that "shared field structure" without name overlap doesn't trigger merge.
- 晋文公/晋灵公 — validates the hard-veto on no variant overlap.

When extraction expands beyond Ch.1 in Phase 4+, the regression set grows organically as real same/different pairs surface in production data.

---

## 4. Person Matcher: Scoring Formula + Thresholds

### Design philosophy

Per founding spec §3 + §6: auto-merge threshold "deliberately high"; merge_candidates queue is the "first curation surface"; false-positive merges compound across the graph, so the scorer skews toward requiring strong positive evidence + lets any single feature veto.

### Feature dimensions

All five dimensions are deterministic functions of the two candidate records' fields:

| Feature | Type | Computation |
|---|---|---|
| **variant_overlap** | `none` / `partial` / `strong` | Strong = either canonical_name is in the other's `variants[]` strings. Partial = any non-canonical variant string match. None = no shared string anywhere. |
| **state_agreement** | `same` / `one_null` / `different` | Compare `state_id`. `one_null` when only one side has it set. |
| **social_category_agreement** | `same` / `one_null` / `different` | Compare `social_category`. |
| **clan_agreement** | `same` / `one_null` / `different` | Compare `clan_name`. |
| **temporal_proximity** | `compatible` / `unknown` / `conflict` | Compatible = death_date_a within the other side's plausible lifespan, or both fall in same era. Conflict = death_date_a more than ~150 years before birth_date_b (or vice versa). Unknown = either side missing both dates. |

### Score formula

```python
# Positive contributions
+0.50 if variant_overlap == "strong"
+0.20 if variant_overlap == "partial"
+0.20 if state_agreement == "same"
+0.10 if clan_agreement == "same"
+0.10 if social_category_agreement == "same"
+0.10 if temporal_proximity == "compatible"

# Negative contributions
-0.40 if state_agreement == "different"
-0.30 if temporal_proximity == "conflict"
-0.20 if clan_agreement == "different"
-0.10 if social_category_agreement == "different"
```

**Hard veto**: if `variant_overlap == "none"`, score is `0.0` regardless of other features. The spec's rule: variant overlap is necessary for a merge to be considered.

Score clamps to `[0, 1]`.

### Initial thresholds

```python
LINKER_AUTO_MERGE_THRESHOLD: float = 0.75
LINKER_QUEUE_THRESHOLD:      float = 0.40
```

**Why 0.75:** strong variant (+0.50) + state agreement (+0.20) = 0.70, just under. Add any one secondary positive (clan / category / temporal, each +0.10) → 0.80, auto-merge. Means: strong variant + state + ≥1 secondary signal triggers auto-merge.

**Why 0.40:** partial variant (+0.20) + state agreement (+0.20) = 0.40 exactly at threshold. Means: partial variant + state agreement is the minimum to land in the queue (worth human review). Below that, evidence is too thin.

### Regression-set walkthroughs

All 10 suggested pairs hit the right bucket with the v1 formula:

| Pair | variant | state | clan | category | temporal | score | result |
|---|---|---|---|---|---|---|---|
| 重耳 ↔ 晋文公 | strong | same | same | different | compatible | +0.50+0.20+0.10−0.10+0.10 = **0.80** | ✅ auto |
| 管仲 ↔ 管夷吾 | strong | same | one_null | one_null | compatible | +0.50+0.20+0.10 = **0.80** | ✅ auto |
| 重耳 ↔ 公子重耳 | strong | same | same | same | compatible | **1.00** | ✅ auto |
| 太子宜臼 ↔ 周平王 | strong | same | same | same | compatible | **1.00** | ✅ auto |
| 小白 ↔ 齐桓公 | strong | same | same | same | compatible | **1.00** | ✅ auto |
| 公子重耳 (晋) ↔ (卫) | strong | different | same | same | compatible | +0.50−0.40+0.10+0.10+0.10 = **0.40** | ✅ queue |
| 召公奭 ↔ 召虎 | partial | same | one_null | one_null | conflict | +0.20+0.20−0.30 = **0.10** | ✅ skip |
| 申侯 西周 ↔ 春秋 | strong | same | one_null | one_null | conflict | +0.50+0.20−0.30 = **0.40** | ✅ queue |
| 太子宜臼 ↔ 太子伯服 | none | same | same | same | compatible | hard veto → **0.00** | ✅ skip |
| 晋文公 ↔ 晋灵公 | none | same | same | same | conflict | hard veto → **0.00** | ✅ skip |

All 5 sames score ≥ 0.75 (auto-merge); all 5 differents score < 0.75 (correctly NOT auto-merged — two land in the queue for human review, three get skipped via hard-veto or temporal-conflict penalty).

If a real-data pair lands in the wrong bucket post-curation, follow the calibration loop in §4's "Calibration loop" subsection — feature first, weight second, threshold last.

### `merge_candidates.surface_features_json` payload

Queued pairs write a full feature breakdown:

```json
{
  "variant_overlap": "strong",
  "state_agreement": "different",
  "clan_agreement": "same",
  "social_category_agreement": "same",
  "temporal_proximity": "compatible",
  "shared_variants": ["重耳"],
  "score_breakdown": {
    "variant_overlap_strong":         +0.50,
    "state_agreement_different":      -0.40,
    "clan_agreement_same":            +0.10,
    "social_category_agreement_same": +0.10,
    "temporal_proximity_compatible":  +0.10
  },
  "score": 0.40
}
```

The breakdown makes the queue actionable for human triage (and, later, for the LLM judge to consume) without re-running the scorer.

### Calibration loop

Weights + thresholds are best-guesses. Response order when a regression pair lands in the wrong bucket:
1. Add a missing feature dimension if there's a real signal the scorer ignores (e.g., person_relation overlap, place_id intersection via person_states).
2. Adjust a weight by a small delta (±0.05).
3. Move the threshold — last resort.

All adjustments get an entry in the config.py comment block (mirroring Phase 2's `GOLDEN_PR_THRESHOLDS` history convention).

---

## 5. `link` CLI Verb + Stage-7 Integration

### Module layout

```text
pipeline/
├── stage5_link/
│   ├── __init__.py             # re-exports link_run, person_match_score
│   ├── linker.py               # link_run(conn, pipeline_run_id) orchestrator
│   ├── scoring.py              # person_match_score(a, b) → {score, features}
│   └── candidate_pool.py       # candidate_pool(conn, candidate_id, pipeline_run_id)
├── cli.py                      # MODIFY: add link verb
└── stage7_load/persons.py      # MODIFY: honor match_target_id
```

### `candidate_pool.candidate_pool`

```python
def candidate_pool(
    conn: sqlite3.Connection,
    candidate_id: str,
    pipeline_run_id: str,
) -> list[dict]:
    """Find plausible match targets for a given candidate_persons row.

    Pre-filters by relevance (avoid O(N²) at corpus scale):
      - any canonical Person sharing at least one variant or canonical_name string
        (uses the trigram index on person_variants.variant + persons.canonical_name)
      - any other same-run candidate_persons sharing at least one variant or
        canonical_name string
      - state_id overlap (when both have it set; missing is permissive)
      - era overlap when both have date fields (loose: ±200 years)

    Returns list of dicts with: target_id, target_kind ('canonical' | 'candidate'),
      canonical_name, variants, state_id, social_category, clan_name, birth/death_date.
    """
```

### `linker.link_run`

```python
def link_run(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
) -> LinkStats:
    """For each candidate_persons row in the run, compute match scores against its
    candidate pool, dispatch by threshold.

      - score >= LINKER_AUTO_MERGE_THRESHOLD → write match_target_id on candidate row +
        audit_log entry with actor='link@v1' + score snapshot.
      - LINKER_QUEUE_THRESHOLD <= score < auto → write merge_candidates row with
        full surface_features_json; leave match_target_id null.
      - score < LINKER_QUEUE_THRESHOLD → no action.

    Per candidate, picks the SINGLE best-scoring target (not multi-match). If the
    best target is itself a same-run candidate not yet promoted to canonical, the
    chain resolves at load time via _resolve_canonical_for_candidate_id().

    Returns: {candidates_processed, auto_merges, queued, skipped}.
    """
```

### CLI verb

```python
@app.command()
def link(
    pipeline_run_id: str,
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Run Stage 5 (linker) for the given pipeline_run_id."""
    from pipeline.stage5_link import link_run

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    stats = link_run(canonical, pipeline_run_id)
    typer.echo(
        f"link {pipeline_run_id}: processed={stats['candidates_processed']} "
        f"auto-merged={stats['auto_merges']} queued={stats['queued']} "
        f"skipped={stats['skipped']}"
    )
```

Small wiring shim; all logic lives in the package.

### Post-Phase-3 user workflow

```bash
uv run changjuan extract --chapter 1                       # pre-flight (unchanged)
/changjuan-extract-v2 chapter:1                             # skill in Claude Code (unchanged)
# ... skill chains to extract-load, which writes candidate_* rows ...
uv run changjuan link <pipeline_run_id>                    # NEW — Stage 5
uv run changjuan load <pipeline_run_id>                    # honors match_target_id
uv run changjuan golden-eval --chapter 1                   # measure P/R (unchanged)
```

Pre-flight `extract` stays single-step (no link awareness). The skill does not auto-trigger `link` — running it is a deliberate user step. Keeps the audit trail clean.

### Stage-7 integration

`pipeline/stage7_load/persons.py::load_candidate_persons` change (5-line addition at the top of the per-candidate loop):

```python
# 1) Honor match_target_id if Stage 5 set it.
target_id = candidate_row["match_target_id"]
if target_id is not None:
    existing = conn.execute(
        "SELECT id FROM persons WHERE id = ?", (target_id,),
    ).fetchone()
    if existing is None:
        log.warning(...)
        target_id = None

# 2) Fall back to canonical_name match (existing Phase 2 safety net).
if target_id is None:
    existing = conn.execute(
        "SELECT id FROM persons WHERE canonical_name = ?", (canonical_name,),
    ).fetchone()

# 3) Create new if still no match; else merge (unchanged Phase 2 logic).
```

All other Phase 2 stage-7 behavior (variants accumulation, citation accumulation, conflict emission, curated-not-overwritten) is unchanged.

### Cross-run vs intra-run pairs

A subtle case: stage 5 may decide that two candidates *within the same run* should merge (the agent emitted both `重耳` and `公子重耳` as separate p1 and p7). The later candidate's `match_target_id` gets set to a same-run candidate id (e.g., `cand:per:<run_id>:p1`).

A new helper `_resolve_canonical_for_candidate_id(conn, cand_id) -> str | None` lives in `pipeline/stage7_load/persons.py` (alongside the existing private helpers). It walks the chain: when stage 7 processes p7 and sees `match_target_id = cand:per:<run_id>:p1`, the helper looks up which canonical id p1 became (already created earlier in the same load pass — `load_candidate_persons` writes a `{candidate_id → canonical_id}` mapping into a local dict as it processes each candidate), then returns that canonical id. The caller merges into it. If the chain resolves to no canonical (e.g., the chained candidate also got skipped), the function returns None and the caller falls back to canonical_name match.

### `concepts/pipeline/linking.md` (new article)

Sections to cover:
- What stage 5 does (deterministic surface-feature matching + threshold-based dispatch).
- Why deterministic-only in Phase 3 (LLM judge deferred until curator UI exists for comparison).
- Feature dimensions + scoring formula (link to §4 of this spec).
- Merge regression set + recalibration loop.
- `match_target_id`: how stage 7 honors it.
- `merge_candidates` queue: what the curator (eventually, UI) consumes.
- Cross-run vs intra-run pair handling.
- What would invalidate this article.

`affects:` globs: `pipeline/stage5_link/**`, `pipeline/cli.py` (`link` verb portion), `tests/golden/merge_regression.yaml`, `pipeline/stage7_load/persons.py` (`match_target_id` honor block).

---

## 6. Definition of Done + Phase 4 Backlog

### Acceptance checklist

Phase 3 is done when all of these are green:

**Code + schema**
- `candidate_persons.match_target_id` column (nullable, no FK, no default) added to `canonical_schema.sql`.
- `pipeline/stage5_link/` package shipped: `scoring.py`, `candidate_pool.py`, `linker.py`.
- `__init__.py` re-exports `link_run`, `person_match_score`.
- `pipeline/cli.py::link` verb.
- `pipeline/stage7_load/persons.py` honors `match_target_id` with fallback + warning.
- `pipeline/config.py` has `LINKER_AUTO_MERGE_THRESHOLD = 0.75` and `LINKER_QUEUE_THRESHOLD = 0.40`; comment block documents v1 calibration.

**Validation**
- `tests/golden/merge_regression.yaml` ≥5 same + ≥5 different pairs.
- `tests/golden/merge_regression_README.md` (or extended ch01 README) records conventions.
- `tests/golden/regression_loader.py` loads + validates.

**Tests**
- Unit: `person_match_score` covers hard-veto, every positive, every negative, clamping.
- Unit: `candidate_pool` covers variant/state/era pre-filters.
- Unit: `link_run` covers auto-merge / queue / skip dispatch + cross-run chain resolution.
- Unit: stage-7 modified loader covers match_target_id honored / null fallback / missing-target warning.
- Integration `@pytest.mark.regression`: same-pairs all auto-merge; different-pairs all don't.
- Integration `@pytest.mark.golden`: `link` then `load` on Ch.1's v2 candidates → exactly 13 canonical persons.
- Phase 2 full suite still green.

**Knowledge**
- New: `concepts/pipeline/linking.md`.
- Updated: `concepts/data-model/knowledge-graph.md` (match_target_id).
- Updated: `concepts/pipeline/load-and-merge.md` (stage-7 match_target_id integration).
- Updated: `concepts/runtime/cli.md` (link verb).
- Updated: `CLAUDE.md` article-mapping row for `pipeline/stage5_link/**`.

**CLI + workflow**
- `uv run changjuan link <run_id>` runs against Ch.1's v2 candidates without crashing.
- Output: summary line with processed / auto-merged / queued / skipped.
- `audit_log` entries appear with `actor='link@v1'` and score snapshot.
- `merge_candidates` rows have non-null `surface_features_json`.

**Acceptance**
- `scripts/phase3-prep.sh` created; runs green.
- `scripts/phase2-prep.sh` still runs green.
- All 5 pre-commit hooks clean.
- `./scripts/validate-articles` clean.
- `./scripts/drift-check` clean.
- `knowledge/log.md` has the "Phase 3 complete" entry.

### Phase 4 starter backlog (recorded as `PHASE3_DEFERRED`)

1. **LLM judge for Stage 5 ambiguous cases** — adds `.claude/skills/changjuan-link-judge/` consuming merge_candidates + emitting verdicts. Comparison study: with-judge vs without-judge merge_candidates quality.
2. **`explicit_reign_other` date parsing + reign tables for 晋/齐/楚/秦/宋/郑/卫…** — required to extract chapters 2+.
3. **Ch.~40 golden annotation (城濮之战)** — cross-chapter linker validation.
4. **Curator UI (Stage 8)** — Streamlit; first queue: merge_candidates from Stage 5; then conflicts; then low-confidence extractions.
5. **Cross-chunk relative-date automation** — only if patterns emerge that chunk-walkback can't catch.
6. **Linker for events / places / states / relations** — Phase 3 was persons-only. Events especially benefit from cross-chunk consolidation (PHASE2_DEFERRED #6's relation P/R gap).
7. **Multi-chapter extraction runs** — actually run extract→link→load on chapters 2-108. Prompt iteration against multi-chapter golden; conflict triage at scale.

### Anti-patterns to resist near Phase 3 close

- **Don't over-tune scorer weights to the regression set.** It's small; over-tuning overfits. Adjust only when a real same/different pair lands in the wrong bucket, not on intuition.
- **Don't introduce LLM judgment to "improve" borderline auto-merge.** Phase 3's whole point is validating the deterministic approach in isolation; the LLM-judge comparison is Phase 4 work.
- **Don't expand to events/places/states/relations in Phase 3.** Persons are the hard case + highest impact; other kinds work fine via stage 7's existing matching.
- **Don't promote `match_target_id` to a FK.** Keep as plain TEXT. Stage 5 may set it to a same-run candidate id that hasn't been promoted to canonical yet — FK would reject. Stage 7's fallback + chain resolution handles missing targets gracefully.

---

*End of Phase 3 spec. Next step: writing-plans skill to produce the task-by-task implementation plan.*
