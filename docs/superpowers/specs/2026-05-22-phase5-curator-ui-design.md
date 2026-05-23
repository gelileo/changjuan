# changjuan Phase 5 — Curator UI v1 (Merge-Candidates Triage)

**Date:** 2026-05-22
**Status:** Draft for review
**Scope:** Build the first slice of the Stage-8 curator surface defined in the founding spec §4: a Streamlit app with a spec-faithful home screen (108-cell coverage grid + queue panel + search), the uniform 40/40/20 review shell, and the merge-candidates queue implemented end-to-end. The other two queues (conflicts, low-confidence) ship as stub pages so the sidebar has its final shape, but only merge candidates is functional. Decision logic lives in a new `pipeline.stage5_link.merge` module so reversibility and the future LLM judge plug in cleanly later.

Layered on:
- Founding spec `2026-05-20-changjuan-design.md` — §4 (curator UI) governs the UI shape; §5 governs the audit_log schema; §7.5 governs the coverage grid.
- Phase 2 spec `2026-05-20-phase2-extraction-design.md` — confidence + low-confidence threshold.
- Phase 3 spec `2026-05-21-phase3-linker-design.md` — produces the `merge_candidates` rows this UI consumes.
- Phase 4 spec `2026-05-22-phase4-multichapter-design.md` — `stage7_load/id_maps.py` is the pattern for FK retargeting reused in `stage5_link/merge.py`.

Where they conflict, this spec governs Phase 5.

---

## 1. Scope & Success Criteria

### In scope (Phase 5)

- **Streamlit curation app** at `curation/app.py`, launched via `streamlit run curation/app.py` (already the canonical command in `CLAUDE.md`).
- **Home screen**: 108-cell coverage grid (5 green, 103 gray today) + queue panel with three entries (merge-candidates active; conflicts and low-confidence as disabled rows showing "Phase 6") + search input rendered disabled with a "Phase 6" tooltip.
- **Merge-candidates review screen**: 40/40/20 shell. Left column = source evidence (verbatim quote + ±2 paragraph toggle). Center column = side-by-side candidate-vs-canonical with field-level diff coloring + surface_features line + `llm_judgment_json` block when non-null. Right column = action panel with five buttons (`a` accept · `e` edit & accept · `r` reject · `d` defer · `s` split) + curator-note textarea + keyboard hints. Keyboard shortcuts via `streamlit-shortcuts`.
- **Decision actions** as pure functions in `pipeline/stage5_link/merge.py`:
  - `accept_merge(conn, mc_id, *, edits=None)` — fuses candidate into canonical (survivor = canonical), folds variants, retargets FKs across the 5 person-FK columns (see §3), resolves PK collisions per §3 rules, writes audit_log, flips `merge_candidates.status` to `'merged'`.
  - `reject_merge(conn, mc_id, *, note=None)` — flips status to `'rejected'` with curator_note, writes audit_log.
  - `defer_merge(conn, mc_id)` — no DB change; cursor advances in-memory only.
  - `split_person(conn, person_id, *, variants_to_extract, note=None)` — manual escape hatch for undoing prior bad merges; minimal UX (text input listing variants), full audit_log write.
- **Read helpers** in `curation/db.py` (read-only sqlite connection): `open_merge_candidates`, `coverage_stats`, `chapter_citation_context`, `low_confidence_count`.
- **Acceptance check** `scripts/phase5-prep.sh` modeled after `phase4-prep.sh`.
- **Knowledge article**: new `knowledge/concepts/curation/streamlit-app.md` per the CLAUDE.md article-mapping table.
- **CLI convenience**: `changjuan curator` subcommand in `pipeline/cli.py` that execs `streamlit run curation/app.py`.

### Out of scope (deferred to Phase 6+)

