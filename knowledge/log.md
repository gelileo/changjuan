# Build Log

## [2026-05-21] stage7: load_candidate_events + merge_date_field helper (Task 18)

Added `pipeline/stage7_load/helpers.py::merge_date_field` — a shared date-merge helper implementing spec §7.2. Precision rank: `point > circa > range`. A more-precise date wins over a less-precise one even at slightly lower confidence (within `_SIMILAR_CONFIDENCE_DELTA = 0.1`). On equal precision, higher confidence wins; tie keeps current.

Added `pipeline/stage7_load/events.py::load_candidate_events`. Composite match key: `(type, year_bce, primary_place_id)` — year extracted from candidate's `date_json` via Python JSON parsing; matched in the canonical table via SQLite `json_extract`. ID format: `evt:<slug>-<year>bce` (or `evt:<slug>` when no year). SHA-256 6-char suffix collision guard. Scalar fields merged: `type`, `outcome`, `summary`, `primary_place_id` — same higher-confidence-wins + Conflict emission semantics as persons.py. `date_json` merged via `merge_date_field`. Citation accumulation via `record_citation`. Provenance `'auto'` on create. `pipeline/stage7_load/__init__.py` updated to re-export `load_candidate_events`.

Four new helper tests in `tests/unit/test_stage7_helpers.py`. Four new events loader tests in `tests/unit/test_stage7_load_events.py`. Total: 118 tests.

Key adaptation from spec: `primary_place_id` defaults to `None` in tests to avoid FK constraint failures (events.primary_place_id references places.id, no place pre-seeded). Events loader uses positional tuple indexing (not `sqlite3.Row`) matching the pattern of places.py/states.py — `open_canonical_db` does not set `row_factory`, only `connect()` does.

Articles touched: `concepts/pipeline/load-and-merge.md` (new Events section + `merge_date_field` section; updated `implemented:` and `What would invalidate this article`), `concepts/verification/testing.md` (new Stage 7 helpers tests section + Stage 7 load_candidate_events tests section).

## [2026-05-21] stage7: load_candidate_states with field-level scalar merge (Task 17)

Added `pipeline/stage7_load/states.py::load_candidate_states`. Mirrors `places.py` shape: match by `name`; scalar merge (`type`, `ruling_clan`, `founded_date_json`, `ended_date_json`) with higher-confidence-wins (delta threshold 0.1); citation accumulation via `record_citation`; `audit_log` uses `change_kind='create'/'set'`. No variants table — name-only match. Slug collision guard uses SHA-256 hex suffix (`sta:<slug>-<hash6>`). Date JSON fields treated as opaque strings for now; Task 18 will add `merge_date_field` for semantic date merging. `state_capitals` relation rows are NOT handled here — they land in Task 19 (`load_candidate_relations`). `pipeline/stage7_load/__init__.py` updated to re-export `load_candidate_states`.

Three new tests in `tests/unit/test_stage7_load_states.py`. Total: 110 tests.

Key adaptation from spec: `candidate_states` uses `chunk_id`/`quote` columns (not `citation_id`), matching the canonical schema. Scalar fields are `type`, `ruling_clan`, `founded_date_json`, `ended_date_json` (not `name` in the merge loop — name is the match key).

Articles touched: `concepts/pipeline/load-and-merge.md` (new States section; updated `implemented:` and `What would invalidate this article`), `concepts/verification/testing.md` (new States test section).

## [2026-05-21] stage7: load_candidate_places with field-level scalar merge (Task 16)

Added `pipeline/stage7_load/places.py::load_candidate_places`. Mirrors `load_candidate_persons` shape: match by `name`; scalar merge (`type`, `lat`, `lon`, `coord_confidence`, `modern_equiv`) with higher-confidence-wins (delta threshold 0.1); citation accumulation via `record_citation`; `audit_log` uses `change_kind='create'/'set'`. No variants table — name-only match. Slug collision guard uses SHA-256 hex suffix (same as persons). `pipeline/stage7_load/__init__.py` updated to re-export `load_candidate_places`.

Three new tests in `tests/unit/test_stage7_load_places.py`. Total: 107 tests.

Key adaptation from spec: `candidate_places` uses `chunk_id`/`quote` columns (not `citation_id`), matching the canonical schema. Spec template's `_suffix_if_collision` helper does not exist; inline hash-suffix logic used instead (matching persons.py). `_audit` positional signature differs from spec guess — matched actual signature.

Articles touched: `concepts/pipeline/load-and-merge.md` (new Places section; updated `implemented:` and `What would invalidate this article`).

## [2026-05-21] cli: list-unresolved-dates + resolve-relative-date verbs (Task 15)

Added two curator triage verbs to `pipeline/cli.py`:

- `list-unresolved-dates` — queries canonical `events` for rows with `inference_kind = 'relative_to_prior_event'`, `year_bce = null`, and no `relative_anchor_event_id`; prints `event_id\toriginal_text` for each.
- `resolve-relative-date --event-id ID --anchor-event-id ID [--offset N]` — sets `relative_anchor_event_id`, calls `resolve_relative_dates` to recompute `year_bce`, persists the update, and writes an `audit_log` entry (`change_kind = 'curator_override'`). The `--offset` flag handles tokens not in the `_RELATIVE_OFFSETS` table (e.g. 其后五年).

