# Build Log

Append-only chronological log of significant changes to this project. Each entry records what changed, why, and which articles were touched. Read sequentially, this log tells the story of the project's decisions.

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

## [2026-05-20] pipeline: LLM cache primitives (Phase 1 stub)

Added `pipeline/llm_cache.py` with `cache_key`, `put`, and `get`. Phase 1 builds the cache primitives without any LLM client — they operate against the `llm_cache` table created by `CANONICAL_SCHEMA`. `cache_key` produces a stable SHA-256 hex digest keyed by `(model, prompt_template_version, normalized_request_json)`. `put` inserts with `ON CONFLICT (key_hash) DO NOTHING`. `get` returns the deserialized response dict or `None` on miss. Phase 2 (stage 3 extraction) wires these around its LLM calls.

Articles touched: `concepts/verification/testing.md` (added LLM cache tests section).

## [2026-05-20] stage 7: match candidates against existing Persons by canonical_name

Refactored `load_candidate_persons` to look up existing canonical Persons before creating. Two candidates with the same `canonical_name` now resolve to one Person (the second is a no-op for fields; Task 19 adds the actual scalar-merge logic). Introduced `_create_person` and `_audit` helpers — replaces the inline INSERT+audit code from Task 17.

Articles touched: `concepts/pipeline/load-and-merge.md` (matching by canonical_name documented in existing article).

## [2026-05-20] stage 7: simple create path (candidate_persons → persons)

Created `pipeline/stage7_load.py` with `load_candidate_persons(conn, pipeline_run_id)`. Task 17 implements the naive create path: every candidate_persons row for the given run becomes a new canonical Person with id `per:<slug>` (slug from `_slugify`, which applies regex `[^\w]+`→`-`). Collision on id gets a uuid hex suffix. Audit log row emitted with `change_kind='create'`, `actor='load@v1'`. Returns count of candidates processed.

Articles created: `concepts/pipeline/load-and-merge.md` (new — describes matching, merge semantics, Conflict emission, variant union, provenance rules). Articles touched: `concepts/verification/testing.md` (added stage 7 load test section).
