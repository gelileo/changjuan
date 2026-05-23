---
title: Curation app — Streamlit retrospective review
type: concept
area: curation
updated: 2026-05-22
status: mature
load_bearing: false
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
affects:
  - curation/**/*.py
---

## What it is

The curation app is a single-page Streamlit application run locally by the project's single curator. It reads from and writes to `data/changjuan.sqlite` — the same database produced by the pipeline. It is not a gate on pipeline delivery: the pipeline produces a complete, usable knowledge graph without any human review. The curation app enables retrospective correction and quality uplift at any time after extraction.

## Three review queues

The app presents three queues in priority order:

1. **Unresolved Person merge candidates** — stage 5 produced candidate merges that require human confirmation (e.g., two names that might or might not refer to the same person). Estimated 3–5 min per decision. Built first because stage-5 linking errors compound: a missed merge duplicates every downstream fact about that person.

2. **Open Conflicts** — field-level disagreements between extraction runs (both auto-provenance, similar confidence) that the pipeline flagged for human resolution. Estimated under 1 min per decision. Each Conflict row already carries a `current_best_variant_idx` suggestion based on highest confidence.

3. **Low-confidence extractions** — canonical field values whose confidence is below a configurable threshold (TBD in Phase 2). Estimated under 30 s per decision since these are quick accept/reject judgements.

## Home screen (v1)

The v1 home screen is a 108-cell chapter coverage grid showing extraction status per chapter, three queue entry-point buttons with pending-count badges, and a free-text search box. No headline counters (total persons, total events) are displayed in v1 — those are deferred to Phase 2 once extraction coverage is meaningful.

## Audit and reversibility

Every curator decision writes an `audit_log` row with `change_kind='set'` or `change_kind='resolve'`, `actor='curator'`, and the before/after values. No decision is permanent: the audit log preserves full history and any change can be manually reverted by a curator. The pipeline never overwrites a `provenance='curated'` field silently — disagreements become new Conflict records.

## Phase 1 status

Not yet implemented. `curation/__init__.py` is a placeholder. The curation app is a Phase 2 build target. This article exists so the `curation/**/*.py` drift-check mapping resolves to a valid article from the first Phase 2 commit touching `curation/`.

## DB access layer (Phase 5 Task 7)

`curation/db.py` provides the read-only data-fetching layer for the curation app. All connections are opened via a `_ro_connect` context manager using the `?mode=ro` URI flag — writes are prohibited at the SQLite level. The module exports:

- **`MergeCandidateRow`** — frozen dataclass for rows from `merge_candidates` (mc_id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, llm_judgment_json, created_at).
- **`ChapterStatus`** — frozen dataclass for chapter extraction coverage (chapter_num, title, extracted bool, latest_run_id).
- **`ChapterContext`** — frozen dataclass for a resolved citation with surrounding paragraph context (citation_id, text, span_start, span_end, paragraphs list).
- **`open_merge_candidates(db_path)`** — returns all `status='open'` merge candidates sorted by `created_at ASC`.
- **`coverage_stats(db_path, *, corpus_path=None)`** — reads all chapters from `corpus.sqlite` (defaults to `db_path.parent/corpus.sqlite`) and cross-references with `pipeline_runs` where `stage='extract'` and `scope_json` contains a `chapter_num` or `chapter` key. Returns 108 `ChapterStatus` rows for a complete corpus.
- **`low_confidence_count(db_path)`** — counts `candidate_facts` rows with `confidence < LOW_CONFIDENCE_THRESHOLD` (0.55). Returns 0 on `OperationalError` (table absent in early-stage databases).
- **`chapter_citation_context(citation_id, *, corpus_path, ...)`** — resolves a citation to its source paragraph via a `citations JOIN chunks` query. Returns `ChapterContext(text="(citation not found)")` on miss — non-blocking per spec §5.

No Streamlit imports are present in this module; it is pure data access.

## Components (Phase 5 Task 8)

`curation/components/` contains three pure-rendering primitives that the Streamlit pages (Tasks 9–10) compose. None carry state, write to the DB, or import from `curation.db` beyond type hints.

### `shell.render_shell`

Three-column layout (40 / 40 / 20 ratio) for the review screen. Accepts three callables (`render_left`, `render_center`, `render_right`); each callable owns its column's content. Column headers are injected as HTML divs with the class `curation-label` (`EVIDENCE`, `CANDIDATE PAIR`, `DECISION`).

### `coverage_grid.render_coverage_grid`

Renders a 108-cell chapter coverage grid using inline CSS (`_GRID_CSS`) and a single HTML string assembled from `list[ChapterStatus]`. Green cells (`.coverage-cell.extracted`) represent chapters with at least one completed extraction run; grey cells represent pending chapters. A `st.caption` line below the grid shows the extracted / total count.

### `records.render_pair`