Also added `open_canonical_db` and `open_corpus_db` convenience functions to `pipeline/db.py`; both open or create the SQLite file, apply the appropriate schema, and return a bare `sqlite3.Connection` (not a context manager) — intended for CLI verbs and tests.

Four new tests in `tests/unit/test_resolve_relative_date_cli.py`. Total: 104 tests.

Articles touched: `concepts/runtime/cli.md` (new Phase-2 subcommands section, updated `affects:` to include test file, updated `updated:` date and `status`).

## [2026-05-21] dates: resolve_relative_dates wrapper for within- and cross-chunk anchors (Task 14)

Added `pipeline.dates.resolve_relative_dates(records, conn, *, anchor_lookup, offset_override)`.
Walks a sequence of records, maintaining a rolling anchor for walkback resolution. When
`date.relative_anchor_event_id` is set, the explicit anchor overrides walkback and is
resolved via `anchor_lookup(conn, event_id)` (default: query canonical events table).
Cycle detection raises `RelativeResolveError("cycle ...")` and dangling anchors raise
`RelativeResolveError("dangling ...")`. BCE-arithmetic offset convention matches existing
`_RELATIVE_OFFSETS` table (明年 = −1). Also promoted `from typing import Callable, Optional,
Sequence` to the top-level imports block. Six new tests in
`tests/unit/test_dates_relative.py` covering: walkback, cascading relatives, null anchor,
explicit-anchor override, dangling, and cycle.

Articles touched: `concepts/data-model/dates-and-reigns.md` (new
`relative_to_prior_event` resolution section + `affects` glob updated to include
`tests/unit/test_dates_relative.py`).

## [2026-05-21] dates: DateDict accepts optional relative_anchor_event_id

Added `relative_anchor_event_id: NotRequired[str | None]` to `DateDict`.
Cross-chunk anchor field is the manual escape hatch for the curator path;
within-chunk dereferencing remains the automatic default. Existing date_json
values without the field continue to work.

Articles touched: concepts/data-model/dates-and-reigns.md (will be updated in Task 14).

## [2026-05-21] config: Phase 2 constants for extraction, QA, golden thresholds (Task 12)

Added Phase 2 configuration constants to `pipeline/config.py`: EXTRACTION_DIR,
QA_MISMATCH_THRESHOLD, QA_SAMPLE_FRACTION, QA_SAMPLE_FLOOR, QA_SAMPLE_CEILING,
and GOLDEN_PR_THRESHOLDS. Threshold values are placeholders to be recalibrated
after the first golden Ch.1 measurement (Task 29). Used by stage-3 extraction
(Task 22), sampling QA (Task 31), and golden-eval CLI (Task 29). Added
`test_phase2_constants_exist()` in `tests/unit/test_config.py`.

Articles touched: concepts/runtime/configuration.md (new, explains all Phase 2
constants and design rationale), concepts/verification/testing.md (Phase 2
constants test section added).

## [2026-05-21] confidence: deterministic stage-3 score stub (Task 11)

Created `pipeline/confidence.py::score_extraction_record` — the entry point for
stage-3 confidence scoring. v1 stub: base 0.70 + citation-quote-length bonus
(max +0.15 at 15+ chars) + justification-completeness bonus (+0.10 when all
scalar fields have non-empty justifications). Score capped at 0.95 to reserve
1.0 for curated records. Future phases will tune weights against sampling-QA
reliability diagrams. Added 4 new unit tests in `tests/unit/test_confidence.py`
exercising base score, ceiling enforcement, quote-length monotonicity, and
justification completeness.

Articles touched: concepts/verification/confidence-and-invariants.md (stage-3
confidence stub section + affects glob), concepts/verification/testing.md
(confidence scorer stub tests section).

## [2026-05-21] schemas: canonical extraction-output schema (Task 10)

Created `pipeline/schemas/extract_output.py::EXTRACT_OUTPUT_SCHEMA` —
single source of truth for stage 3's structured output. Used by the Python
validator (Task 21) and mirrored to .claude/skills/changjuan-extract/extraction-schema.yaml
via the regenerator script (Task 26). PROMPT_TEMPLATE_VERSION constant
tracks the prompt template version (initial value 'v1'). Person schema
includes the social_category enum field added in the previous commit.

Also added `[mypy-jsonschema]` override to `mypy.ini` (suppress `import-untyped` for jsonschema — no stubs installed) and `disallow_untyped_calls = False` to `[mypy-tests.*]` (test helper functions are untyped by convention in this project).

Articles touched: concepts/verification/testing.md (extraction-output schema tests section added).

## [2026-05-21] schema: add `social_category` to Person (coarse-grained type)