- **Reject-memory.** When the curator rejects a pair, the next linker run today could re-flag it. A `(canonical_id, candidate_variant_fingerprint)` lookup table is Phase 6 work. Phase 5's acceptance bar is "UI ready," not "linker rerun produces no duplicate flags."
- **Undo button.** The `audit_log` row carries enough state to roll back a merged or rejected decision, but exposing it through the UI (which row to target? linear rollback or selective?) is its own design problem.
- **Conflicts queue + low-confidence queue.** Stub pages only. Phase 6.
- **Re-extract button** on chapter views. §4 mentions it but it touches stage 3 and is its own subsystem.
- **`person_relations` empty-`kind` extractor bug.** Lives in stage 3 / extract-v2 prompts, not the curator surface. Phase 6 cleanup track.
- **LLM judge** for ambiguous merge pairs (HANDOFF item 2). The UI renders `llm_judgment_json` when non-null; populating that column is a later phase.
- **Prefetch ergonomics.** §4 targets <200ms per record via prefetch + custom JS. Phase 5's acceptance bar is "UI ready," not "ergonomics tuned." YAGNI for a 31-row queue.
- **Headline counter widgets** on the home screen — explicitly deferred by the founding spec §4 until "a week of curation surfaces which numbers actually get glanced at."
- **Optimistic-concurrency tokens.** Single-curator project.

### Success criteria

Phase 5 is done when **all** of the following hold (mirrors the Phase 4 "11 pass / 0 fail" pattern):

1. `streamlit run curation/app.py` boots, renders the home screen, and the coverage grid shows 5/108 chapters extracted.
2. Clicking through to the merge-candidates page loads all 31 open candidates (sorted oldest-first) and renders the shell for the first row.
3. The five action handlers (`accept_merge`, `reject_merge`, `defer_merge`, `split_person`, plus the `edits` variant of accept) each pass unit tests on a fixture DB, with the atomicity guarantee verified (failed transaction → zero DB state change).
4. `tests/integration/test_curator_smoke.py` executes every action at least once against a copy of the live DB and finishes with `merge_candidates` all resolved, no orphan FKs across the 5 person-FK columns retargeted by `accept_merge`, and `audit_log` row count equal to decisions made + collisions resolved.
5. All 5 pre-commit hooks pass (drift-check, ruff, ruff-format, mypy strict, regen-extraction-schema).
6. Full pytest suite green (`uv run pytest -q`).
7. `scripts/phase5-prep.sh` reports all green.
8. The article `knowledge/concepts/curation/streamlit-app.md` exists and matches what was shipped (drift-check enforces this).

Note: Phase 5 does **not** require the curator to actually work through all 31 candidates. That happens after the phase closes; the bar here is "the surface works."

---

## 2. Architecture / Module Layout

```
changjuan/
├── pipeline/
│   ├── stage5_link/
│   │   └── merge.py            NEW — accept_merge, reject_merge, defer_merge,
│   │                            split_person. Pure functions on a sqlite Connection,
│   │                            single transaction each, audit_log atomic with
│   │                            the data change.
│   └── cli.py                  SMALL EDIT — `changjuan curator` subcommand.
│
├── curation/                   NEW package (path reserved in CLAUDE.md).
│   ├── __init__.py
│   ├── app.py                  Streamlit entry — home screen.
│   ├── pages/
│   │   ├── 1_Merge_candidates.py   Review screen.
│   │   ├── 2_Conflicts.py          Stub: "Phase 6 — not implemented".
│   │   └── 3_Low_confidence.py     Stub: "Phase 6 — not implemented".
│   ├── components/
│   │   ├── shell.py            40/40/20 layout primitive.
│   │   ├── coverage_grid.py    108-cell grid component.
│   │   └── records.py          Side-by-side candidate-vs-canonical renderer w/ diff.
│   └── db.py                   Read helpers; opens read-only connection per request.
│
├── tests/
│   ├── unit/
│   │   ├── test_stage5_merge.py    NEW — accept/reject/defer/split branches +
│   │   │                            atomicity verification (DB snapshot before/after).
│   │   └── test_curation_db.py     NEW — read helpers.
│   └── integration/
│       └── test_curator_smoke.py   NEW — end-to-end exercise against fixture copy
│                                    of live DB.
│
├── scripts/
│   ├── curator-smoke               NEW — runs the integration test; called by
│   │                                phase5-prep.sh.
│   └── phase5-prep.sh              NEW — acceptance check (sections in §7).
│
└── knowledge/concepts/curation/
    └── streamlit-app.md            NEW article — UI shape, queue ergonomics, action
                                     semantics, audit_log contract. Affects glob:
                                     `curation/**/*.py`.
```

**Key boundaries:**

