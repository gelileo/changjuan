# changjuan Phase 6 — Curator Hardening (Reject-Memory + Walk-the-31 + person_relations Fix)

**Date:** 2026-05-23
**Status:** Draft for review
**Scope:** A three-track Phase 6 that hardens the Phase 5 curator into something usable for real curation work. Track A ships reject-memory so the linker stops re-flagging rejected pairs across reruns. Track B walks the existing 31 open `merge_candidates` rows end-to-end as a phase deliverable, fixing UI friction discovered during the walk under a strict ≤3-fix budget. Track C fixes the one-line field-name bug in `pipeline/stage3_extract.py:377` that has kept `person_relations` at 0 rows and backfills the table from cached extraction YAMLs.

Layered on:
- Founding spec `2026-05-20-changjuan-design.md` — §4 governs curator UI shape; §5 governs `audit_log` schema.
- Phase 3 spec `2026-05-21-phase3-linker-design.md` — produces the `merge_candidates` rows whose rejection we now persist.
- Phase 5 spec `2026-05-22-phase5-curator-ui-design.md` — §3 (merge algorithm) and §11 (PHASE5_DEFERRED) define what Phase 6 picks up.

Where they conflict, this spec governs Phase 6.

---

## 1. Scope & Success Criteria

### In scope (Phase 6)

**Track A — Reject-memory**
- New table `rejected_merges` keyed on `(canonical_id, candidate_fingerprint)`.
- Pure fingerprint helper `pipeline.stage5_link.fingerprint.candidate_fingerprint(row)` — SHA-1 of `name + sorted(set(variants))`, first 16 hex chars.
- `reject_merge` in `pipeline/stage5_link/merge.py` inserts a `rejected_merges` row inside the same transaction as the existing audit_log write.
- `pipeline/stage5_link/linker.py` filters out pairs whose `(canonical_id, fingerprint)` is in `rejected_merges` before emitting new `merge_candidates` rows.
- CLI flag `changjuan link --ignore-rejections` for the "I changed my mind" case. Default = honor rejections.

**Track B — Walk the 31**
- Curator (the user) walks all 31 open `merge_candidates` rows via the Phase 5 UI to a recorded decision in `audit_log`.
- `.bak` snapshot taken before the walk so the walk is reversible by file copy.
- Friction-fix budget: up to 3 UI fixes, each <100 LOC, no schema change. Anything larger is logged as a Phase 7 input, not built in Phase 6.
- Retrospective document `docs/superpowers/retros/2026-05-23-phase6-walk.md` captures ergonomic friction observed, rough time-per-decision, and recommended next moves.

**Track C — person_relations bug**
- Fix `pipeline/stage3_extract.py:377` to read `r.get("kind_detail", "")` instead of the non-existent `relation_kind`.
- Backfill `candidate_person_relations` and `person_relations` by re-running stages 3 → 5 → 7 against the cached `data/extractions/*.yaml` for chapters 1-5. No LLM calls.
- Stage 7 already silently skips kinds not in `_VALID_PERSON_RELATION_KINDS`, so the fix path is purely additive: rows previously dropped at stage 7 will now insert.

### Explicitly out of scope (deferred to Phase 7+)
- Conflicts queue UI (PHASE5_DEFERRED item 3).
- Low-confidence queue UI (item 4).
- Undo button (item 2) — mitigated by Track B's `.bak` snapshot.
- Re-extract button (item 5), search box (item 6), headline counters (item 7), per-chapter drill-in (item 8), prefetch ergonomics (item 9).
- Linker breadth to events / places / states / relations.
- LLM judge populating `llm_judgment_json`.
- `chapter_citation_context` ±N paragraph window.
- Atomicity tests for the accept/reject/split error branches (DoD item 4 gap from Phase 5).

