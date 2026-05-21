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

`tests/unit/test_dates.py` exercises `pipeline.dates.parse_date` and the `DateDict` TypedDict. Tests use direct string input — no fixtures beyond the imported function. The `@pytest.mark.parametrize` decorator covers lenient-prefix variants (`鲁僖二十八年`, `僖公二十八年`). New tasks append to this file as new `inference_kind` values are implemented. Zhou-king tests assert both the `year_bce` value and `inference_kind == "explicit_reign_zhou"`. Era-only tests assert `uncertainty == "range"` and that `year_bce` falls within the era's expected range. The unknown-passthrough test asserts `year_bce is None` and `inference_kind == "unknown"` — confirming `parse_date` never raises for unrecognized input. Relative-reference tests build an `anchor` by first calling `parse_date` on a known date string, then pass it to the second call; without anchor, the test confirms the relative form falls through to `unknown`. Task 13 adds `test_datedict_accepts_relative_anchor_event_id` — a schema-level test that constructs a DateDict literal with the optional `relative_anchor_event_id` field and asserts it round-trips; this guards the type-level addition against accidental regression (e.g., by mypy during future refactoring).

## Stage 4 normalize tests

`tests/unit/test_stage4_normalize.py` verifies `normalize_date_string` returns valid JSON with the correct `year_bce` and `inference_kind` fields for the canonical anchor case (鲁僖公二十八年 → 632 BCE). This is the integration point between `pipeline.dates` and the `*_date_json` columns.

## Reign table tests

`tests/unit/test_reign_table.py` loads `pipeline/reign_table.json` directly via `Path(__file__).resolve().parents[2]` and asserts that the anchor cases resolve correctly (鲁隐公元年 = 722 BCE, 鲁僖公二十八年 = 632 BCE, 周平王元年 = 770 BCE). This file carries no SQLite or pipeline fixtures — it reads only the bundled JSON.

## Stage 7 load tests

`tests/unit/test_stage7_load_persons.py` exercises `pipeline.stage7_load.load_candidate_persons`. Tests seed `candidate_persons` rows directly into a `tmp_path`-based database, call `load_candidate_persons`, then query `persons` and `audit_log` to assert outcomes. Task 17 adds basic create-path tests; Task 18 adds the dedup-by-name test (`test_load_matches_existing_person_by_canonical_name` — loads twice with the same `canonical_name`, asserts `len(persons) == 1`). Task 19 adds three scalar-merge and Conflict-emission tests: `test_load_updates_scalar_when_new_confidence_higher` (fill-from-None path), `test_load_does_not_overwrite_curated` (curated-never-overwritten, asserts `len(conflicts) == 1`), and `test_load_emits_conflict_on_disagreement_at_similar_confidence` (similar-confidence path, checks both variants in `variants_json`). Task 20 adds `test_load_unions_name_variants`: pre-seeds a `person_variants` row mapping `晋文公` → `per:zhong-er`, then loads a candidate with `canonical_name='晋文公'`, and asserts `len(persons) == 1` (no duplicate created). The merge-regression tests (Tasks 18–20) form a suite that guards against silent duplicates, curated-overwrite bugs, and missed variant resolution. Phase 1 code-review adds `test_load_slug_collision_guard`: pre-seeds `per:foo` with `canonical_name='alpha'`, then loads a candidate with `canonical_name='foo'` (slug also `'foo'`), asserts the second Person gets id `per:foo-<hash6>` and no crash occurs. Also adds `test_merge_uses_per_field_confidence_from_audit_log`: a 3-run scenario (Run1 creates at 0.5; Run2 sets gender='M' at 0.9; Run3 proposes gender='F' at 0.7) that asserts gender remains 'M' and a Conflict is emitted — verifying `_last_field_confidence` is used instead of the stale row-level confidence. Also adds `test_merge_json_field_same_content_different_key_order_no_conflict`: pre-seeds a Person with `birth_date_json='{"year_bce": 632, "uncertainty": "point"}'`, then loads a candidate with the same JSON in different key order; asserts no Conflict and no `set` audit-log event — verifying `_scalars_equal` does semantic JSON comparison.

## Stage 7 citation accumulation tests

`tests/unit/test_stage7_citations.py` exercises the `entity_citations` accumulation behavior added in Phase 2 Task 5. Three tests: `test_first_load_writes_one_entity_citations_row` (load one candidate, assert one `entity_citations` row with `entity_kind='person'` and `citation_id == chunk_id`), `test_reload_accumulates_citations` (same `canonical_name`, two different `chunk_id` values across two runs, assert one Person and two `entity_citations` rows), and `test_same_citation_twice_is_idempotent` (load same candidate twice, assert still one row — verifying `INSERT OR IGNORE` idempotence). Tests seed `candidate_persons` directly via `connect`/`apply_schema` pattern, identical to the stage 7 load tests.