Side-by-side candidate-vs-canonical field renderer. Computes a `list[FieldDiff]` for the five tracked fields (`canonical_name`, `gender`, `clan_name`, `state_id`, `notes`). Each diff carries a badge (`same` / `one_null` / `disagree`) that drives background colour on the rendered spans. In `edit_mode=True`, the canonical column renders `st.text_input` widgets instead of readonly spans and returns an `edits: dict[str, Any]` with changed fields; in read-only mode returns `None`. `surface_features_json` is rendered as a `st.caption`; `llm_judgment_json` is rendered inside a `st.expander`.

## Home screen and stub pages (Phase 5 Task 9)

`curation/app.py` is the Streamlit entry point (`streamlit run curation/app.py`). It sets page config, shows the chapter coverage grid (gated on `CORPUS_PATH.exists()`), renders three queue links, and provides a disabled search box (Phase 6).

Queue rendering:
- **Merge candidates** — `st.page_link("pages/1_Merge_candidates.py", ...)` with open-count badge via `open_merge_candidates(DB_PATH)`. Target page is created in Task 10; Streamlit emits a warning until then.
- **Conflicts** — greyed-out HTML div, no link (Phase 6 stub).
- **Low confidence** — greyed-out HTML div with `low_confidence_count(DB_PATH)` badge (Phase 6 stub).

`curation/pages/2_Conflicts.py` and `curation/pages/3_Low_confidence.py` are Phase 6 stub pages. Each calls `st.set_page_config` and renders a single `st.warning` explaining the deferral. Streamlit's multipage convention requires no `__init__.py` in `pages/`.

`streamlit-shortcuts` (v1.2.1) added as a project dependency for Task 10 keyboard shortcuts.

## Merge-candidates review screen (Phase 5 Task 10)

`curation/pages/1_Merge_candidates.py` is the workhorse review page. It uses the 40/40/20 `render_shell` layout (evidence / candidate-pair / decision columns) and wires all five curator actions.

### Queue management

- `_load_queue()` — loads `list[MergeCandidateRow]` once into `st.session_state["mc_queue"]` via `open_merge_candidates(DB_PATH)`; cursor is tracked in `st.session_state["mc_cursor"]`. The queue is frozen for the session; `_reload()` clears both keys and calls `st.rerun()`.
- `_advance()` / `_retreat()` — increment / decrement cursor (retreat clamped to 0).
- When the cursor reaches the end of the queue, a completion message with item count is shown and a "Reload queue" button is offered.

### DB connections

Reads use short-lived URI connections (`file:{path}?mode=ro`) opened inline. Writes use `_write_connect(db_path)` (plain `sqlite3.connect`, `PRAGMA foreign_keys = ON`) opened per-action, closed in a `finally` block.

### Five actions (render_right column)

| Button | Key | Function | Handles |
|--------|-----|----------|---------|
| Accept merge | `a` | `_do_accept(mc_id)` | `StaleMergeCandidateError` → skip; `MergeConflictError` → error; `MergeError` → error |
| Edit & accept | `e` | enters edit mode first, then `_do_accept(mc_id, edits=edits_captured)` | same as above; clears `edit_mode` on success |
| Reject | `r` | `_do_reject(mc_id)` | `StaleMergeCandidateError` → skip; `MergeError` → error |
| Defer | `d` | `_do_defer(mc_id)` | always advances |
| Split | `s` | `_do_split(candidate_b_id, variants, note)` inside expander | `MergeError` → error |

### Edit mode

The `edit_mode` boolean lives in `st.session_state["edit_mode"]`. When `True`, `render_pair` renders `st.text_input` widgets for the canonical column and returns an `edits: dict[str, Any]` with changed fields. The `edits_captured` variable is set by `render_center` (via `nonlocal`) and consumed by the "Edit & accept" button in `render_right`.

### Keyboard shortcuts

`streamlit_shortcuts.add_shortcuts` maps `a/e/r/d/j/k` to the corresponding button labels (`**kwargs` form: `add_shortcuts(a="...", e="...", ...)`). `mypy.ini` has `[mypy-streamlit_shortcuts] ignore_missing_imports = True`.

**Phase 6 dependency-drift note:** Pre-Phase 6 the function was named `add_keyboard_shortcuts` and took a single `dict` argument. `streamlit-shortcuts >= 1.3` renamed it to `add_shortcuts` with a `**kwargs` signature; Phase 6's bug-fix at the start of Track B's walk migrated to the new API. The pin in `pyproject.toml` (`streamlit-shortcuts>=1.2.1`) is a floor only; fresh installs pick up the new API.

### `_load_person` dual-table lookup (Phase 6 walk fix #1)

`_load_person` in `pages/1_Merge_candidates.py` previously queried only the `persons` table. After Phase 5.1 established that `merge_candidates.candidate_a_id` typically references `candidate_persons.id`, the A column on the review screen rendered every field as `-` because the lookup returned no row. The helper now falls back to `candidate_persons` when `persons` misses — mirroring the dual-table pattern in `pipeline.stage5_link.merge._load_reject_payload`. Counted against the Track B friction-fix budget (1/3 used).
