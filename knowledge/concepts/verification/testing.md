---
title: Testing conventions, golden chapters, and fixtures
type: concept
area: verification
updated: 2026-05-21
status: mature
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

A "golden chapter" is a small, representative excerpt of the primary corpus used to validate extraction and linking stages end-to-end. The recommended chapters are Ch. 1 (ingest baseline) and Ch. ~40 (mid-corpus with multiple states and persons). Fixtures are stored under `tests/golden/` and are committed; they are never regenerated automatically. Each chapter gets a subdirectory with a `README.md` documenting the annotation conventions (stable IDs, variant formats, date structure, event criteria) and decisions made during hand annotation.

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

Chunking tests use a `_seed_doc` helper to insert minimal `documents` rows into a `tmp_path`-based database before exercising `chunk_documents`. The test `test_chunks_emerge_from_single_newline_separated_paragraphs` is a targeted regression for the `_PARA_SEP` regex: it seeds 4 single-`\n`-separated paragraphs with a `chunk_target_chars` smaller than one paragraph, then asserts more than one chunk is produced — which only passes when the regex correctly splits on single newlines. This guards against re-introducing the blank-line-required regex that silently collapsed each chapter into one chunk.

## Canonical schema tests

Tests in `tests/unit/test_canonical_schema.py` verify that `CANONICAL_SCHEMA` creates all entity and relation tables (Task 9), all candidate and bookkeeping tables plus the `field_history` view (Task 10), and that `person_relations.kind` accepts `clan_member` without a constraint violation. The `test_audit_log_field_history_query` test inserts a field-level `audit_log` row and reads it back through the `field_history` view, asserting the `{value, confidence}` extraction is correct.

## Date parser tests

`tests/unit/test_dates.py` exercises `pipeline.dates.parse_date`. Tests use direct string input — no fixtures beyond the imported function. The `@pytest.mark.parametrize` decorator covers lenient-prefix variants (`鲁僖二十八年`, `僖公二十八年`). New tasks append to this file as new `inference_kind` values are implemented. Zhou-king tests assert both the `year_bce` value and `inference_kind == "explicit_reign_zhou"`. Era-only tests assert `uncertainty == "range"` and that `year_bce` falls within the era's expected range. The unknown-passthrough test asserts `year_bce is None` and `inference_kind == "unknown"` — confirming `parse_date` never raises for unrecognized input. Relative-reference tests build an `anchor` by first calling `parse_date` on a known date string, then pass it to the second call; without anchor, the test confirms the relative form falls through to `unknown`.

## Stage 4 normalize tests

`tests/unit/test_stage4_normalize.py` verifies `normalize_date_string` returns valid JSON with the correct `year_bce` and `inference_kind` fields for the canonical anchor case (鲁僖公二十八年 → 632 BCE). This is the integration point between `pipeline.dates` and the `*_date_json` columns.

## Reign table tests

`tests/unit/test_reign_table.py` loads `pipeline/reign_table.json` directly via `Path(__file__).resolve().parents[2]` and asserts that the anchor cases resolve correctly (鲁隐公元年 = 722 BCE, 鲁僖公二十八年 = 632 BCE, 周平王元年 = 770 BCE). This file carries no SQLite or pipeline fixtures — it reads only the bundled JSON.

## Stage 7 load tests

`tests/unit/test_stage7_load_persons.py` exercises `pipeline.stage7_load.load_candidate_persons`. Tests seed `candidate_persons` rows directly into a `tmp_path`-based database, call `load_candidate_persons`, then query `persons` and `audit_log` to assert outcomes. Task 17 adds basic create-path tests; Task 18 adds the dedup-by-name test (`test_load_matches_existing_person_by_canonical_name` — loads twice with the same `canonical_name`, asserts `len(persons) == 1`). Task 19 adds three scalar-merge and Conflict-emission tests: `test_load_updates_scalar_when_new_confidence_higher` (fill-from-None path), `test_load_does_not_overwrite_curated` (curated-never-overwritten, asserts `len(conflicts) == 1`), and `test_load_emits_conflict_on_disagreement_at_similar_confidence` (similar-confidence path, checks both variants in `variants_json`). Task 20 adds `test_load_unions_name_variants`: pre-seeds a `person_variants` row mapping `晋文公` → `per:zhong-er`, then loads a candidate with `canonical_name='晋文公'`, and asserts `len(persons) == 1` (no duplicate created). The merge-regression tests (Tasks 18–20) form a suite that guards against silent duplicates, curated-overwrite bugs, and missed variant resolution. Phase 1 code-review adds `test_load_slug_collision_guard`: pre-seeds `per:foo` with `canonical_name='alpha'`, then loads a candidate with `canonical_name='foo'` (slug also `'foo'`), asserts the second Person gets id `per:foo-<hash6>` and no crash occurs. Also adds `test_merge_uses_per_field_confidence_from_audit_log`: a 3-run scenario (Run1 creates at 0.5; Run2 sets gender='M' at 0.9; Run3 proposes gender='F' at 0.7) that asserts gender remains 'M' and a Conflict is emitted — verifying `_last_field_confidence` is used instead of the stale row-level confidence. Also adds `test_merge_json_field_same_content_different_key_order_no_conflict`: pre-seeds a Person with `birth_date_json='{"year_bce": 632, "uncertainty": "point"}'`, then loads a candidate with the same JSON in different key order; asserts no Conflict and no `set` audit-log event — verifying `_scalars_equal` does semantic JSON comparison.

## Stage 7 citation accumulation tests