- **Decision logic lives in `pipeline.stage5_link.merge`**, not in Streamlit. Merge is conceptually a stage-5 operation; the UI only triggers it. Reversibility (Phase 6's undo) and the future LLM judge both compose into this module without touching Streamlit.
- **`curation/`** is view + read-only DB access only. Every write goes through a `pipeline.stage5_link.merge` function.
- **No new schema.** Existing columns suffice: `merge_candidates.status` (`open` / `merged` / `rejected`), `merge_candidates.resolved_at`, `audit_log` per founding spec §5.
- **Stub pages** materialize the two future queues so Streamlit's auto-sidebar lists them in their final order. Clicking renders a "Phase 6" notice.

---

## 3. Components

### `curation/app.py` (home screen)

- Reads coverage stats via `curation.db.coverage_stats() -> list[ChapterStatus]` (108 rows: chapter_num, title, extracted boolean, latest_run_id when extracted).
- Reads queue counts: `open_merge_candidates_count`, `open_conflicts_count` (Phase 6 queue, displayed only), `low_confidence_count()` (derived from `candidate_facts.confidence < threshold`; threshold lives in `pipeline.config`).
- Renders: `coverage_grid` component + queue panel with three rows.
- Search box rendered disabled with a "Phase 6" tooltip.

### `curation/pages/1_Merge_candidates.py` (review screen)

- Reads the open queue via `curation.db.open_merge_candidates(limit=None) -> list[MergeCandidateRow]`. Sorted by `created_at ASC` (oldest first) for stable iteration.
- Cursor lives in `st.session_state["mc_cursor"]` (integer index into the in-memory snapshot, refetched only on explicit reload).
- Renders the shell with the current candidate.
- Click handlers call `pipeline.stage5_link.merge.*` then advance the cursor.
- Keyboard bindings via `streamlit-shortcuts`: `a` accept, `e` edit-and-accept (focuses center column), `r` reject, `d` defer, `s` split, `j` next, `k` prev, `Enter` confirms focused action.

### `curation/components/shell.py`

- Pure function `render_shell(left, center, right)` using `st.columns([40, 40, 20])`. No state.

### `curation/components/coverage_grid.py`

- `render_coverage_grid(stats: list[ChapterStatus])` — emits a 9×12 CSS grid via `st.markdown(..., unsafe_allow_html=True)`. Each cell links to a per-chapter view (Phase 6); for Phase 5 cells are non-interactive. Green = extracted; gray = not yet. Tooltip on hover: chapter title + latest run_id when applicable.

### `curation/components/records.py`

- `render_pair(candidate, canonical, *, edit_mode=False) -> dict[str, Edit] | None` — emits the side-by-side panel. For each field on `persons` + the variants list, computes a diff badge (`same` / `one_null` / `disagree`) and renders accordingly. When `edit_mode=True`, fields become `st.text_input` and the function returns the edits dict; otherwise read-only and returns `None`.
- Also renders the surface_features line and the `llm_judgment_json` block when non-null.

### `pipeline/stage5_link/merge.py`

Public functions:

```python
def accept_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    edits: dict[str, Any] | None = None,
) -> MergeResult:
    """Fuse candidate (A) into canonical (B). Survivor = canonical.

    Within a single transaction (BEGIN ... COMMIT, ROLLBACK on any error):
      1. Load the merge_candidates row; verify status='open'.
         If not -> raise StaleMergeCandidateError.
      2. Apply `edits` to the canonical row's columns first.
         Field-level audit_log rows per founding spec §5: shape
         {value, confidence, source_excerpt}.
      3. For each field on `persons`:
         - canonical NULL, candidate non-NULL -> copy candidate -> canonical.
         - Both non-NULL, different values -> raise MergeConflictError
           (these should already be routed to conflicts during linking;
           defense-in-depth).
         - All other cases -> no-op.
      4. Fold candidate's person_variants into canonical (dedup on
         (variant, kind)).
      5. Retarget FKs across the five person-FK columns:
            - event_participants.person_id
            - person_relations.from_person_id
            - person_relations.to_person_id
            - person_states.person_id
            - entity_citations.entity_id     (WHERE entity_kind='person')
         For each column, two-phase: first detect collisions (rows that
         would violate the table's PRIMARY KEY after retarget), then
         resolve and UPDATE.

         Collision rules per table (the PRIMARY KEY determines what
         counts as a collision):
            - event_participants: PK (event_id, person_id, role). If
              both candidate and canonical play the same role in the
              same event, keep the higher-confidence row and DELETE
              the other before UPDATE.
            - person_relations: PK (from_person_id, to_person_id, kind).
              Collision can also be a SELF-LOOP — if the merge would
              create from=to (because the candidate had a relation TO
              the canonical, or vice versa), DELETE the relation outright
              (a self-loop has no meaning here).
            - person_states: PK (person_id, state_id, role,
              from_date_json). Higher-confidence row wins on collision.
            - entity_citations: PK (entity_kind, entity_id, citation_id).
              Collisions are idempotent (the row already exists for the
              canonical) — DELETE the candidate's row, no UPDATE needed.
            - person_variants: handled by step 4's fold (UNIQUE
              constraint on (person_id, variant, kind) makes the fold
              naturally collision-safe).

         Collision-resolution writes are part of the same transaction
         and produce their own audit_log rows (change_kind='merge_collision_resolved').
      6. DELETE candidate row from persons; DELETE its person_variants
         rows that didn't survive the fold.
      7. UPDATE merge_candidates SET status='merged', resolved_at=now()
         WHERE id=mc_id.
      8. Write audit_log: one record-level row (change_kind='merge',
         before_json=candidate snapshot, after_json=canonical snapshot
         post-merge), plus field-level rows for any `edits`.

    Returns MergeResult with the post-merge canonical row id +
    summary counts (variants_added, relations_retargeted, fields_edited).
    """

def reject_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    note: str | None = None,
) -> RejectResult: ...

def defer_merge(conn: sqlite3.Connection, mc_id: str) -> None: ...

def split_person(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    variants_to_extract: list[str],
    note: str | None = None,
) -> SplitResult: ...
```

`split_person` is the manual escape hatch for undoing a prior bad merge. Phase 5 stub: implement the function shape + audit_log writes; UI surfaces it via `s` shortcut but the full UX (per-variant pick) is intentionally minimal — text input listing variants to peel off into a new person row. Relations on the source row stay put (the curator can fix via the conflicts queue later).

### `curation/db.py`

- `connection() -> sqlite3.Connection` — opens the project DB in read-only mode (`file:...?mode=ro`); write paths get their own short-lived connection inside the merge functions.
- `open_merge_candidates() -> list[MergeCandidateRow]` — joins `merge_candidates` + `candidate_persons` (A) + `persons` (B) + the citation needed for evidence rendering.
- `coverage_stats() -> list[ChapterStatus]` — joins corpus.sqlite chapter list (108 chapters) against `pipeline_runs.scope_json` to find extracted chapter_nums.
- `chapter_citation_context(citation_id, *, paragraphs_before=2, paragraphs_after=2) -> ChapterContext` — resolves a citation_id to its source text + a context window in corpus.sqlite.
- `low_confidence_count() -> int` — derived from `candidate_facts.confidence < pipeline.config.LOW_CONFIDENCE_THRESHOLD`.

---

## 4. Data Flow

```
1. CURATOR launches:           streamlit run curation/app.py
   ├─ app.py reads READ-ONLY:
   │     - 108 chapters from corpus.sqlite (titles)
   │     - distinct pipeline_runs.scope_json -> extracted chapter_nums
   │     - count(*) FROM merge_candidates WHERE status='open'
   │     - count(*) FROM conflicts WHERE status='open' (display only)
   │     - low_confidence_count()
   └─ Renders coverage_grid + queue panel.

2. CURATOR clicks "Merge candidates (31 open)":
   ├─ Streamlit routes to pages/1_Merge_candidates.py
   ├─ db.open_merge_candidates() runs ONE join query.
   ├─ Result loaded into st.session_state["mc_queue"] (snapshot).
   ├─ Cursor at index 0 -> render shell for first row.
   └─ Evidence column: db.chapter_citation_context(a.citation_id, before=2,
      after=2) hits corpus.sqlite for the source paragraph + context.

3. CURATOR presses 'a' (accept):
   ├─ Handler opens a WRITE connection (separate from the read-only
   │   display connection) and calls
   │   pipeline.stage5_link.merge.accept_merge(conn, mc_id).
   ├─ accept_merge runs as a single BEGIN ... COMMIT (or ROLLBACK).
   ├─ On success: handler advances cursor, st.rerun() renders next candidate.
   ├─ On MergeConflictError: row stays open, banner surfaces, cursor stays,
   │   no audit_log row written.
   ├─ On StaleMergeCandidateError: cursor advances, banner "Already
   │   resolved, skipping", no DB change.
   └─ On any sqlite error: transaction rolls back, banner with error class,
      cursor stays.

4. CURATOR presses 'r' (reject):
   UPDATE merge_candidates SET status='rejected', resolved_at=now(),
     curator_note=<note> WHERE id=mc_id
   + audit_log row (change_kind='merge_rejected').
   No reject-memory writes (Phase 6 work).

5. CURATOR presses 'd' (defer):
   Cursor advances in-memory; merge_candidates row UNCHANGED on disk.
   Deferred rows reappear in the next session's queue load.

6. CURATOR presses 's' (split):
   split_person(conn, person_id, variants_to_extract=...) -> peels listed
   variants into a new person row, writes audit_log. Relations on the
   source row stay put.
```

**Two connections per session:** read-only for display, read-write for merge actions. Sqlite WAL mode is already on; concurrent reader+writer is fine. The write connection is opened inside each merge function call (short-lived) so failed transactions don't poison long-lived state.

**Snapshot vs live queue:** the queue is snapshotted at page load. Refresh requires explicit reload. The in-memory cursor can in principle point at an mc_id resolved in another tab — handled by the `status='open'` check in `accept_merge` (raises `StaleMergeCandidateError`, banner shown, cursor advances).

---

## 5. Error Handling

| Failure mode | Where it surfaces | Behavior |
|---|---|---|
| Stale `mc_id` (resolved in another tab) | `accept_merge` / `reject_merge` validate `status='open'` | Raise `StaleMergeCandidateError`; banner "Already resolved, skipping"; cursor advances; no audit_log |
| Non-null field disagreement | `accept_merge` step 3 | Raise `MergeConflictError`; banner "Field disagreement — use Edit & accept or Reject"; cursor stays; no audit_log |
| FK retarget PK collision (unhandled — defense-in-depth) | sqlite raises IntegrityError | Transaction rolls back; banner with sqlite error; cursor stays. The §3 step-5 collision rules should pre-empt this in practice; an actual raise here is a bug |
| FK retarget hits a row referencing a deleted canonical id | sqlite raises IntegrityError | Same as above — rollback, banner, cursor stays |
| Audit_log INSERT fails | inside same transaction | Rollback; banner; cursor stays |
| `chapter_citation_context` misses | `db.chapter_citation_context` | Returns placeholder `ChapterContext(text="(citation not found)", spans=[])`; evidence column shows the placeholder; **does not block the decision** |
| Cursor out of bounds (queue empty mid-session) | `pages/1_Merge_candidates.py` | Render "queue empty — N triaged" terminal screen + link back to home |
| Streamlit re-run during a click | Streamlit semantics | Handler is idempotent up to the `status='open'` check; double-click → second call hits stale-mc_id branch → no double-merge |
| Two curator tabs open | same as stale + UI snapshot drift | Tolerated; status check prevents corruption |
| `split_person` with bad variant list | `split_person` validates upfront | Raise `SplitValidationError`; banner; cursor stays |
| DB locked by stage 7 mid-write | sqlite raises OperationalError | Rollback; banner "DB busy, retry"; cursor stays |

**Two design rules pinned by the table:**

1. **Audit-log is atomic with the data change.** Either both write or neither. A half-written audit row would silently corrupt the field_history view (founding spec §5).
2. **Evidence-column failure is non-blocking.** Phase 4 surfaced cases where citation spans don't fully cover the extracted claim — the curator should be able to triage anyway. We never gate a decision on the evidence column rendering correctly.

---

## 6. Testing

### Unit tests — `tests/unit/test_stage5_merge.py`

- `accept_merge` happy path: variant fold dedupes on `(variant, kind)`; NULL canonical slots filled from candidate; FK retargets across the 5 person-FK columns (event_participants.person_id, person_relations.from_person_id, person_relations.to_person_id, person_states.person_id, entity_citations.entity_id WHERE entity_kind='person'); candidate row + dangling person_variants deleted; `merge_candidates.status='merged'`; one record-level `audit_log` row written.
- `accept_merge` collision branches (one test per collision rule in §3 step 5): event_participants PK collision → higher-confidence row wins; person_relations would create a self-loop → relation deleted; person_states PK collision → higher-confidence row wins; entity_citations duplicate → candidate row dropped silently. Each collision write produces an audit_log row with `change_kind='merge_collision_resolved'`.
- `accept_merge` with `edits`: record-level row + one field-level row per edit, conforming to the §5 `{value, confidence, source_excerpt}` shape.
- `accept_merge` error branches:
  - Stale mc_id → `StaleMergeCandidateError`, no DB change.
  - Non-NULL disagreement on a field → `MergeConflictError`, no DB change.
  - Canonical id doesn't exist → IntegrityError, no DB change.
  - **Atomicity verified by snapshotting the full DB before, calling, catching, snapshotting after, asserting equality.**
- `reject_merge`: status flip + curator_note persisted + audit_log row with `change_kind='merge_rejected'`.
- `defer_merge`: asserts zero rows change on disk.
- `split_person`: new person row exists, listed variants moved, audit_log row with `change_kind='split'`.

### Unit tests — `tests/unit/test_curation_db.py`

- `open_merge_candidates` returns rows sorted by `created_at ASC` and only `status='open'`.
- `coverage_stats` joins pipeline_runs.scope_json against the 108-chapter list — Ch.1-5 green, the rest gray.
- `chapter_citation_context` resolves a citation_id to the right paragraph window with `±N` respected; gracefully returns the placeholder on miss.

### Integration test — `tests/integration/test_curator_smoke.py`

- Builds a fixture DB by copying `data/changjuan.sqlite` into a `tmp_path` and running the test against the copy. Loops every open merge candidate; calls accept on the first half, reject on the second half, then verifies: `merge_candidates` all resolved; no orphan FKs in the 5 person-FK columns retargeted by `accept_merge`; `audit_log` row count equals decisions + collision-resolutions.
- This is the **acceptance check** for Phase 5's "UI ready" bar — if it passes, the merge surface works end-to-end against real data.

### Streamlit native testing

Skipped. `streamlit-testing-library` is flaky and Phase 5's components are thin enough that snapshot tests would mostly be testing Streamlit's own renderer. Contract we care about is the service layer, which is covered by units. Manual exercise via `streamlit run curation/app.py` happens at task completion and inside `phase5-prep.sh`.

---

## 7. `scripts/phase5-prep.sh` (acceptance check)

Mirrors `phase4-prep.sh`. Sections:

1. **Git tree status** — clean (only the expected untracked items).
2. **Pre-commit hooks** — all 5 pass.
3. **Pytest** — `uv run pytest -q` green.
4. **Integration smoke** — `pytest tests/integration/test_curator_smoke.py` passes against a copy of the live DB.
5. **Drift-check** — `curation/**/*.py` ↔ `knowledge/concepts/curation/streamlit-app.md` mapping per CLAUDE.md.
6. **Streamlit boot** — timeout-guarded smoke: spawn `streamlit run curation/app.py`, wait for HTTP 200 on `/`, kill. (5-second budget.)
7. **`PHASE5_DEFERRED`** — minimum: reject-memory, undo button, prefetch ergonomics, conflicts queue, low-confidence queue, person_relations zero-kind, LLM judge for ambiguous merges, re-extract button.

---

## 8. Knowledge articles

- **`concepts/curation/streamlit-app.md`** (~600-900 words) — new article.
  - UI shape (home screen + review screen layout)
  - Three queues + their roles
  - Action semantics (accept / edit & accept / reject / defer / split)
  - Audit-log contract (record-level + field-level shapes)
  - Connection management (read-only display vs write transaction)
  - Affects glob: `curation/**/*.py`.
- **`concepts/pipeline/linking.md`** — append a "Merge actions" section documenting `pipeline.stage5_link.merge`. Affects glob already covers `pipeline/stage5_link/**`.

The CLAUDE.md mapping table already includes both rows; no changes to that table are needed.

---

## 9. Build order hints (for the implementation plan)

Phase 5 decomposes naturally into roughly these task chunks (the writing-plans skill will refine):

1. **Schema additions: none.** Skip.
2. **`pipeline/stage5_link/merge.py` + unit tests.** Build the load-bearing module first; verify the atomicity guarantee before any UI exists.
3. **`curation/db.py` + unit tests.** Read helpers in isolation.
4. **`curation/components/{shell,coverage_grid,records}.py`.** Pure rendering, no state.
5. **`curation/app.py`** (home screen) + **`curation/pages/{2,3}_*.py`** stubs.
6. **`curation/pages/1_Merge_candidates.py`** (the review screen) + keyboard shortcuts.
7. **`tests/integration/test_curator_smoke.py`** + **`scripts/curator-smoke`**.
8. **`scripts/phase5-prep.sh`.**
9. **`pipeline/cli.py`** — `changjuan curator` subcommand.
10. **Knowledge article** + log entry. Commit-by-commit drift-check compliance per CLAUDE.md.

Order chosen so the riskiest code (merge logic, FK retargeting, audit_log atomicity) gets unit tests before any view layer is built; once it works, the UI is mostly assembly.

---

## 10. Risks & open questions

- **Streamlit multipage convention vs single-page.** The plan uses Streamlit's auto-sidebar (`pages/1_...py` naming). If that proves clunky in practice (e.g., page state doesn't survive navigation cleanly), fall back to a single `app.py` with `st.tabs` or `st.navigation`. Decided in the implementation phase, not here.
- **`streamlit-shortcuts` package**. Pulls a small dependency. Acceptable for a single-curator local tool; flag it during the plan-writing if uv resolution causes friction.
- **Read-only sqlite connection mode (`mode=ro`)**. The whole codebase opens the DB read-write today. Verify `mode=ro` URI works against the current sqlite3 build during the first implementation task; fall back to a normal connection with a comment if needed.
- **Side-by-side rendering at narrow widths.** The 40/40/20 shell assumes a wide window. Streamlit's default width handles 1280px+ fine; smaller windows wrap inelegantly. Acceptable for v1 (curator is on a desktop); flag in the article.
- **Defer semantics on a single-curator project.** Defer leaves status='open' so the row reappears on next load. If the curator wants permanence they reject. This is a deliberate simplification of the §4 implication of a 'deferred' status — flagged here so a Phase 6 reviewer doesn't assume it's an oversight.
- **`split_person` minimal UX.** The fully-fleshed split flow (per-variant picker, FK fix-up) is intentionally deferred. The Phase 5 version writes a correct audit_log row but the resulting new person row will be relation-less. Future undo will need to reconcile this.