### Success criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | `rejected_merges` table exists with correct schema | `sqlite3 data/changjuan.sqlite ".schema rejected_merges"` |
| 2 | Rejecting a candidate via UI writes one `rejected_merges` row in the same transaction as the `audit_log` row | Unit test on `reject_merge` |
| 3 | Re-running the linker after a rejection does not re-flag the same pair | Integration test: link → reject one pair → link again → assert pair absent from new merge_candidates |
| 4 | `changjuan link --ignore-rejections` re-flags previously rejected pairs | Integration test asserting the flag bypasses the filter |
| 5 | Fingerprint is stable across variant-order and duplicate-variant changes | Unit tests on `candidate_fingerprint` |
| 6 | All 31 open `merge_candidates` rows are resolved (accept / edit-accept / reject / split). No defers remain at end of walk. | `SELECT COUNT(*) FROM merge_candidates WHERE status = 'open'` returns 0 |
| 7 | `person_relations` count > 0 after Track C backfill | `SELECT COUNT(*) FROM person_relations` |
| 8 | `pytest -q` passes; all four phase-prep scripts pass; new `scripts/phase6-prep.sh` passes | Standard verification gate |

### Definition of Done (Phase 6)

1. All eight success criteria above met.
2. Knowledge articles updated per the article-mapping table — at minimum `concepts/pipeline/linking.md`, `concepts/data-model/knowledge-graph.md`, `concepts/runtime/configuration.md`, `concepts/pipeline/extraction.md`, `concepts/curation/streamlit-app.md`, and `concepts/pipeline/load-and-merge.md`. `knowledge/log.md` has a Phase 6 entry.
3. `scripts/phase6-prep.sh` exists and is green; older phase-prep scripts still green.
4. Walk retrospective `docs/superpowers/retros/2026-05-23-phase6-walk.md` written and committed.
5. Commits follow the living-docs same-task rule and pre-commit hooks pass.

---

## 2. Architecture

### 2.1 Module map

```
pipeline/
├── stage3_extract.py                  # one-line fix at :377 (Track C)
├── stage5_link/
│   ├── fingerprint.py                 # NEW — pure fingerprint helper (Track A)
│   ├── linker.py                      # filter against rejected_merges (Track A)
│   └── merge.py                       # reject_merge writes rejected_merges row (Track A)
├── schemas/
│   └── canonical_schema.sql           # NEW table rejected_merges (Track A)
└── cli.py                             # NEW --ignore-rejections flag on link verb (Track A)

curation/
└── pages/1_Merge_candidates.py        # ≤3 friction fixes from the walk (Track B)

scripts/
└── phase6-prep.sh                     # NEW — Phase 6 acceptance check

tests/
├── unit/
│   ├── test_fingerprint.py            # NEW (Track A)
│   └── test_reject_memory.py          # NEW (Track A)
└── integration/
    ├── test_link_rejection_loop.py    # NEW (Track A)
    └── test_person_relations_backfill.py  # NEW (Track C)

docs/superpowers/retros/
└── 2026-05-23-phase6-walk.md          # NEW (Track B)
```

### 2.2 Track ordering and dependencies

- **A before B.** Without reject-memory, every rejection in the walk would be lost on the next linker run.
- **C independent.** Can run in parallel with A or B in a separate subagent task.
- **Walk-the-31 (B) happens last** so any UI friction fixes discovered ride on top of A's already-merged changes.

### 2.3 Boundaries preserved

- Read-only `mode=ro` connections in `curation.db` remain unchanged. Writes still route exclusively through `pipeline.stage5_link.merge`.
- `audit_log` is the source of truth for "what the curator did"; `rejected_merges` is a derived index used only by the linker to avoid re-flagging.
- The fingerprint is computed from candidate-side data only — no canonical-side dependency — so it's stable across canonical merges that happen later.

---

## 3. Track A — Reject-memory

### 3.1 Schema

Add to `pipeline/schemas/canonical_schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS rejected_merges (
    canonical_id          TEXT NOT NULL REFERENCES persons(id),
    candidate_fingerprint TEXT NOT NULL,
    rejected_at           TEXT NOT NULL,        -- ISO-8601 UTC
    audit_log_id          INTEGER REFERENCES audit_log(id),
    PRIMARY KEY (canonical_id, candidate_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_rejected_merges_fingerprint
    ON rejected_merges (candidate_fingerprint);
```

The live DB at `data/changjuan.sqlite` was created before this table existed. Phase 6 mirrors Phase 5's pattern: the integration test runs an in-test migration that calls `apply_schema()` (idempotent — `CREATE TABLE IF NOT EXISTS`). A one-shot migration CLI verb is not in scope; `apply_schema()` re-run on the live DB picks up the new table.

### 3.2 Fingerprint

`pipeline/stage5_link/fingerprint.py`:

