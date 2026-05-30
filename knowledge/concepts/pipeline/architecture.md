---
title: Automation-first pipeline architecture
type: concept
area: pipeline
updated: 2026-05-22
status: thin
load_bearing: true
references:
  - concepts/data-model/knowledge-graph.md
  - concepts/verification/confidence-and-invariants.md
affects:
  - pipeline/config.py
  - pipeline/stage1_ingest.py
  - pipeline/stage2_chunk.py
  - pipeline/stage4_normalize.py
  - pipeline/stage7_load.py
  - pipeline/stage9_export.py
---

## What this is

The pipeline that produces the knowledge graph is a 9-stage sequential ETL: **Ingest → Chunk → Extract (LLM) → Normalize → Link & dedup (LLM) → Cross-canon check (LLM, gated) → Load → Curate (human, optional) → Freeze & export**. Each stage has typed inputs/outputs, is idempotent over its input, and is resumable from the last successful chunk. Three stages are LLM-driven (3, 5, 6) and share a content-hash cache; the rest are deterministic Python. The load-bearing rule is that **every stage produces a complete, usable best-guess result without any human in the loop**. Curation is purely retrospective: a curator can revisit and correct any record at any time, but no stage waits for human input. The output `data/changjuan.sqlite` is queryable end-to-end after any stage-7 load, with or without curation. The frozen export bundle (stage 9) writes `graph.sqlite` (v2 layout; `schema_version=2`).

## Why this shape, not the alternatives

A single-LLM-agent pipeline (one tool-using agent decides everything per chapter) was considered and rejected — hard to evaluate, hard to cache, hard to tune one capability without breaking another, non-deterministic failures. A "curate-as-you-go" pipeline where human review gates downstream stages was considered and rejected because the user is one person extracting from 108 chapters plus 左传/史记; making curation mandatory would mean the system is unusable until hundreds of hours of review are done. Optional retrospective curation lets the system deliver value immediately and improve incrementally.

## What would invalidate this article