---

## 11. PHASE5_DEFERRED carryforward (for `scripts/phase5-prep.sh`)

Items deferred to Phase 6+:

1. **Reject-memory** — `(canonical_id, candidate_variant_fingerprint)` lookup table to prevent the linker re-flagging rejected pairs on rerun.
2. **Undo button** — reverse a merged/rejected decision via audit_log replay.
3. **Conflicts queue** — full UX for the conflicts queue (12 open rows today).
4. **Low-confidence extractions queue** — sorted-by-chapter triage page over `candidate_facts.confidence < threshold`.
5. **Re-extract button** — per-chapter re-run of stage 3 with diff-against-curated-state.
6. **`person_relations` empty-`kind` extractor bug** — extract-v2 emits relations with empty `kind`; CHECK constraint rejects them; `person_relations` table is at 0 rows.
7. **LLM judge for ambiguous merges** — populate `llm_judgment_json` before the curator sees the row.
8. **Prefetch ergonomics** — §4 target of <200ms per record via prefetch + custom JS shortcut handling.
9. **Linker for events / places / states / relations** — Phase 3 was persons-only; merge_candidates today only has person rows.
10. **Coverage grid per-chapter detail view** — clicking a cell drills into the chapter.
11. **Search box** — disabled in Phase 5; full implementation requires deciding what's searched and how results render.
12. **Headline counter widgets** — per §4 deferred until a week of curation reveals which numbers matter.

---

*End of Phase 5 design spec. Next step after approval: invoke `superpowers:writing-plans` to produce the implementation plan.*