Added an optional enum field to the Person entity (and `candidate_persons`):
royalty / noble / official / military / religious / clergy / commoner /
servant / foreign / mythic / unknown. Surfaced as a schema gap while
annotating golden Ch.1's unnamed-but-acting persons (老宫人, 女婴, 妇人,
男子) — the existing `person_states.role` field is too narrow to capture
coarse social class for figures who don't hold named state offices.
Specific positions (太宰 / 大宗伯 / etc.) still live in `person_states.role`;
`social_category` is independent.

Schema change scoped to:
- pipeline/schemas/canonical_schema.sql (persons + candidate_persons TEXT column)
- tests/golden/loader.py (enum validation)
- tests/golden/precision_recall.py (block matches on category mismatch when both set)
- tests/golden/ch01/persons.yaml (13 records backfilled)
- docs/superpowers/specs/2026-05-20-changjuan-design.md (data-model addendum)
- knowledge/concepts/data-model/knowledge-graph.md (field documentation)

Articles touched: concepts/data-model/knowledge-graph.md, concepts/verification/testing.md.

## [2026-05-21] tests/golden: precision_recall.py harness

Created `tests/golden/precision_recall.py::compute_pr`. Per-entity-type
matching rules: Persons match on variant-set overlap + state_id agreement;
Events on type + ±1y date + primary_place_id; Places/States on name;
Relations on full tuple. Returns dict matching `stats_json.extraction.per_entity_type`
shape. Five tests in `tests/unit/test_precision_recall.py`.

Articles touched: none (test infrastructure).

## [2026-05-21] tests/golden: loader.py validates YAML structure + cross-references

Created `tests/golden/loader.py::load_golden`. Validates: required fields per
entity kind, citation FK integrity (all citations referenced by other entities
exist in citations.yaml), date inference_kind allowlist, relative-anchor cycle
detection + dangling-anchor rejection. Raises `GoldenLoadError` on any
violation. Five tests in `tests/unit/test_golden_loader.py`.

Articles touched: `concepts/verification/testing.md` (golden YAML loader tests section added). Also added `[mypy-yaml]` override to `mypy.ini` to suppress `import-untyped` for pyyaml (no stubs installed).

## [2026-05-21] deps + golden skeleton: pyyaml, jsonschema, tests/golden/

Added pyyaml and jsonschema to dependencies. Created tests/golden/ch01/README.md
with annotation conventions skeleton. Setup for Task 7 (loader) and Task 9
(hand annotation).

Articles touched: `concepts/verification/testing.md` (golden chapters section updated to document the directory structure and README conventions).

## [2026-05-21] stage 7: entity_citations accumulator on every create/update (deferred #7)

Added `pipeline/stage7_load/citations.py::record_citation`. Called from every Person create/update path in `persons.py` (single call site at the end of the `load_candidate_persons` loop covers both branches). Idempotent on the unique `(entity_kind, entity_id, citation_id)` tuple via `INSERT OR IGNORE`; the PRIMARY KEY on `entity_citations` serves as the constraint. Re-loading the same candidate twice writes one `entity_citations` row, not two. Each candidate's `chunk_id` is used as the `citation_id` value.

Three new tests in `tests/unit/test_stage7_citations.py` cover: first-load writes one row, second load with different chunk_id accumulates a second row (one Person), same candidate loaded twice stays idempotent.

Articles touched: `concepts/pipeline/load-and-merge.md` (citation accumulation section updated from "deferred" to implemented; `affects` glob updated to `pipeline/stage7_load/**`).

## [2026-05-21] stage 7: split monolith into package (deferred #5)

`pipeline/stage7_load.py` → `pipeline/stage7_load/` package. Public API (`load_candidate_persons`) preserved via `__init__.py` re-export. Moved helpers to `helpers.py`, audit helper to `audit.py`, person loader to `persons.py`. Prerequisite for Phase 2's per-kind loaders (events, places, states, relations).

Articles touched: none (pure refactor; no behaviour change).

## [2026-05-21] stage 1: ingest_documents returns actual insert count (deferred #3)

`pipeline/stage1_ingest.py::ingest_dongzhoulieguozhi` now sums `cursor.rowcount` per row instead of returning `len(rows)`. Changed from `executemany` to per-row `execute` to count inserts properly. Re-ingesting an existing chapter now correctly reports 0 inserts. Test `test_ingest_returns_actual_insert_count_not_input_length` added.

`no knowledge impact: clarifies return-value semantics; behavior is preserved for first-run callers (count matches len(rows)) but now correctly reports 0 on re-ingest of existing rows.`

## [2026-05-21] stage 2: chunking edge-case tests (deferred #9)

Added two regression tests in `tests/unit/test_stage2_chunk.py`:
- `test_empty_paragraphs_are_skipped` — empty paragraphs (from `\n\n\n` runs) don't produce empty chunks.
- `test_oversized_single_paragraph_emits_one_chunk` — paragraphs larger than the target chunk size still emit exactly one chunk; v1 chunker doesn't split mid-paragraph.

Articles touched: none (test-only; behavior already correct).

## [2026-05-21] stage 2: _PARA_SEP regex accepts single-newline paragraphs (deferred #1)