`tests/unit/test_stage7_citations.py` exercises the `entity_citations` accumulation behavior added in Phase 2 Task 5. Three tests: `test_first_load_writes_one_entity_citations_row` (load one candidate, assert one `entity_citations` row with `entity_kind='person'` and `citation_id == chunk_id`), `test_reload_accumulates_citations` (same `canonical_name`, two different `chunk_id` values across two runs, assert one Person and two `entity_citations` rows), and `test_same_citation_twice_is_idempotent` (load same candidate twice, assert still one row — verifying `INSERT OR IGNORE` idempotence). Tests seed `candidate_persons` directly via `connect`/`apply_schema` pattern, identical to the stage 7 load tests.

## Stage 9 export tests

`tests/unit/test_stage9_export.py` exercises `pipeline.stage9_export.export_bundle`. Task 21 adds two baseline tests: `test_export_creates_manifest_and_sqlite` (seeds one Person, exports, asserts `manifest.json` and `changjuan.sqlite` exist, manifest `version` and `counts["persons"]==1`) and `test_export_snapshot_is_readable_sqlite` (asserts the snapshot opens as SQLite and contains the `persons` table). Task 22 adds `test_export_strips_all_candidate_tables` (seeds a `candidate_persons` row, exports, asserts no `candidate_*` tables in snapshot — documents the fail-loud stripping contract) and `test_export_strips_llm_cache` (asserts `llm_cache` is absent from snapshot — documents the implementation-detail exclusion). Task 23 adds `test_export_roundtrip_preserves_canonical_data` (seeds 2 Persons with different provenances + 1 Event, exports, opens snapshot with a fresh `sqlite3.connect` handle — no pipeline helpers — checks row ids and provenance values, and confirms manifest `counts["persons"]==2` and `counts["events"]==1` agree with snapshot reality). This is the canonical round-trip regression test for stage 9.

## CLI tests

`tests/unit/test_cli.py` exercises `pipeline.cli` via `typer.testing.CliRunner`. Two tests: `test_cli_has_ingest_chunk_load_export_commands` (invokes `app --help`, asserts exit 0, asserts all four subcommand names appear in stdout) and `test_cli_ingest_dry_runs` (invokes `ingest --repo-root <empty-tmp-dir>`, asserts exit code in `{0, 1}` and no `Traceback` in stdout — the empty-dir case must exit cleanly with an error message, not crash). These tests use `typer.testing.CliRunner` so no subprocess is spawned and `monkeypatch.chdir` can be used safely.

## LLM cache tests

`tests/unit/test_llm_cache.py` exercises `pipeline.llm_cache` — the Phase 1 cache primitives that Phase 2 will wire around LLM calls. Three tests: `test_cache_key_is_stable` (same inputs produce the same SHA-256 hex key; differing `prompt_template_version` produces a different key), `test_put_then_get_roundtrip` (put a response under a key, retrieve it, assert round-trip fidelity), and `test_get_miss_returns_none` (key absent → `get` returns `None`). No LLM client is involved; these tests work entirely against the `llm_cache` SQLite table created by `CANONICAL_SCHEMA`.

## Golden YAML loader tests

`tests/unit/test_golden_loader.py` exercises `tests.golden.loader.load_golden`. Five tests: `test_loads_valid_golden_set` (happy path — minimal valid YAML set for a chapter, asserts correct entity counts), `test_rejects_dangling_citation_reference` (person references a citation id that doesn't exist in citations.yaml → `GoldenLoadError`), `test_rejects_missing_required_field` (person missing `canonical_name` → `GoldenLoadError`), `test_rejects_unknown_inference_kind` (event date with an unrecognized `inference_kind` value → `GoldenLoadError`), and `test_rejects_relative_anchor_cycle` (two events whose `relative_anchor_event_id` values form a cycle → `GoldenLoadError`). Tests use `tmp_path`-based `golden_dir` fixture writing minimal YAML files. The loader itself lives in `tests/golden/loader.py` — it is test infrastructure, not part of the pipeline package.

## Precision/Recall harness tests

`tests/unit/test_precision_recall.py` exercises `tests.golden.precision_recall.compute_pr`. Five tests: `test_person_p_r_with_perfect_match` (single person in golden and candidates — both precision and recall are 1.0), `test_person_recall_drops_when_missing` (two in golden, one in candidates — recall 0.5, fn 1), `test_person_precision_drops_with_extras` (one in golden, two in candidates — precision 0.5, fp 1), `test_event_matches_on_type_year_and_place` (exact event match — precision 1.0), `test_event_year_within_one_year_counts_as_match` (year off by one — tp 1). The harness lives in `tests/golden/precision_recall.py`; it is test infrastructure, not part of the pipeline package.

## Phase 1 round-trip integration test

`tests/integration/test_roundtrip.py` is the regression target for the full Phase 1 deterministic pipeline. `test_phase1_roundtrip` walks all four stages against a synthetic 1-chapter corpus: (1) ingest a single-chapter JSON into `corpus.sqlite`, (2) chunk the document, (3) seed a `candidate_persons` row directly and call `load_candidate_persons`, (4) call `export_bundle`. Assertions: `manifest["counts"]["persons"] == 1`, `audit_log` key present in counts, no `candidate_*` tables in snapshot, canonical Person's `canonical_name == "重耳"`. This test uses direct function calls (not the CLI) so it validates the pipeline layer, not the CLI layer. It lives in `tests/integration/` and is collected by default (no marker required in Phase 1).

## What would invalidate this article

- Adding a second test runner.
- Changing the golden-chapter selection criteria.
- Moving fixtures out of `tests/fixtures/`.
- Changing `apply_schema`'s idempotency contract (currently delegated to DDL).