- Any stage starting to require human input to complete.
- "Current best variant" auto-resolution becoming impossible for some class of disagreement.
- Curator overrides ever getting silently overwritten by re-extraction (they don't; divergences become Conflict records).
- A new corpus that can't be added without redesigning stages 1–2.

## Stage 4 — normalize

`pipeline/stage4_normalize.py` provides `normalize_date_string(original, anchor_json=None) -> str`, a thin wrapper over `pipeline.dates.parse_date`. Callers pass a raw date string and optionally a prior date's JSON (for relative references); the function returns a JSON string ready to insert into any `*_date_json` column. This is the only stage-4 entry point in Phase 1; extraction prompts and batch normalization land in Phase 2.

## Stage 9 — canonical snapshot

`_snapshot_canonical_only` produces the candidate-stripped `graph.sqlite` that the enrichment passes below mutate. It snapshots `src_db` via `VACUUM INTO` (not `shutil.copyfile`), then drops `candidate_*` tables and `llm_cache` and `VACUUM`s. The `VACUUM INTO` choice is load-bearing: the canonical DB runs in WAL journal mode, and `shutil.copyfile` would copy only the main `.sqlite` file — silently dropping committed-but-un-checkpointed transactions living in the `-wal` sidecar. A live connection sees the full main+WAL view, which `VACUUM INTO` snapshots intact. See `concepts/pipeline/export-contract.md` for the full rationale and the data-loss measurement that motivated the fix.

## Stage 9 — citation enrichment pass

`pipeline/export_enrich.py::build_citations_table` is called by `export_bundle` immediately after `_snapshot_canonical_only`, before the manifest is written. It reads every distinct `citation_id` from `entity_citations` in the snapshot, fetches the matching rows from `corpus.sqlite::chunks`, and writes a `citations(citation_id, document_id, paragraph_start, paragraph_end, text)` table into the export-only `graph.sqlite`. Fail-loud on any missing chunk id. The `export_bundle` signature requires `corpus_db: Path` and `book_meta: dict[str, object]`; the latter is sourced from `data/books/<book_id>/book-meta.json` and provides book identity and capability metadata written into `manifest.json`. `_source_editions` accepts `corpus_db` directly (and guards against a missing `documents` table for tests that supply a chunk-only corpus).

## Stage 9 — pinyin enrichment pass

`pipeline/export_enrich.py::add_pinyin_columns` is called by `export_bundle` immediately after `build_citations_table`, before the manifest is written. It adds a `pinyin` TEXT column (idempotently via `PRAGMA table_info`) to both `persons` and `person_variants` in the snapshot, then populates each row using `to_pinyin` — a pure function wrapping `pypinyin.lazy_pinyin` with `Style.NORMAL` (toneless joined lowercase). This enables client-side romanized-input search without any query-time conversion. Non-Han characters pass through pypinyin as-is; polyphonic characters resolve to their most-common reading (documented limitation).

## Stage 9 — deed_importance enrichment pass

`pipeline/export_enrich.py::build_deed_importance` is called by `export_bundle` immediately after `add_pinyin_columns`, before the manifest is written. It reads every `(event_id, person_id, event.type)` triple from the snapshot's `event_participants JOIN events`, computes a blended importance score for each participation (global type-weight × log-scaled participant and citation counts × within-person rarity salience), and writes results into `deed_importance(event_id, person_id, score PRIMARY KEY (event_id, person_id))`. The table uses `INSERT OR REPLACE` so multi-role participations (where one person appears in one event under more than one role) collapse to a single row per `(event_id, person_id)` pair — a known v1 limitation noted in the export contract. `TYPE_WEIGHTS`, `DEFAULT_WEIGHT`, and `SALIENCE_WEIGHT` constants in `pipeline/export_enrich.py` are explicitly tunable.

## Stage 9 — texts/ copy pass

`export_bundle` copies `data/readable/ch*.md` files into `out_dir/texts/` in sorted order after the manifest write. The copy is gated on `readable_dir.is_dir()`, so an absent `data/readable/` directory silently produces an empty `texts/` subdirectory. The source path is `cfg.readable_dir` (`data/readable/`). This is the phase-2 Reader payload; the v1 web bundle ships only `graph.sqlite`. `export_bundle` gains the required kw-only param `readable_dir: Path`; all call sites must supply it. `Config.readable_dir` is the canonical accessor.

## Stage 9 — dynamic table enumeration in counts

`_count_rows` in `stage9_export.py` enumerates tables via `sqlite_master` rather than a hardcoded list, matching the same dynamic approach used in `_snapshot_canonical_only`. Since the snapshot has `candidate_*` and `llm_cache` already stripped, the dynamic set equals the canonical set exactly. No separate constant to keep in sync.

## Stage 7 — JSON-aware equality for *_json fields

`_scalars_equal(field, old_val, new_val)` compares scalar field values for equality. For fields ending in `_json`, it deserializes both values before comparing so that two JSON strings with the same content but different key orderings are treated as equal. This prevents spurious Conflicts when the LLM produces the same JSON with non-deterministic key order across runs.

## Stage 7 — per-field confidence lookup

`_merge_scalar_fields` consults `_last_field_confidence` (an `audit_log` query) to determine the prior confidence for each scalar field before deciding whether to update or emit a Conflict. This prevents the stale row-level `persons.confidence` from being used as the baseline after a high-confidence update has already occurred in a previous run. If no prior set-event exists for the field, the row-level confidence is used as fallback.

## Stage 7 — slug collision guard

`load_candidate_persons` derives each new Person's id as `per:<slug>`. If that id is already held by a *different* Person (slug collision from distinct names), the loader appends a 6-character SHA-256 hex suffix: `per:<slug>-<hash6>`. This is a defensive correctness guarantee; in practice the matcher merges same-name candidates before this path is reached, but it prevents a `PRIMARY KEY` crash when two distinct canonical names happen to produce the same ASCII slug.

### `_PARA_SEP` regex

`pipeline/stage2_chunk.py` splits documents on `r"\r?\n+"` — one or more newlines.
The upstream 东周列国志 JSON uses single `\n` between paragraphs; an earlier
version required blank lines (`r"\r?\n\s*\r?\n+"`) and silently collapsed every
chapter into one chunk. The regression test
`test_chunks_emerge_from_single_newline_separated_paragraphs` guards against
re-introducing the bug.

## First commitments (true once code lands)

- Stages live under `pipeline/stage{1,2,3,4,5,6,7,9}_*.py`. Stage 8 is the Streamlit curation app under `curation/`.
- LLM cache: `pipeline/llm_cache.py`, keyed by `hash(prompt_template_version, model, input)`.
- Conflict auto-resolution rule: configurable precedence (default 史记 > 左传 > 东周列国志 for dates; 东周列国志 wins narrative detail). The picked variant is recorded in `Conflict.current_best_variant_idx`; alternatives are preserved.
- `pipeline_runs.stats_json.thresholds_breached` is the gate for stage-9 freeze.
- `--chapters N..M` flag on every stage for dry runs; nothing requires "full corpus" mode to run.
- `pipeline/config.py::GOLDEN_PR_THRESHOLDS` gates `changjuan golden-eval` per entity kind. Recalibrated after v2 baseline (Task 29.4): relation.precision lowered 0.75 → 0.65 (v2 measured 0.6984); all others unchanged. See `concepts/runtime/configuration.md` for the full table + recalibration history.
- `pipeline/config.py::LINKER_AUTO_MERGE_THRESHOLD` (0.70 since Phase 6.5; 0.75 in Phases 3-5) and `LINKER_QUEUE_THRESHOLD` (0.40) are the Phase 3 dispatch dial for Stage 5 linker (`pipeline/stage5_link/linker.py::link_run`). Scores at or above auto → write `match_target_id`; between queue and auto → write `merge_candidates` row; below queue → candidate creates a new canonical at load. See `concepts/runtime/configuration.md` for full calibration history.
- `pipeline/config.py::LOW_CONFIDENCE_THRESHOLD` (0.55) added in Phase 5 Task 7. Read by `curation.db.low_confidence_count` to surface low-confidence candidate facts in the curation app's third review queue. No pipeline stage reads this constant; it is curation-layer only.