Changed `pipeline/stage2_chunk.py::_PARA_SEP` from `r"\r?\n\s*\r?\n+"` to `r"\r?\n+"`. Upstream 东周列国志 JSON uses single `\n` between paragraphs; the previous regex required blank-line separators and silently collapsed each chapter into one ~5KB chunk. Added regression test `test_chunks_emerge_from_single_newline_separated_paragraphs`. Re-chunked the corpus: chunk count went from 108 (one per chapter) to 606.

Articles touched: `concepts/pipeline/architecture.md` (chunking section).

Append-only chronological log of significant changes to this project. Each entry records what changed, why, and which articles were touched. Read sequentially, this log tells the story of the project's decisions.

## [2026-05-20] docs: add thin Streamlit curation app article

Created `knowledge/concepts/curation/streamlit-app.md` — the article referenced by `curation/**/*.py` in the CLAUDE.md article-mapping table. Documents the three review queues, home screen v1 design, audit/reversibility contract, and Phase 1 status (placeholder only). Without this article the drift-check would fail on the first Phase 2 commit touching `curation/`.

Articles created: `concepts/curation/streamlit-app.md` (new). Articles updated: `knowledge/index.md` (curation section added).

## [2026-05-20] fix(stage7): JSON-aware equality for *_json fields in merge

Added `_scalars_equal(field, old_val, new_val)` to `stage7_load.py`. For fields ending in `_json`, it deserializes both values before comparison so that two JSON strings with the same content but different key orderings are treated as equal. `_merge_scalar_fields` uses `_scalars_equal` instead of bare `==`. Prevents spurious Conflict records from repeated extractions where LLM output key order is non-deterministic.

Articles updated: `concepts/pipeline/load-and-merge.md` (skip-if-equal rule updated), `concepts/verification/testing.md` (new test documented).

## [2026-05-20] fix(stage7): use per-field confidence (audit_log lookup) for merge decisions

Added `_last_field_confidence` helper to `stage7_load.py`. `_merge_scalar_fields` now looks up the most recent `set`-event confidence for each field from `audit_log` before deciding whether to update or conflict. Row-level `persons.confidence` is used as fallback only when no prior set-event exists. Prevents a high-confidence field value from being overwritten by a lower-confidence extraction in a later run that compares against the stale creation-time confidence.

Articles updated: `concepts/pipeline/load-and-merge.md` (per-field confidence lookup documented), `concepts/verification/testing.md` (new test documented).

## [2026-05-20] fix(stage9): dynamic table enumeration in _count_rows

Replaced the hardcoded `_CANONICAL_TABLES` constant in `stage9_export.py` with dynamic `sqlite_master` enumeration in `_count_rows`. The snapshot already strips `candidate_*` and `llm_cache`, so dynamic enumeration is equivalent and stays correct as new canonical tables are added. `_CANONICAL_TABLES` removed.

Articles updated: `concepts/pipeline/export-contract.md` (`_count_rows` dynamic enumeration section added).

## [2026-05-20] fix(stage7): add hash-suffix collision guard to Person id slugs

Added a slug-collision guard in `load_candidate_persons`: after computing `per:<slug>`, the loader checks whether that id is already held by a *different* Person. If so, a 6-char SHA-256 suffix derived from `canonical_name` is appended (`per:<slug>-<hash6>`). Prevents `PRIMARY KEY` crash when two distinct names share the same slug.

Articles updated: `concepts/pipeline/load-and-merge.md` (slug collision rule documented).

## [2026-05-20] living-docs: seed first 3 north-star articles (greenfield)

Seeded the knowledge base with three thin "north star" articles capturing the load-bearing decisions made before any code is written. Source of truth for these decisions is `docs/superpowers/specs/2026-05-20-changjuan-design.md`; the articles distill the design spec into durable per-concept references that the same-task rule can attach to as code lands.

Articles created:

- `concepts/data-model/knowledge-graph.md` — the six-entity model (Person, State, Place, Event, Citation, Conflict) + structured Date + Person name variants + citation on every relation. `Family` deferred to `person_relations(kind="clan_member")`.
- `concepts/pipeline/architecture.md` — the 9-stage sequential ETL and the load-bearing principle: automation produces a complete usable graph without curation; curation is retrospective, never a gate.
- `concepts/verification/confidence-and-invariants.md` — confidence is a deterministic computed score (not LLM self-report); two-layer extraction invariant with honest framing of per-field-justification (gameable, generation-time nudge) vs. sampling QA (the real backstop).

Anchor questions: not re-asked. All anchors were resolved during the design-spec brainstorm earlier in the session — audience, source coupling, primary reader-view metaphor, map style, data strategy, MVP scope, tech stack — see `docs/superpowers/specs/2026-05-20-changjuan-design.md` §1 and Non-goals subsection.

Decisions still pending (deferred deliberately; see spec Non-goals & deliberate omissions):

- LLM provider/model choice (recommendation: Claude Sonnet for stages 3/5, Opus for stage 6).
- Reign-table source (recommendation: bundled JSON from 杨伯峻 chronology).
- 左传 / 史记 source edition (recommendation: ctext.org, archived at a known SHA).
- Place coordinates source (recommendation: CHGIS + fallback geocode).
- Golden-chapter selection (recommendation: Ch. 1 + Ch. ~40).
- Promotion of `Family` to a first-class entity (after golden-chapter pass tells us).