```python
import hashlib
import json

def candidate_fingerprint(name: str, variants: list[str]) -> str:
    """Stable identity hash for a candidate person across re-extractions.

    Order-insensitive and dedup-insensitive over variants. Name is taken
    verbatim (no normalization) since the linker already operates on
    normalized surface forms upstream.
    """
    normalized = sorted(set(variants))
    payload = json.dumps({"name": name, "variants": normalized}, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
```

Trade-offs:
- **Why SHA-1, 16 hex chars (64 bits):** collision-resistant enough for a single-user local KB; short enough to read in logs.
- **Why no normalization on `name`:** the extractor (stage 3) is deterministic on a cached YAML, so the same `candidate_persons.name` reappears across re-extracts. Re-normalizing inside the fingerprint helper would risk divergence if normalization rules ever change.
- **Why sorted(set(variants)):** re-extraction may emit variants in a different order or include the canonical surface twice; the fingerprint should ignore both.
- **Known limitation:** if a future re-extraction discovers a *new* variant (genuine new evidence), the fingerprint shifts and the rejection won't catch. This is arguably correct behavior — new evidence deserves a fresh look — but it should be called out in the linking article so the curator can recognize the pattern.

### 3.3 Write path

`reject_merge` already exists in `pipeline/stage5_link/merge.py`. Phase 6 extends it:

1. Locate candidate A. Phase 5.1 established A can be in either `candidate_persons` (typical) or `persons` (escape-hatch case). Reuse the same table-detection branch already in `accept_merge`. Load name and variants from whichever side A lives in:
   - `candidate_persons`: name from column, variants from `variants_json` (parsed).
   - `persons`: name from column, variants from `person_variants` table (collected list).
2. Compute fingerprint over `(name, variants)` via `candidate_fingerprint`.
3. Resolve canonical_id. Canonical B is always in `persons`; its id is `canonical_id`. In the rare A-in-`persons` case, treat A's id as the canonical_id (the rejected pair is "don't merge B into A").
4. Inside the existing `with conn:` transaction, insert into `audit_log` first, then `rejected_merges` with `audit_log_id` referencing it.
5. Use `INSERT OR IGNORE` on `rejected_merges` so the operation is idempotent against duplicate rejections of the same pair.

### 3.4 Read path

`pipeline/stage5_link/linker.py` builds the rejection filter once per run:

```python
def _load_rejected_fingerprints(conn) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT canonical_id, candidate_fingerprint FROM rejected_merges"
    ).fetchall()
    return {(r[0], r[1]) for r in rows}
```

Each candidate pair the linker would emit is checked against this set. The check happens after canonical-side resolution (so `canonical_id` is known) and before the `INSERT INTO merge_candidates`. Skipped pairs are counted into a `linker_stats.rejected_filter_skipped` counter for visibility.

### 3.5 CLI flag

`changjuan link --ignore-rejections`:
- Default: filter is applied.
- With flag: `_load_rejected_fingerprints` returns an empty set; all previously rejected pairs are re-emitted.
- Stage 5 linker stats add a one-line note when the flag is set.

### 3.6 Error handling

| Failure | Behavior |
|---|---|
| `candidate_persons` row missing at reject time | Raise; `with conn:` rolls back. Audit log is *not* written. Curator-visible error message via existing Streamlit error handling. |
| `audit_log` insert fails | Existing rollback path (Phase 5). `rejected_merges` row also not written, since the insert is inside the same `with conn:`. |
| Fingerprint collision between two genuinely different candidates | 64-bit space; vanishingly unlikely at this scale. Detected at insert time by `INSERT OR IGNORE` (second row silently dropped); both rejections still recorded in `audit_log`. Acceptable. |

### 3.7 Tests

- `tests/unit/test_fingerprint.py`:
  - Same inputs → same fingerprint (determinism).
  - Variant order does not affect fingerprint.
  - Duplicate variants do not affect fingerprint.
  - Adding a new variant changes the fingerprint.
  - Changing the name changes the fingerprint.
- `tests/unit/test_reject_memory.py`:
  - `reject_merge` writes one `rejected_merges` row and one `audit_log` row in a single transaction.
  - Second rejection of the same `(canonical_id, fingerprint)` is idempotent (no error, still one row).
  - Rollback path: if `audit_log` insert fails, `rejected_merges` row is not present.