## Confidence scorer stub tests

`tests/unit/test_confidence.py` exercises `pipeline.confidence.score_extraction_record` (Phase 2 Task 11). Four tests: `test_base_score_with_minimal_input` (empty quote → base 0.7), `test_score_never_exceeds_ceiling` (long quote + complete justifications → score capped at 0.95), `test_longer_citation_increases_score` (quote length bonus — score(50-char) > score(1-char)), and `test_complete_justifications_increase_score` (all scalar fields justified → bonus +0.10). Tests use direct function calls with hand-constructed record dicts matching the stage-3 output schema. The scoring function is deterministic with no side-effects, so no fixtures or temporary paths are needed.

## Stage 9 export tests

`tests/unit/test_stage9_export.py` exercises `pipeline.stage9_export.export_bundle`. Task 21 adds two baseline tests: `test_export_creates_manifest_and_sqlite` (seeds one Person, exports, asserts `manifest.json` and `changjuan.sqlite` exist, manifest `version` and `counts["persons"]==1`) and `test_export_snapshot_is_readable_sqlite` (asserts the snapshot opens as SQLite and contains the `persons` table). Task 22 adds `test_export_strips_all_candidate_tables` (seeds a `candidate_persons` row, exports, asserts no `candidate_*` tables in snapshot — documents the fail-loud stripping contract) and `test_export_strips_llm_cache` (asserts `llm_cache` is absent from snapshot — documents the implementation-detail exclusion). Task 23 adds `test_export_roundtrip_preserves_canonical_data` (seeds 2 Persons with different provenances + 1 Event, exports, opens snapshot with a fresh `sqlite3.connect` handle — no pipeline helpers — checks row ids and provenance values, and confirms manifest `counts["persons"]==2` and `counts["events"]==1` agree with snapshot reality). This is the canonical round-trip regression test for stage 9.

## CLI tests

`tests/unit/test_cli.py` exercises `pipeline.cli` via `typer.testing.CliRunner`. Three tests: `test_cli_has_ingest_chunk_load_export_commands` (invokes `app --help`, asserts exit 0, asserts all four subcommand names appear in stdout), `test_cli_ingest_dry_runs` (invokes `ingest --repo-root <empty-tmp-dir>`, asserts exit code in `{0, 1}` and no `Traceback` in stdout — the empty-dir case must exit cleanly with an error message, not crash), and `test_cli_load_wires_all_five_entity_kinds` (Phase 2 Task 20 — integration test verifying the load command dispatches to all five loaders; seeds one candidate each of places, states, persons, events; invokes load; asserts all five canonical tables receive rows). These tests use `typer.testing.CliRunner` so no subprocess is spawned and `monkeypatch.chdir` can be used safely.

## list-unresolved-dates / resolve-relative-date CLI tests

`tests/unit/test_resolve_relative_date_cli.py` (Phase 2 Task 15) exercises the two curator triage verbs added to `pipeline.cli`. A `_seed` helper creates a minimal canonical database with one anchored event (`evt:anchor`, `year_bce=771`) and one unresolved relative event (`evt:rel`, `year_bce=null`, `inference_kind='relative_to_prior_event'`, `original='明年'`). Four tests:

- `test_list_unresolved_shows_dangling_relatives` — invokes `list-unresolved-dates`; asserts `evt:rel` appears in stdout and `evt:anchor` does not.
- `test_resolve_relative_date_sets_anchor_and_recomputes` — invokes `resolve-relative-date` with `evt:anchor` as anchor; asserts `year_bce` updates to 770 (771 − 1), `relative_anchor_event_id` is set, and exactly one `audit_log` row with `actor LIKE 'curator:%'` exists.
- `test_resolve_with_explicit_offset_unknown_token` — updates `original` to `'其后五年'` (not in `_RELATIVE_OFFSETS`), invokes with `--offset 5`; asserts `year_bce == 766` (771 − 5).
- `test_resolve_dangling_anchor_errors` — passes `--anchor-event-id evt:nope`; asserts non-zero exit code and "not found" or "dangling" in output.

These tests also exercise `pipeline.db.open_canonical_db` and `open_corpus_db` — the convenience helpers that apply the schema and return a bare `sqlite3.Connection`.