`affects:` globs are deliberately empty on all three articles — code does not yet exist. The same-task rule will attach globs as files land.

## [2026-05-20] tooling: linting + type-checking + hooks

Added ruff (linter + formatter), mypy (strict type-checking), pre-commit hooks for ruff/mypy. No knowledge articles changed yet — this is pure tooling, no behaviour, model, or architecture.

Also converted the broad natural-language CLAUDE.md mapping row for "Date type / inference_kind / reign-table normalization" to a glob pattern (`pipeline/**/date*.py` etc.) to eliminate false-positive drift-check matches from tooling files (validate_articles.py, scripts/validate-articles) that contain the word "date" in a frontmatter-validation context.

`no knowledge impact: tooling only.`

## [2026-05-20] living-docs: adopted methodology via installer

Ran `install.sh` from `mpklu/living-doc`. Greenfield templates installed:

- `CLAUDE.md` filled in with project-specific content (project description, file layout, article-mapping table tailored to the planned `pipeline/`, `curation/`, `corpora/`, `data/` boundaries).
- `knowledge/{index.md, log.md, concepts/, connections/}`, `schemas/article-frontmatter.schema.json`, `scripts/{drift-check, validate-articles}`, `actions/drift-check/*`, `.pre-commit-config.yaml`.
- `LIVING_DOCS_FIRST_PROMPT.md` consumed and to be deleted on commit.

## [2026-05-20] pipeline: Config dataclass for paths and tunables

Added `pipeline.config.Config` — a frozen dataclass that centralizes repo paths, data-dir paths, and chunking tunables (`chunk_target_chars=1800`, `chunk_overlap_chars=200`). Future stages read from this rather than hardcoding paths.

Articles touched: `concepts/pipeline/architecture.md` (added `affects: [pipeline/config.py]`); also created `concepts/verification/testing.md` because the CLAUDE.md article-mapping table requires a test-conventions article for any change touching `tests/**/*.py` (the `tests/unit/test_config.py` added in this task triggered the same-task rule). The new article documents pytest as the only runner, `tmp_path` for unit tests, `@pytest.mark.integration` for golden-chapter tests, and `[mypy-tests.*]` loose typing. `knowledge/index.md` updated to list the new article.

## [2026-05-20] fix(pipeline): apply_schema thin wrapper; test fixture uses IF NOT EXISTS

Removed the silent `OperationalError` catch from `apply_schema`. The function is now a thin `executescript` + `commit` wrapper; idempotency is the DDL script's responsibility (via `IF NOT EXISTS`). Updated `tests/unit/test_db.py`'s `SCHEMA_SQL` fixture to use `CREATE TABLE IF NOT EXISTS` to match. No change to observable behaviour for compliant DDL; non-compliant DDL will now surface errors rather than silently swallowing them.

`concepts/verification/testing.md` is unaffected — test conventions (pytest, `tmp_path`, markers, conftest) are unchanged. The `SCHEMA_SQL` fixture update is a correctness fix, not a convention change.

## [2026-05-20] pipeline: SQLite helpers (db.py)

Added `pipeline.db.connect` (context-manager: foreign_keys ON, WAL on, Row factory) and `pipeline.db.apply_schema` (idempotent DDL via `executescript`). All future stages use these rather than calling sqlite3 directly.

Also added `tests/conftest.py` with the `tmp_db_dir` shared fixture (an empty directory with a `data/` subdirectory, available to all test modules). Updated `concepts/verification/testing.md` to note that shared fixtures live in `tests/conftest.py`.

Articles touched: none yet (db.py is utility; will be referenced by article `affects:` globs once stages 1/7/9 land). `concepts/verification/testing.md` updated to document the conftest.py fixture layer.

## [2026-05-20] schema: corpus.sqlite (documents, chunks, citations)

Created the immutable source-side schema: `documents` (one per chapter), `chunks` (paragraph-aware splits with overlap), `citations` (verbatim quote spans). Foreign keys on `chunks.document_id` and `citations.chunk_id` enforced; `UNIQUE (corpus, chapter_num)` prevents accidental double-ingest. WAL mode and PRAGMA foreign_keys=ON by way of `pipeline.db.connect`.

Articles touched: `concepts/data-model/knowledge-graph.md` (+ affects glob for the schema file).

## [2026-05-20] stage 2: paragraph-aware chunking with overlap

Implemented `pipeline.stage2_chunk.chunk_documents`. Chunks accumulate paragraphs up to `chunk_target_chars` (default 1800), then start a new chunk that overlaps the prior chunk's tail by ~`chunk_overlap_chars` (default 200) characters. No chunk splits a paragraph mid-text. Chunk ids are deterministic `chk:<doc_id>:<paragraph_start>` so citations stay stable across re-runs. SHA-256 (first 16 chars) on chunk text in `hash` for LLM-cache keying in Phase 2.