- `tests/integration/test_link_rejection_loop.py`:
  - Apply schema → seed candidates → link → reject one candidate → link again → assert the rejected pair is absent.
  - Run with `--ignore-rejections` → assert the pair reappears.

---

## 4. Track B — Walk the 31

### 4.1 Pre-flight

```bash
cp data/changjuan.sqlite data/changjuan.sqlite.phase6-walk-bak
```

Filename includes the phase tag so it's discoverable later. The `.bak` is the rollback mechanism for Phase 6 in lieu of an undo button. Restoration is `cp` in the other direction.

### 4.2 Workflow

The curator (user) opens the UI:

```bash
uv run changjuan curator
```

Navigates to "🔗 Merge candidates" and disposes of each candidate via the existing five-action shell (`a`/`e`/`r`/`d`/`s`). Defer (`d`) is permitted *during* the walk as a "come back to this" marker, but the walk does not complete until every candidate has a persisted disposition — accept, edit-accept, reject, or split. The Phase 5 implementation of `defer_merge` is a no-op (cursor advance only), so any candidate left in defer state remains `status = 'open'` and blocks DoD.

### 4.3 Friction-fix budget

A friction fix qualifies if:
- It is <100 LOC of new or changed code (including tests).
- It does not change the schema.
- It does not change `merge.py`'s public API.

The budget is 3 fixes total across the walk. The 4th-or-larger friction item is logged in the retrospective and becomes Phase 7 input.

Examples of qualifying fixes (illustrative — actuals depend on what the walk surfaces):
- Reorder displayed fields so the most-discriminating field appears first.
- Add a "previous decision" hint when the same name appeared in an earlier candidate.
- Surface the `surface_features` string when it's currently hidden behind a click.

Examples of non-qualifying items (would defer to Phase 7):
- Implementing the ±N paragraph context window.
- Adding a real undo button (audit_log replay).
- Implementing the conflicts queue.

### 4.4 Retrospective

`docs/superpowers/retros/2026-05-23-phase6-walk.md` is written after the walk completes. Sections:
1. **Summary:** counts by disposition; total elapsed time; rough seconds-per-candidate.
2. **What worked:** UI elements that did their job.
3. **Friction observed:** ranked list. For each item: what happened, why it slowed the walk, whether it was fixed in-budget or deferred.
4. **Recommended next moves:** the ranked list informs Phase 7 scope.

### 4.5 Tests

No automated tests for the walk itself — it's curator work. Friction fixes ship with whatever tests their change demands per Phase 5's testing conventions. The Phase 5 integration smoke test (`tests/integration/test_curator_smoke.py`) continues to cover the action-handler atomicity contract.

---

## 5. Track C — person_relations fix

### 5.1 Root cause

`pipeline/stage3_extract.py:377`:

```python
r.get("relation_kind", ""),     # bug: YAML field is `kind_detail`
```

The extractor emits `kind_detail: parent | ally | mentor | spouse | killed_by | …` (matching the canonical CHECK constraint vocabulary). The loader reads a non-existent `relation_kind`, falls back to `""`, and writes `""` into `candidate_person_relations.kind`. Stage 7 (`pipeline/stage7_load/relations.py:361`) silently skips rows whose `kind` is not in `_VALID_PERSON_RELATION_KINDS`. Net: 0 rows in `person_relations`.

### 5.2 Fix

Single line change:

```python
r.get("kind_detail", ""),
```

### 5.3 Backfill

Re-run stages 3 → 5 → 7 for chapters 1-5 against the cached `data/extractions/*.yaml`:

```bash
uv run changjuan extract --chapters 1..5 --use-cache
uv run changjuan link
uv run changjuan load --chapters 1..5
```

No LLM calls — the extract command re-reads cached YAMLs. Expected outcome: `candidate_person_relations.kind` rows now carry real values; stage 7 promotes them; `person_relations` count goes positive.

### 5.4 Side effects accepted

Stage 7 has contradiction detection for directional kinds (`parent`, `child`, `killed_by`, `ruler`, `minister`, `mentor`). With person_relations populated for the first time, contradictions previously invisible may now emit rows into the `conflicts` table. This is correct behavior — Phase 7's conflicts queue will surface them. Phase 6 logs the new conflicts count but does not act on them.

### 5.5 Tests

- `tests/integration/test_person_relations_backfill.py`:
  - Load a fixture extraction YAML known to contain `kind_detail` entries.
  - Run stages 3, 5, 7.
  - Assert `person_relations` count > 0 with the expected kinds.
  - Assert no rows have empty `kind`.