## LLM cache tests

`tests/unit/test_llm_cache.py` exercises `pipeline.llm_cache` — the Phase 1 cache primitives that Phase 2 will wire around LLM calls. Three tests: `test_cache_key_is_stable` (same inputs produce the same SHA-256 hex key; differing `prompt_template_version` produces a different key), `test_put_then_get_roundtrip` (put a response under a key, retrieve it, assert round-trip fidelity), and `test_get_miss_returns_none` (key absent → `get` returns `None`). No LLM client is involved; these tests work entirely against the `llm_cache` SQLite table created by `CANONICAL_SCHEMA`.

## Golden YAML loader tests

`tests/unit/test_golden_loader.py` exercises `tests.golden.loader.load_golden`. Seven tests: `test_loads_valid_golden_set` (happy path — minimal valid YAML set for a chapter, asserts correct entity counts), `test_rejects_dangling_citation_reference` (person references a citation id that doesn't exist in citations.yaml → `GoldenLoadError`), `test_rejects_missing_required_field` (person missing `canonical_name` → `GoldenLoadError`), `test_rejects_unknown_inference_kind` (event date with an unrecognized `inference_kind` value → `GoldenLoadError`), `test_rejects_relative_anchor_cycle` (two events whose `relative_anchor_event_id` values form a cycle → `GoldenLoadError`), `test_accepts_valid_social_category` (person with `social_category: official` → field returned verbatim), `test_rejects_invalid_social_category` (person with `social_category: wizard` → `GoldenLoadError` matching "social_category"). Tests use `tmp_path`-based `golden_dir` fixture writing minimal YAML files. The loader validates `social_category` against `_VALID_SOCIAL_CATEGORIES` (frozenset of 11 values). The loader itself lives in `tests/golden/loader.py` — it is test infrastructure, not part of the pipeline package.

## Precision/Recall harness tests

`tests/unit/test_precision_recall.py` exercises `tests.golden.precision_recall.compute_pr`. Seven tests: `test_person_p_r_with_perfect_match` (single person in golden and candidates — both precision and recall are 1.0), `test_person_recall_drops_when_missing` (two in golden, one in candidates — recall 0.5, fn 1), `test_person_precision_drops_with_extras` (one in golden, two in candidates — precision 0.5, fp 1), `test_event_matches_on_type_year_and_place` (exact event match — precision 1.0), `test_event_year_within_one_year_counts_as_match` (year off by one — tp 1), `test_person_match_blocked_by_social_category_mismatch` (golden has `noble`, candidate has `royalty` — tp 0, fp 1, fn 1), `test_person_match_ignores_missing_social_category` (golden has no `social_category`, candidate has `royalty` — tp 1, match not blocked). The `_person_match` function checks `social_category` agreement only when both sides have it set. The harness lives in `tests/golden/precision_recall.py`; it is test infrastructure, not part of the pipeline package.

## Phase 1 round-trip integration test

`tests/integration/test_roundtrip.py` is the regression target for the full Phase 1 deterministic pipeline. `test_phase1_roundtrip` walks all four stages against a synthetic 1-chapter corpus: (1) ingest a single-chapter JSON into `corpus.sqlite`, (2) chunk the document, (3) seed a `candidate_persons` row directly and call `load_candidate_persons`, (4) call `export_bundle`. Assertions: `manifest["counts"]["persons"] == 1`, `audit_log` key present in counts, no `candidate_*` tables in snapshot, canonical Person's `canonical_name == "重耳"`. This test uses direct function calls (not the CLI) so it validates the pipeline layer, not the CLI layer. It lives in `tests/integration/` and is collected by default (no marker required in Phase 1).

## Extraction-output schema tests

`tests/unit/test_extract_output_schema.py` exercises `pipeline.schemas.extract_output.EXTRACT_OUTPUT_SCHEMA` and the `PROMPT_TEMPLATE_VERSION` constant. Eight tests: `test_minimal_valid_passes` (minimal payload with one person, empty lists for other entities — asserts jsonschema validates without error); `test_missing_top_level_required_fails` (deletes `events` key — asserts `ValidationError`); `test_person_missing_citation_fails` (deletes `citation` from a person entry — asserts `ValidationError`); `test_event_with_date_inference_kind_validated` (appends an event with a valid `inference_kind="explicit_reign_zhou"` — asserts validates); `test_event_with_invalid_inference_kind_fails` (appends an event with `inference_kind="bogus"` — asserts `ValidationError`); `test_prompt_template_version_constant_exists` (asserts `PROMPT_TEMPLATE_VERSION` starts with `"v"`); `test_person_accepts_valid_social_category` (sets `social_category="royalty"` on a person — asserts validates); `test_person_rejects_invalid_social_category` (sets `social_category="wizard"` — asserts `ValidationError`). Tests use `jsonschema.validate` directly with no database or filesystem fixtures.

## Phase 2 constants tests

`tests/unit/test_config.py::test_phase2_constants_exist` (Task 12) validates that Phase 2 configuration constants are present and have correct types and ranges: `EXTRACTION_DIR` is a string; `QA_SAMPLE_FRACTION` and `QA_MISMATCH_THRESHOLD` are in (0, 1); `QA_SAMPLE_FLOOR < QA_SAMPLE_CEILING`; and all five entity kinds in `GOLDEN_PR_THRESHOLDS` (person, event, place, state, relation) have precision and recall values in (0, 1]. This guards against typos in constant names and ensures the threshold structure is valid before the constants are read by stage-3 extraction (Task 22), sampling QA (Task 31), and the golden-eval CLI (Task 29).

## resolve_relative_dates tests

`tests/unit/test_dates_relative.py` (Phase 2 Task 14) exercises
`pipeline.dates.resolve_relative_dates` and `RelativeResolveError`. Six tests:
`test_within_chunk_walkback_resolves` (e1 has year 771, e2 "明年" resolves to 770
via rolling anchor); `test_cascading_relatives` (three records — first anchored,
second and third each "明年" step forward: 771 → 770 → 769);
`test_no_prior_anchor_leaves_null_and_reduces_confidence` (no prior anchor — year_bce
stays None); `test_explicit_anchor_overrides_walkback` (relative_anchor_event_id points
to a fake_lookup returning year 600 — result is 599, not the walkback target 770);
`test_dangling_anchor_raises` (fake_lookup returns None — RelativeResolveError matching
"dangling"); `test_anchor_cycle_raises` (e1 anchors to itself — RelativeResolveError
matching "cycle"). A private `_date()` helper extracts and asserts-isinstance the nested
`date` sub-dict to satisfy mypy strict without cluttering every assertion.

## Stage 7 load_candidate_states tests

`tests/unit/test_stage7_load_states.py` (Phase 2 Task 17) exercises `pipeline.stage7_load.load_candidate_states`. A `_seed_candidate_state` helper inserts a minimal `candidate_states` row (using `chunk_id`/`quote` columns matching the canonical schema). Three tests:

- `test_creates_canonical_state_on_first_load` — seeds one candidate, calls `load_candidate_states`, asserts one `states` row with the correct name.
- `test_second_load_with_same_name_merges_not_creates` — two runs with the same name, second adds `ruling_clan='姬'`; asserts exactly one `states` row and two `entity_citations` rows.
- `test_higher_confidence_field_overrides_lower` — first run sets `ruling_clan='姒'` at confidence 0.7; second run proposes `ruling_clan='姬'` at confidence 0.9 (delta 0.2 > threshold 0.1); asserts `ruling_clan` updates to `'姬'`.

These tests guard the name-match, null-fill, and higher-confidence-override paths for states. The `canonical` fixture uses `open_canonical_db` with `tmp_path`, identical to the places tests pattern.

## Stage 7 load_candidate_places tests

`tests/unit/test_stage7_load_places.py` (Phase 2 Task 16) exercises `pipeline.stage7_load.load_candidate_places`. A `_seed_candidate_place` helper inserts a minimal `candidate_places` row (using `chunk_id`/`quote` columns matching the canonical schema). Three tests:

- `test_creates_canonical_place_on_first_load` — seeds one candidate, calls `load_candidate_places`, asserts one `places` row with the correct name.
- `test_second_load_with_same_name_merges_not_creates` — two runs with the same name, second adds `lat=34.5`; asserts exactly one `places` row and two `entity_citations` rows (citation accumulation from both chunk_ids).
- `test_higher_confidence_lat_overrides_lower` — first run sets `lat=34.0` at confidence 0.7; second run proposes `lat=34.5` at confidence 0.9 (delta 0.2 > threshold 0.1); asserts `lat` updates to 34.5.

These tests guard the name-match, null-fill, and higher-confidence-override paths for places. The `canonical` fixture uses `open_canonical_db` with `tmp_path`, identical to the persons tests pattern.

## Stage 7 helpers tests

`tests/unit/test_stage7_helpers.py` (Phase 2 Task 18) exercises `pipeline.stage7_load.helpers.merge_date_field` in isolation. Four tests:

- `test_merge_date_field_point_beats_range_at_lower_confidence` — a range-precision date at confidence 0.9 vs a point-precision date at confidence 0.85; asserts the point date wins (spec §7.2 more-precise-wins rule).
- `test_merge_date_field_higher_confidence_wins_when_precision_same` — two point dates at confidence 0.7 vs 0.85; asserts the higher-confidence entry wins.
- `test_merge_date_field_returns_other_when_one_is_none` — one `None` argument; asserts the non-None entry is returned regardless of which side is None.
- `test_merge_date_field_tie_keeps_current` — same precision, same confidence; asserts current is returned (tie → keep existing).

These tests use no fixtures — just direct function calls with hand-constructed dicts.

## Stage 7 load_candidate_events tests

`tests/unit/test_stage7_load_events.py` (Phase 2 Task 18) exercises `pipeline.stage7_load.load_candidate_events`. A `_seed_candidate_event` helper inserts a minimal `candidate_events` row (using `chunk_id`/`quote` matching the canonical schema). `primary_place_id` defaults to `None` to avoid FK constraint failures (the events table references `places(id)`). Four tests:

- `test_creates_canonical_event_on_first_load` — seeds one candidate, calls `load_candidate_events`, asserts one `events` row and the correct `type`.
- `test_same_match_key_collapses` — two runs with the same `(type, year_bce, primary_place_id)` key, second adds `outcome='晋胜'`; asserts exactly one `events` row with `outcome` filled in via null-fill merge.
- `test_date_merge_point_beats_range` — first run seeds `uncertainty='range'` at confidence 0.9; second run seeds `uncertainty='point'` at confidence 0.85; asserts the canonical `date_json` has `uncertainty='point'` (more-precise wins).
- `test_conflict_emitted_on_scalar_disagreement` — `outcome='晋胜'` at confidence 0.9 vs `outcome='楚胜'` at confidence 0.88 (delta 0.02 < threshold 0.1); asserts at least one `conflicts` row with `subject_kind='event'` and `field='outcome'`.

The `canonical` fixture uses `open_canonical_db` with `tmp_path`, identical to the places/states tests pattern.

## Stage 7 load_candidate_relations tests

`tests/unit/test_stage7_load_relations.py` (Phase 2 Task 19) exercises `pipeline.stage7_load.load_candidate_relations` across all six relation kinds. A `_seed_entities` helper inserts minimal canonical persons/events/places/states so FK constraints pass. Per-kind seed helpers use `INSERT OR REPLACE` so the same composite key can be re-seeded with a new `pipeline_run_id` for idempotence tests. Twelve tests:

- `test_event_participant_first_load_creates_row` — seeds one `candidate_event_participants` row, calls `load_candidate_relations`, asserts one `event_participants` row.
- `test_event_participant_idempotence_accumulates_citations` — same tuple key seeded under `run:1` then `run:2`; asserts one canonical row + two `entity_citations` rows with `entity_kind='event_participant'`.
- `test_event_place_first_load_creates_row` — same pattern for `event_places`.
- `test_event_place_idempotence_accumulates_citations` — dedup + citation accumulation for event_places.
- `test_event_relation_first_load_creates_row` — same pattern for `event_relations`.
- `test_event_relation_idempotence_accumulates_citations` — dedup + citation accumulation for event_relations.
- `test_person_relation_first_load_creates_row` — same pattern for `person_relations`.
- `test_person_relation_idempotence_accumulates_citations` — dedup + citation accumulation for person_relations.
- `test_person_relation_contradictory_directionality_emits_conflict` — `(per:a, per:b, killed_by)` then `(per:b, per:a, killed_by)`; asserts both rows exist + one `conflicts` row with `subject_kind='person_relation'` and `field='directionality'`.
- `test_person_state_first_load_creates_row` — same pattern for `person_states`.
- `test_person_state_idempotence_accumulates_citations` — dedup + citation accumulation for person_states.
- `test_state_capitals_stub_returns_zero` — `load_candidate_relations` returns 0 and `state_capitals` stays empty (stub; no `candidate_state_capitals` staging table exists).

The `canonical` fixture uses `open_canonical_db` with `tmp_path`. The `entity_citations` CHECK constraint was extended (Task 19) to allow all six relation kinds alongside the four entity kinds.

## What would invalidate this article

- Adding a second test runner.
- Changing the golden-chapter selection criteria.
- Moving fixtures out of `tests/fixtures/`.
- Changing `apply_schema`'s idempotency contract (currently delegated to DDL).