Articles touched: `concepts/pipeline/architecture.md` (+ stage2_chunk.py to affects).

## [2026-05-20] stage 1: 108-chapter sanity test wired up

Added a guard test that ingests the real upstream 东周列国志 (via the `corpora/dongzhoulieguozhi` symlink) and asserts exactly 108 chapter rows land. Skipped automatically if the corpus symlink is missing. This is our canary: when upstream changes shape, this fires before silent data loss.

`no knowledge impact: same affects glob (pipeline/stage1_ingest.py).`

## [2026-05-20] stage 1: ingest 东周列国志 from JSON

Implemented `pipeline.stage1_ingest.ingest_dongzhoulieguozhi`: reads the upstream `dongzhoulieguozhi/json/东周列国志.json`, inserts one row per chapter into `corpus.sqlite.documents` with stable id `dzl:<n>`. Idempotent via ON CONFLICT DO NOTHING on `(corpus, chapter_num)`.

Articles touched: `concepts/pipeline/architecture.md` (added `pipeline/stage1_ingest.py` to affects); `concepts/verification/testing.md` (added "Synthetic corpus helpers" section documenting the `_make_fake_corpus` pattern used in stage tests).

## [2026-05-20] schema: changjuan.sqlite — entity + relation tables

Added entity tables (persons, person_variants, states, state_capitals, places, events) and relation tables (event_participants, event_places, event_relations, person_relations, person_states, entity_citations) per spec §5. `person_relations.kind` includes `clan_member` — the deferred-Family lever. Every row carries `confidence`, `provenance ∈ {auto, curated}`, `pipeline_run_id` for traceability.

Articles touched: `concepts/data-model/knowledge-graph.md` (+ canonical_schema.sql to affects); `concepts/verification/testing.md` (+ canonical schema tests section).

## [2026-05-20] schema: changjuan.sqlite — candidate, bookkeeping, field_history view

Added candidate_* staging tables (per spec §7 — re-extraction safety), bookkeeping (conflicts, audit_log with the {value, confidence} field-level shape, pipeline_runs with stats_schema_version, llm_cache, merge_candidates, qa_samples), and the `field_history` view that reconstructs per-field history from audit_log without a redundant JSON blob on entity rows. Index on `audit_log(entity_kind, entity_id, field)` keeps the view fast.

Articles touched: `concepts/data-model/knowledge-graph.md` (no glob change — same file).

## [2026-05-20] data-model: reign table + dates-and-reigns article

Bundled `pipeline/reign_table.json` with 鲁 and 周 chronologies for the Spring-Autumn period. Created `concepts/data-model/dates-and-reigns.md` as a separate article from the knowledge-graph article — the date model is intricate enough (six `inference_kind` values, reign-year arithmetic) to warrant its own durable explanation.

Articles created: `concepts/data-model/dates-and-reigns.md`. `concepts/verification/testing.md` updated to document `test_reign_table.py`.

## [2026-05-20] dates: explicit_reign_lu parser (pipeline/dates.py created)

Created `pipeline/dates.py` with `parse_date(original: str) -> DateDict`. Task 12 implements `explicit_reign_lu` only. `DateDict` is a `TypedDict` with fields `year_bce`, `uncertainty`, `year_bce_end?`, `original`, `era`, `inference_kind`. Subsequent tasks extend `parse_date` in-place.

Articles touched: `concepts/data-model/dates-and-reigns.md` (added `parse_date` surface section); `concepts/verification/testing.md` (added date parser tests section).

## [2026-05-20] dates: explicit_reign_zhou parser

Extended `parse_date` with `_try_zhou` handling `周X王N年` for all 13 tabulated Zhou kings (平王 through 敬王, 770–476 BCE). Refactored Lu logic into `_try_lu` helper returning `DateDict | None`.

Articles touched: `concepts/data-model/dates-and-reigns.md` (Zhou parser surface note); `concepts/verification/testing.md` (Zhou test note).

## [2026-05-20] dates: era_only ranges + unknown fallback

Extended `parse_date` with `_try_era` (ten era patterns covering 春秋/战国 sub-periods) and `_unknown` fallback. `parse_date` no longer raises `NotImplementedError` — unrecognized inputs return `inference_kind="unknown"`, `year_bce=None`. Note: the plan's test assertion `500 <= year_bce <= 480` for 春秋末 was a typo (the chained comparison is impossible); corrected to `476 <= year_bce <= 510` (matching the configured range midpoint 493).

Articles touched: `concepts/data-model/dates-and-reigns.md` (updated dispatch order, never-raises contract); `concepts/verification/testing.md` (era/unknown test notes).

## [2026-05-20] dates: all six inference_kinds parseable

`pipeline.dates.parse_date(original, anchor=None)` now handles all five non-`explicit_reign_other` kinds: explicit_reign_lu, explicit_reign_zhou, relative_to_prior_event (其年/明年/次年/去年/前年/是岁/是年/是+season), era_only (春秋初/中/末/晚期 + 战国初/中/末/晚期), unknown (fallback). `explicit_reign_other` remains deferred until a non-鲁/非周 reign citation appears that needs deterministic resolution.