- Existing tests that previously asserted `person_relations` count = 0 (if any) are updated. Audit by `grep -rn "person_relations" tests/` during implementation.

### 5.6 Documentation

- `knowledge/concepts/pipeline/extraction.md` — note the field name `kind_detail` and the historical bug.
- `knowledge/concepts/pipeline/load-and-merge.md` — note that `person_relations` now populates; conflicts table may grow.

---

## 6. Cross-track concerns

### 6.1 audit_log change_kind values

No new values introduced in Phase 6. Existing `merge_rejected` covers Track A's reject path. The `rejected_merges` row is a derived index, not a new audit kind.

### 6.2 Living-docs same-task rule

| Track | Files touched | Articles required |
|---|---|---|
| A | `pipeline/stage5_link/**`, `pipeline/schemas/canonical_schema.sql`, `pipeline/cli.py` | `concepts/pipeline/linking.md` + `concepts/data-model/knowledge-graph.md` + `concepts/runtime/configuration.md` + `concepts/runtime/cli.md` |
| B | `curation/pages/1_Merge_candidates.py` (if friction fix) | `concepts/curation/streamlit-app.md` |
| C | `pipeline/stage3_extract.py`, `tests/integration/test_person_relations_backfill.py` | `concepts/pipeline/extraction.md` + `concepts/pipeline/load-and-merge.md` + `concepts/verification/testing.md` |

The Phase 5 lesson — `pipeline/stage5_link/**` touches three articles — applies to Track A. Don't waste minutes debugging drift-check failure; just touch the three.

### 6.3 phase6-prep.sh

Mirrors `phase5-prep.sh`:
1. `pytest -q` green (≥ 265 + new tests).
2. Schema includes `rejected_merges` table.
3. Old phase-prep scripts still green.
4. `merge_candidates` open-count = 0 (Track B success criterion).
5. `person_relations` count > 0 (Track C success criterion).
6. Walk retro file exists.
7. Drift check green.

### 6.4 Phase 5.1 lesson preserved

Track A's `reject_merge` operates on Phase 5.1's two-table candidate-A reality. The fingerprint helper is table-agnostic — it takes `(name, variants)`. `reject_merge` itself mirrors `accept_merge`'s table-detection branch (§3.3 step 1) and loads variants from whichever side A lives in. Don't re-litigate the candidate_persons design.

---

## 7. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fingerprint shifts on benign re-extraction (new variant discovered) | Medium | Low — one re-flag, curator decides again | Document the behavior; treat re-flag as feature, not bug. |
| Walk surfaces a friction item that exceeds the ≤3 budget | Medium | Medium — pressure to expand scope | Hard cap. 4th item ships in Phase 7. |
| Live DB schema migration (adding `rejected_merges` table) fails | Low | High — Phase 6 wedged | `apply_schema()` is `CREATE TABLE IF NOT EXISTS`; safe to re-run. Smoke test runs it before assertions. |
| Track C backfill exposes many contradictions, flooding `conflicts` | Medium | Low — informational only | Phase 7 owns the conflicts queue; Phase 6 just notes the count. |
| User aborts the walk mid-way (e.g., session ends) | Low | Low — `audit_log` records each decision atomically | Resume next session; `merge_candidates.status` shows progress. |
| `.bak` snapshot grows out of date during a long walk | Low | Low | Take snapshot immediately before the walk starts; document that mid-walk rollback loses any walk progress (acceptable). |

---

## 8. Open questions

None at spec time. The implementation plan should re-check during writing-plans.

---

## 9. Out of scope (Phase 7+ candidates)

Reproduced from PHASE5_DEFERRED for traceability:
- Undo button (audit_log replay).
- Conflicts queue (12 open today; possibly more after Track C).
- Low-confidence extractions queue.
- Re-extract button (per-chapter).
- Search box (design + implementation).
- Headline counter widgets.
- Coverage grid per-chapter detail view.
- Prefetch ergonomics (<200ms target).
- `chapter_citation_context` ±N paragraph window.
- Atomicity tests for accept/reject/split error branches.
- LLM judge for ambiguous merges.
- Linker breadth: events / places / states / relations.

Any item Track B surfaces and the budget can't absorb is logged into the walk retrospective and ranked here.
