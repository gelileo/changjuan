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

## What would invalidate this article

- Adding a second test runner.
- Changing the golden-chapter selection criteria.
- Moving fixtures out of `tests/fixtures/`.
- Changing `apply_schema`'s idempotency contract (currently delegated to DDL).
