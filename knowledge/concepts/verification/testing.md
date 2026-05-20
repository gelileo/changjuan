---
title: Testing conventions, golden chapters, and fixtures
type: concept
area: verification
updated: 2026-05-20
status: thin
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

## What would invalidate this article

- Adding a second test runner.
- Changing the golden-chapter selection criteria.
- Moving fixtures out of `tests/fixtures/`.