Articles touched: `concepts/data-model/dates-and-reigns.md` (updated signature, added `_try_relative` to dispatch order); `concepts/verification/testing.md` (relative-reference test pattern note).

## [2026-05-20] stage4: normalize_date_string wrapper returning JSON

Created `pipeline/stage4_normalize.py` with `normalize_date_string(original, anchor_json=None) -> str` — thin wrapper over `pipeline.dates.parse_date` that serializes the result as JSON. Stages 3/5/7 call this to produce values for `*_date_json` columns.

Articles touched: `concepts/pipeline/architecture.md` (added Stage 4 normalize section, added pipeline/stage4_normalize.py to affects glob); `concepts/verification/testing.md` (added stage4 normalize test section).

## [2026-05-20] stage 7: variant-aware Person matching

`_find_existing_person` now consults both `persons.canonical_name` and `person_variants.variant` when looking up an existing Person to match. The match-by-variant path correctly resolves `'晋文公'` to a Person whose canonical_name is `'重耳'` if that variant is registered. Scalar merge runs on matched-existing-Person path.

Articles touched: `concepts/pipeline/architecture.md` (+ stage7_load.py to affects); `concepts/pipeline/load-and-merge.md` (frontmatter updated to reflect Task 20 implementation).

## [2026-05-20] stage 7: scalar merge + Conflict emission

Implemented `_merge_scalar_fields` per spec §7: skip None, skip equal, fill-from-None, never-overwrite-curated, higher-confidence-wins-by-margin (`_SIMILAR_CONFIDENCE_DELTA = 0.1`), otherwise emit Conflict. `_emit_conflict` records both variants with `current_best_variant_idx` set to the higher-confidence one and `resolution_rule='highest_confidence'`.

Articles touched: `concepts/pipeline/load-and-merge.md` (frontmatter updated to reflect Task 19 implementation).

## [2026-05-20] stage 9: export bundle + round-trip test

`pipeline.stage9_export.export_bundle(src, out, version=...)` produces `out/manifest.json` and `out/changjuan.sqlite`. The snapshot is built by copy-then-drop: `candidate_*` tables and `llm_cache` are stripped via `name LIKE 'candidate_%'` enumeration (fail-loud if a future schema change adds a candidate table — no allowlist to forget). Manifest carries `version`, `schema_version`, `generated_at`, per-table counts, and source-corpus editions pulled from `corpus.sqlite.documents.source_edition`. Round-trip test confirms canonical rows survive intact.

Articles touched: `concepts/pipeline/architecture.md` (+ stage9_export.py to affects). Cross-reference from `export-contract.md` already created in Task 21.

## [2026-05-20] stage 9: round-trip test (Task 23)

Added `test_export_roundtrip_preserves_canonical_data`: seeds 2 Persons (auto + curated) and 1 Event, calls `export_bundle`, opens the snapshot with a raw `sqlite3.connect` handle, asserts row ids and provenance values survive intact, and confirms manifest counts match. This is the canonical regression target for stage 9.

Articles touched: `concepts/verification/testing.md` (Task 23 round-trip test description added).

## [2026-05-20] stage 9: strip-candidate-tables + llm_cache tests (Task 22)

Added `test_export_strips_all_candidate_tables` (seeds a `candidate_persons` row, exports, asserts zero `candidate_*` tables in snapshot) and `test_export_strips_llm_cache` (asserts `llm_cache` absent from snapshot). Both pass with the Task 21 implementation — the tests document the stripping contract explicitly.

Articles touched: `concepts/verification/testing.md` (no new section needed; Task 21 log entry already covers the stage 9 test file).

## [2026-05-20] stage 9: export bundle (manifest + canonical-only sqlite snapshot)

Created `pipeline/stage9_export.py` and `concepts/pipeline/export-contract.md`. `export_bundle(src, out, version=...)` produces `out/changjuan.sqlite` (copy-then-drop snapshot) and `out/manifest.json` (version, schema_version=1, generated_at ISO 8601 UTC, per-table counts, source_corpus_editions). `candidate_*` tables and `llm_cache` are stripped dynamically via `name LIKE 'candidate_%'` enumeration — fail-loud design, no hardcoded allowlist to forget. No denormalized JSON files in v1.

Articles created: `concepts/pipeline/export-contract.md` (new — describes snapshot strategy, manifest contents, candidate_* prefix stripping, schema_version v1).

## [2026-05-20] Phase 1 complete — deterministic foundation in place

The full deterministic ETL skeleton wires end-to-end. `tests/integration/test_roundtrip.py` exercises: ingest → chunk → seed synthetic candidates → load (with field-level merge semantics) → export (manifest + canonical-only snapshot). The pipeline is ready for stage 3 (LLM extraction) in Phase 2.

Tables in `changjuan.sqlite`: persons, person_variants, states, state_capitals, places, events, event_participants, event_places, event_relations, person_relations, person_states, entity_citations, candidate_* (9 staging tables), conflicts, audit_log, pipeline_runs, llm_cache, merge_candidates, qa_samples. Plus the `field_history` view.

