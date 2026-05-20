---
title: Testing conventions, golden chapters, and fixtures
type: concept
area: verification
updated: 2026-05-20
status: current
load_bearing: false
references:
  - concepts/pipeline/architecture.md
affects:
  - tests/**/*.py
---

## What this is

Tests live under `tests/` in two layers:

- **`tests/unit/`** — fast, isolated tests for individual modules. No filesystem side-effects beyond `tmp_path`. No LLM calls.
- **`tests/integration/`** — end-to-end tests that run one or more pipeline stages against a golden chapter fixture and assert on the output database.

## Test conventions

- **Pytest** is the only test runner.
- Unit tests use `tmp_path` (pytest built-in) for any path-dependent logic. They never read from `data/` or `corpora/`.
- Integration tests are gated behind a marker (`@pytest.mark.integration`) and are excluded from the default `pytest` run; they require the golden-chapter fixture to be present under `tests/fixtures/`.
- All test files are typed loosely (`[mypy-tests.*]` override in `mypy.ini` sets `disallow_untyped_defs = false`).

## Golden chapters

A "golden chapter" is a small, representative excerpt of the primary corpus used to validate extraction and linking stages end-to-end. The recommended chapters are Ch. 1 (ingest baseline) and Ch. ~40 (mid-corpus with multiple states and persons). Fixtures are stored under `tests/fixtures/` and are committed; they are never regenerated automatically.

## Shared fixtures

Shared pytest fixtures live in `tests/conftest.py`. Currently provides `tmp_db_dir` — an empty `tmp_path`-based directory with a `data/` subdirectory, suitable for ad-hoc SQLite database tests.

## DDL fixtures

Test modules that exercise `apply_schema` must supply DDL using `CREATE TABLE IF NOT EXISTS` (not bare `CREATE TABLE`). `apply_schema` is a thin wrapper around `executescript` — it does not suppress `OperationalError`; idempotency is the DDL script's responsibility. Using `IF NOT EXISTS` in test DDL mirrors exactly how every real Phase 1 schema (`pipeline/schemas/*.sql`) is written.

## Schema-application tests

Tests in `tests/unit/test_corpus_schema.py` verify that `CORPUS_SCHEMA` (imported from `pipeline.schemas`) creates the expected tables (`documents`, `chunks`, `citations`), is idempotent under double-apply, and that `documents` has the required columns. These tests use `tmp_path` with `connect()` + `apply_schema()` directly — no fixtures beyond pytest built-ins.

## Synthetic corpus helpers

Stage tests that require real-looking source files (e.g., ingest stages that read from `corpora/`) use `_make_fake_corpus`-style helper functions defined at module level in each test file. These helpers write minimal JSON or text fixtures into `tmp_path`-based directories and return the synthesized path. They live in the test module rather than `conftest.py` because they are corpus-specific, not shared across tests.

## Real-corpus smoke tests

Real-corpus smoke tests use `@pytest.mark.skipif` against the `corpora/` symlink so they are silently skipped when the upstream corpus is not present locally.

Chunking tests use a `_seed_doc` helper to insert minimal `documents` rows into a `tmp_path`-based database before exercising `chunk_documents`.

## Canonical schema tests

Tests in `tests/unit/test_canonical_schema.py` verify that `CANONICAL_SCHEMA` creates all entity and relation tables (Task 9), all candidate and bookkeeping tables plus the `field_history` view (Task 10), and that `person_relations.kind` accepts `clan_member` without a constraint violation. The `test_audit_log_field_history_query` test inserts a field-level `audit_log` row and reads it back through the `field_history` view, asserting the `{value, confidence}` extraction is correct.

## Date parser tests

`tests/unit/test_dates.py` exercises `pipeline.dates.parse_date`. Tests use direct string input — no fixtures beyond the imported function. The `@pytest.mark.parametrize` decorator covers lenient-prefix variants (`鲁僖二十八年`, `僖公二十八年`). New tasks append to this file as new `inference_kind` values are implemented. Zhou-king tests assert both the `year_bce` value and `inference_kind == "explicit_reign_zhou"`. Era-only tests assert `uncertainty == "range"` and that `year_bce` falls within the era's expected range. The unknown-passthrough test asserts `year_bce is None` and `inference_kind == "unknown"` — confirming `parse_date` never raises for unrecognized input. Relative-reference tests build an `anchor` by first calling `parse_date` on a known date string, then pass it to the second call; without anchor, the test confirms the relative form falls through to `unknown`.

## Stage 4 normalize tests

`tests/unit/test_stage4_normalize.py` verifies `normalize_date_string` returns valid JSON with the correct `year_bce` and `inference_kind` fields for the canonical anchor case (鲁僖公二十八年 → 632 BCE). This is the integration point between `pipeline.dates` and the `*_date_json` columns.

## Reign table tests

`tests/unit/test_reign_table.py` loads `pipeline/reign_table.json` directly via `Path(__file__).resolve().parents[2]` and asserts that the anchor cases resolve correctly (鲁隐公元年 = 722 BCE, 鲁僖公二十八年 = 632 BCE, 周平王元年 = 770 BCE). This file carries no SQLite or pipeline fixtures — it reads only the bundled JSON.

## What would invalidate this article

- Adding a second test runner.
- Changing the golden-chapter selection criteria.
- Moving fixtures out of `tests/fixtures/`.
- Changing `apply_schema`'s idempotency contract (currently delegated to DDL).
