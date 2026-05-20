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

## [2026-05-20] stage 1: ingest 东周列国志 from JSON

Implemented `pipeline.stage1_ingest.ingest_dongzhoulieguozhi`: reads the upstream `dongzhoulieguozhi/json/东周列国志.json`, inserts one row per chapter into `corpus.sqlite.documents` with stable id `dzl:<n>`. Idempotent via ON CONFLICT DO NOTHING on `(corpus, chapter_num)`.

Articles touched: `concepts/pipeline/architecture.md` (added `pipeline/stage1_ingest.py` to affects); `concepts/verification/testing.md` (added "Synthetic corpus helpers" section documenting the `_make_fake_corpus` pattern used in stage tests).