CLI verbs working: `changjuan ingest`, `changjuan chunk`, `changjuan load <pipeline_run_id>`, `changjuan export <version>`.

Articles updated this phase: knowledge-graph.md, architecture.md, dates-and-reigns.md (new), cli.md (new), with affects globs covering every file in `pipeline/`.

Next phase: golden-chapter annotation + stage 3 extraction prompt + LLM client + sampling QA harness.

## [2026-05-20] cli: typer-based CLI scaffold (ingest/chunk/load/export)

Added `pipeline/cli.py` with four subcommands via `typer.Typer()`. Each command takes `--repo-root` for non-cwd execution. `ingest` exits 1 with a clear message when the corpus file is absent. `load` requires a `pipeline_run_id` positional so promotion is always scoped to a specific run. `export` requires a `version` positional.

Why separate subcommands over a single `run` command: the stage-checkpointed model benefits from independent re-runnable steps. A mega-command would hide per-stage cost profiles and make resumption harder.

Articles created: `concepts/runtime/cli.md` (new — describes all four subcommands, design rationale, first commitments). Articles touched: `knowledge/index.md` (added runtime section).

## [2026-05-20] pipeline: LLM cache primitives (Phase 1 stub)

Added `pipeline/llm_cache.py` with `cache_key`, `put`, and `get`. Phase 1 builds the cache primitives without any LLM client — they operate against the `llm_cache` table created by `CANONICAL_SCHEMA`. `cache_key` produces a stable SHA-256 hex digest keyed by `(model, prompt_template_version, normalized_request_json)`. `put` inserts with `ON CONFLICT (key_hash) DO NOTHING`. `get` returns the deserialized response dict or `None` on miss. Phase 2 (stage 3 extraction) wires these around its LLM calls.

Articles touched: `concepts/verification/testing.md` (added LLM cache tests section).

## [2026-05-20] stage 7: match candidates against existing Persons by canonical_name

Refactored `load_candidate_persons` to look up existing canonical Persons before creating. Two candidates with the same `canonical_name` now resolve to one Person (the second is a no-op for fields; Task 19 adds the actual scalar-merge logic). Introduced `_create_person` and `_audit` helpers — replaces the inline INSERT+audit code from Task 17.

Articles touched: `concepts/pipeline/load-and-merge.md` (matching by canonical_name documented in existing article).

## [2026-05-20] stage 7: simple create path (candidate_persons → persons)

Created `pipeline/stage7_load.py` with `load_candidate_persons(conn, pipeline_run_id)`. Task 17 implements the naive create path: every candidate_persons row for the given run becomes a new canonical Person with id `per:<slug>` (slug from `_slugify`, which applies regex `[^\w]+`→`-`). Collision on id gets a uuid hex suffix. Audit log row emitted with `change_kind='create'`, `actor='load@v1'`. Returns count of candidates processed.

Articles created: `concepts/pipeline/load-and-merge.md` (new — describes matching, merge semantics, Conflict emission, variant union, provenance rules). Articles touched: `concepts/verification/testing.md` (added stage 7 load test section).

## [2026-05-21] golden ch01: hand-annotated YAML for Western Zhou collapse + annotation helpers

Hand-annotated `tests/golden/ch01/*.yaml` over the now-correctly-chunked Chapter 1
of 东周列国志. Final counts:

- persons: 13 (9 named + 4 unnamed-but-acting via `per:_<descriptor>-ch01` ids)
- events: 14 (excluding the commented-out 东郊游猎 — see README rationale)
- places: 8
- states: 4 (周 + 姜戎 + 犬戎 + 晋)
- citations: 46 (all span-verified against `data/corpus.sqlite` via NFC substring match)
- relations: 63 (event_participant + event_place + person_relation + person_state + state_capital)

Annotation conventions + 14 substantive judgment-call entries (scope rules,
date strategy, chunk-choice rule, span workflow, variant folding, place
geocoding, quote selection, relation coverage strategy) recorded in
`tests/golden/ch01/README.md`'s decisions log. These will be harvested into
`changjuan-extract`'s system prompt during Task 27.

Phase 2 reality: variants of the same person (e.g., 女婴 ↔ later-named 褒姒,
重耳 ↔ 晋文公 etc.) stay as separate `per:*` ids; stage-5 linker (Phase 3)
will merge.

Also committed: four annotation-helper scripts used during this pass:

- `scripts/read-chapter` — dumps a chapter's chunks as readable Markdown.
- `scripts/find-span` — one-shot (chunk_id, quote) → `[start, end]` lookup.
- `scripts/fill-spans` — bulk fills missing span fields in citations YAML
  (or extraction YAML, auto-detected); prompts on in-chunk ambiguity.
- `scripts/validate-golden` — runs the structural loader + corpus-side
  chunk_id / span / quote alignment checks.

These will be reused for future chapters' golden annotation passes and (the
extract-format mode of fill-spans) by the `changjuan-extract` skill at runtime.

Articles touched: none (annotation data + helper scripts; conventions
documented in tests/golden/ch01/README.md).
