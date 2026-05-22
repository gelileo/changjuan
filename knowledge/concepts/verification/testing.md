---
title: Testing conventions, golden chapters, and fixtures
type: concept
area: verification
updated: 2026-05-21 (Task 8)
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

## Reign-year boundary tests

Phase 2 Task 35 adds three boundary regression tests for reign-year transitions (deferred item #2): `test_lu_xi_gong_33_resolves_to_627_bce` (鲁僖公33年 → 627 BCE, pinning the final year of 鲁僖公's reign), `test_lu_wen_gong_1_resolves_to_626_bce` (鲁文公元年 → 626 BCE, pinning the first year of 鲁文公's reign and the 元年 parsing), and `test_lu_zhuang_gong_32_resolves_to_662_bce` (鲁庄公32年 → 662 BCE, pinning the final year of 鲁庄公's reign). These tests use direct string input to `parse_date`; they verify that the bundled `pipeline/reign_table.json` has correct boundary years. All three tests passed against the existing reign table with no parser or data fixes required.

## Stage 4 normalize tests

`tests/unit/test_stage4_normalize.py` verifies `normalize_date_string` returns valid JSON with the correct `year_bce` and `inference_kind` fields for the canonical anchor case (鲁僖公二十八年 → 632 BCE). This is the integration point between `pipeline.dates` and the `*_date_json` columns.

## Reign table tests

`tests/unit/test_reign_table.py` loads `pipeline/reign_table.json` directly via `Path(__file__).resolve().parents[2]` and asserts that the anchor cases resolve correctly (鲁隐公元年 = 722 BCE, 鲁僖公二十八年 = 632 BCE, 周平王元年 = 770 BCE). This file carries no SQLite or pipeline fixtures — it reads only the bundled JSON.

## Stage 7 load tests

`tests/unit/test_stage7_load_persons.py` exercises `pipeline.stage7_load.load_candidate_persons`. Tests seed `candidate_persons` rows directly into a `tmp_path`-based database, call `load_candidate_persons`, then query `persons` and `audit_log` to assert outcomes. Task 17 adds basic create-path tests; Task 18 adds the dedup-by-name test (`test_load_matches_existing_person_by_canonical_name` — loads twice with the same `canonical_name`, asserts `len(persons) == 1`). Task 19 adds three scalar-merge and Conflict-emission tests: `test_load_updates_scalar_when_new_confidence_higher` (fill-from-None path), `test_load_does_not_overwrite_curated` (curated-never-overwritten, asserts `len(conflicts) == 1`), and `test_load_emits_conflict_on_disagreement_at_similar_confidence` (similar-confidence path, checks both variants in `variants_json`). Task 20 adds `test_load_unions_name_variants`: pre-seeds a `person_variants` row mapping `晋文公` → `per:zhong-er`, then loads a candidate with `canonical_name='晋文公'`, and asserts `len(persons) == 1` (no duplicate created). The merge-regression tests (Tasks 18–20) form a suite that guards against silent duplicates, curated-overwrite bugs, and missed variant resolution. Phase 1 code-review adds `test_load_slug_collision_guard`: pre-seeds `per:foo` with `canonical_name='alpha'`, then loads a candidate with `canonical_name='foo'` (slug also `'foo'`), asserts the second Person gets id `per:foo-<hash6>` and no crash occurs. Also adds `test_merge_uses_per_field_confidence_from_audit_log`: a 3-run scenario (Run1 creates at 0.5; Run2 sets gender='M' at 0.9; Run3 proposes gender='F' at 0.7) that asserts gender remains 'M' and a Conflict is emitted — verifying `_last_field_confidence` is used instead of the stale row-level confidence. Also adds `test_merge_json_field_same_content_different_key_order_no_conflict`: pre-seeds a Person with `birth_date_json='{"year_bce": 632, "uncertainty": "point"}'`, then loads a candidate with the same JSON in different key order; asserts no Conflict and no `set` audit-log event — verifying `_scalars_equal` does semantic JSON comparison. Task 36 (deferred #10) adds `test_load_updates_scalar_when_new_confidence_strictly_higher_by_delta`: a 2-scenario test exercising both branches of the `confidence > current + _SIMILAR_CONFIDENCE_DELTA` strict-greater check. Scenario 1: current=0.70, new=0.85 → 0.85 > 0.70 + 0.10 → gender updates to 'F'. Scenario 2: current=0.85 (after update), new=0.75 → 0.75 ≤ 0.85 + 0.10 → gender stays 'F' and Conflict is emitted. This test completes the scalar-merge branch coverage.

## Stage 7 citation accumulation tests

`tests/unit/test_stage7_citations.py` exercises the `entity_citations` accumulation behavior added in Phase 2 Task 5. Three tests: `test_first_load_writes_one_entity_citations_row` (load one candidate, assert one `entity_citations` row with `entity_kind='person'` and `citation_id == chunk_id`), `test_reload_accumulates_citations` (same `canonical_name`, two different `chunk_id` values across two runs, assert one Person and two `entity_citations` rows), and `test_same_citation_twice_is_idempotent` (load same candidate twice, assert still one row — verifying `INSERT OR IGNORE` idempotence). Tests seed `candidate_persons` directly via `connect`/`apply_schema` pattern, identical to the stage 7 load tests.

## Confidence scorer stub tests

`tests/unit/test_confidence.py` exercises `pipeline.confidence.score_extraction_record` (Phase 2 Task 11). Four tests: `test_base_score_with_minimal_input` (empty quote → base 0.7), `test_score_never_exceeds_ceiling` (long quote + complete justifications → score capped at 0.95), `test_longer_citation_increases_score` (quote length bonus — score(50-char) > score(1-char)), and `test_complete_justifications_increase_score` (all scalar fields justified → bonus +0.10). Tests use direct function calls with hand-constructed record dicts matching the stage-3 output schema. The scoring function is deterministic with no side-effects, so no fixtures or temporary paths are needed.

## Stage 9 export tests

`tests/unit/test_stage9_export.py` exercises `pipeline.stage9_export.export_bundle`. Task 21 adds two baseline tests: `test_export_creates_manifest_and_sqlite` (seeds one Person, exports, asserts `manifest.json` and `changjuan.sqlite` exist, manifest `version` and `counts["persons"]==1`) and `test_export_snapshot_is_readable_sqlite` (asserts the snapshot opens as SQLite and contains the `persons` table). Task 22 adds `test_export_strips_all_candidate_tables` (seeds a `candidate_persons` row, exports, asserts no `candidate_*` tables in snapshot — documents the fail-loud stripping contract) and `test_export_strips_llm_cache` (asserts `llm_cache` is absent from snapshot — documents the implementation-detail exclusion). Task 23 adds `test_export_roundtrip_preserves_canonical_data` (seeds 2 Persons with different provenances + 1 Event, exports, opens snapshot with a fresh `sqlite3.connect` handle — no pipeline helpers — checks row ids and provenance values, and confirms manifest `counts["persons"]==2` and `counts["events"]==1` agree with snapshot reality). This is the canonical round-trip regression test for stage 9.

## CLI tests

`tests/unit/test_cli.py` exercises `pipeline.cli` via `typer.testing.CliRunner`. Four tests: `test_cli_has_ingest_chunk_load_export_commands` (invokes `app --help`, asserts exit 0, asserts all four subcommand names appear in stdout), `test_cli_ingest_dry_runs` (invokes `ingest --repo-root <empty-tmp-dir>`, asserts exit code in `{0, 1}` and no `Traceback` in stdout — the empty-dir case must exit cleanly with an error message, not crash), `test_cli_load_wires_all_five_entity_kinds` (Phase 2 Task 20 — integration test verifying the load command dispatches to all five loaders; seeds one candidate each of places, states, persons, events; invokes load; asserts all five canonical tables receive rows), and `test_extract_load_cli_loads_yaml_via_cli` (Phase 2 Task 23 — end-to-end CLI test for the `extract-load` verb; creates minimal corpus and extraction YAML, invokes the verb with `--chapter`, `--extraction-file`, `--prompt-version`; asserts exit 0 and `"persons=1"` in stdout). These tests use `typer.testing.CliRunner` so no subprocess is spawned and `monkeypatch.chdir` can be used safely.

## list-unresolved-dates / resolve-relative-date CLI tests

`tests/unit/test_resolve_relative_date_cli.py` (Phase 2 Task 15) exercises the two curator triage verbs added to `pipeline.cli`. A `_seed` helper creates a minimal canonical database with one anchored event (`evt:anchor`, `year_bce=771`) and one unresolved relative event (`evt:rel`, `year_bce=null`, `inference_kind='relative_to_prior_event'`, `original='明年'`). Four tests:

- `test_list_unresolved_shows_dangling_relatives` — invokes `list-unresolved-dates`; asserts `evt:rel` appears in stdout and `evt:anchor` does not.
- `test_resolve_relative_date_sets_anchor_and_recomputes` — invokes `resolve-relative-date` with `evt:anchor` as anchor; asserts `year_bce` updates to 770 (771 − 1), `relative_anchor_event_id` is set, and exactly one `audit_log` row with `actor LIKE 'curator:%'` exists.
- `test_resolve_with_explicit_offset_unknown_token` — updates `original` to `'其后五年'` (not in `_RELATIVE_OFFSETS`), invokes with `--offset 5`; asserts `year_bce == 766` (771 − 5).
- `test_resolve_dangling_anchor_errors` — passes `--anchor-event-id evt:nope`; asserts non-zero exit code and "not found" or "dangling" in output.

These tests also exercise `pipeline.db.open_canonical_db` and `open_corpus_db` — the convenience helpers that apply the schema and return a `sqlite3.Connection` with `row_factory = sqlite3.Row` set (Task 38 fixed a missing `row_factory` assignment that caused dict-style column access to fail when using these helpers directly).

## LLM cache tests

`tests/unit/test_llm_cache.py` exercises `pipeline.llm_cache` — the Phase 1 cache primitives that Phase 2 will wire around LLM calls. Three tests: `test_cache_key_is_stable` (same inputs produce the same SHA-256 hex key; differing `prompt_template_version` produces a different key), `test_put_then_get_roundtrip` (put a response under a key, retrieve it, assert round-trip fidelity), and `test_get_miss_returns_none` (key absent → `get` returns `None`). No LLM client is involved; these tests work entirely against the `llm_cache` SQLite table created by `CANONICAL_SCHEMA`.

## Golden YAML loader tests

`tests/unit/test_golden_loader.py` exercises `tests.golden.loader.load_golden`. Seven tests: `test_loads_valid_golden_set` (happy path — minimal valid YAML set for a chapter, asserts correct entity counts), `test_rejects_dangling_citation_reference` (person references a citation id that doesn't exist in citations.yaml → `GoldenLoadError`), `test_rejects_missing_required_field` (person missing `canonical_name` → `GoldenLoadError`), `test_rejects_unknown_inference_kind` (event date with an unrecognized `inference_kind` value → `GoldenLoadError`), `test_rejects_relative_anchor_cycle` (two events whose `relative_anchor_event_id` values form a cycle → `GoldenLoadError`), `test_accepts_valid_social_category` (person with `social_category: official` → field returned verbatim), `test_rejects_invalid_social_category` (person with `social_category: wizard` → `GoldenLoadError` matching "social_category"). Tests use `tmp_path`-based `golden_dir` fixture writing minimal YAML files. The loader validates `social_category` against `_VALID_SOCIAL_CATEGORIES` (frozenset of 11 values). The loader itself lives in `tests/golden/loader.py` — it is test infrastructure, not part of the pipeline package.

## Precision/Recall harness tests

`tests/unit/test_precision_recall.py` exercises `tests.golden.precision_recall.compute_pr`. Thirteen tests: `test_person_p_r_with_perfect_match` (single person in golden and candidates — both precision and recall are 1.0), `test_person_recall_drops_when_missing` (two in golden, one in candidates — recall 0.5, fn 1), `test_person_precision_drops_with_extras` (one in golden, two in candidates — precision 0.5, fp 1), `test_event_matches_on_type_year_and_place` (exact event match — precision 1.0), `test_event_year_within_one_year_counts_as_match` (year off by one — tp 1), `test_person_match_blocked_by_social_category_mismatch` (golden has `noble`, candidate has `royalty` — tp 0, fp 1, fn 1), `test_person_match_ignores_missing_social_category` (golden has no `social_category`, candidate has `royalty` — tp 1, match not blocked), `test_person_match_with_chunk_local_state_id_resolves_via_lookup` (golden `sta:zhou` and candidate `s1` both resolve to `周` via their respective lookup maps — tp 1), `test_event_match_with_chunk_local_primary_place_id_resolves_via_lookup` (golden `pla:qian-mu` and candidate `pl1` both resolve to `千亩` — tp 1), `test_relation_match_with_id_resolution` (golden `evt:a`/`per:a` and candidate `e1`/`p1` resolve to matching names via lookup — tp 1), `test_event_match_year_alone_suffices_when_place_differs` (type+year match, place differs — tp 1; verifies relaxed Path C matcher), `test_event_match_place_alone_suffices_when_year_differs` (type+place match, year off by 11 — tp 1; verifies relaxed Path C matcher), `test_event_match_type_alone_does_not_suffice` (type matches but both year and place differ — tp 0; verifies the floor of the relaxed matcher).

The harness matchers are factory functions (not bare functions) that capture per-side name-lookup maps built from the `id`/`name` (or `id`/`canonical_name`) fields of both the golden and candidate entity lists. Cross-entity ID refs (state_id, primary_place_id, event_id, person_id, place_id) are translated to names before comparison; if an id is absent from the lookup it passes through unchanged (graceful degradation). This design bridges the canonical-style ids used in the golden (`sta:zhou`, `pla:qian-mu`, etc.) and the chunk-local ids emitted by the extraction skill (`s1`, `pl1`, etc.).

**Phase-2 event matcher (Task 29 Path C):** `_event_match_factory` was relaxed from "type AND year ±1 AND place" to "type AND (year ±1 OR place)". Type remains strict (semantic backbone). Year and place are treated as FK-ish corroborating signals; requiring both was too brittle for stage-3 candidates that haven't been linker-consolidated. With the relaxed matcher, Ch.1 v2 event P/R moved from 0.53/0.57 → 0.93/1.00.

The `golden_eval_cmd` in `pipeline/cli.py` builds candidate dicts that include an `id` field carrying the chunk-local suffix extracted from the row's full candidate id (`cand:per:run:xxx:p1` → `p1`). Relation FK columns (`candidate_event_id`, `candidate_person_id`, etc.) are similarly stripped to chunk-local suffix before being stored in the relation dict. This aligns the lookup keys across both sides.

The harness lives in `tests/golden/precision_recall.py`; it is test infrastructure, not part of the pipeline package.

## Re-extract accumulation integration tests

`tests/integration/test_re_extract_accumulates.py` (Phase 2 Task 38) exercises the full v1 → v2 re-extract flow synthetically (no LLM). Uses `open_corpus_db` / `open_canonical_db` with `tmp_path`. Four tests marked `@pytest.mark.integration`:

- `test_re_extract_accumulates_variants` — v1 adds variant `公子重耳`; v2 adds `晋公子`; asserts both appear in `person_variants` for the single canonical Person (exercises the variant-accumulation path added in Task 38).
- `test_re_extract_emits_conflict_on_scalar_disagreement` — v1 sets `clan_name='姬'`; v2 proposes `clan_name='姚'` at similar confidence; asserts at least one `conflicts` row with `field='clan_name'`.
- `test_re_extract_accumulates_citations` — two runs citing different chunks (`chk:1` / `chk:2`); asserts one canonical Person and `entity_citations` count ≥ 2. Uses a two-chunk corpus helper (`_seed_corpus_two_chunks`) because `entity_citations` is keyed on `(entity_kind, entity_id, citation_id)` — the same chunk cited twice is idempotent.
- `test_curated_field_not_silently_overwritten` — v1 creates Person with `clan_name='姬'`; curator sets `provenance='curated'`; v2 proposes `clan_name='姚'`; asserts `clan_name` remains `'姬'` (curated-never-overwritten invariant).

All four assertions passed without modifying stage 7 merge logic; only the variant-writing path (`_write_variants` in `persons.py`) and schema change (`candidate_persons.variants_json`) were new additions.

## Phase 1 round-trip integration test

`tests/integration/test_roundtrip.py` is the regression target for the full Phase 1 deterministic pipeline. `test_phase1_roundtrip` walks all four stages against a synthetic 1-chapter corpus: (1) ingest a single-chapter JSON into `corpus.sqlite`, (2) chunk the document, (3) seed a `candidate_persons` row directly and call `load_candidate_persons`, (4) call `export_bundle`. Assertions: `manifest["counts"]["persons"] == 1`, `audit_log` key present in counts, no `candidate_*` tables in snapshot, canonical Person's `canonical_name == "重耳"`. This test uses direct function calls (not the CLI) so it validates the pipeline layer, not the CLI layer. It lives in `tests/integration/` and is collected by default (no marker required in Phase 1).

## Extraction-output schema tests

`tests/unit/test_extract_output_schema.py` exercises `pipeline.schemas.extract_output.EXTRACT_OUTPUT_SCHEMA` and the `PROMPT_TEMPLATE_VERSION` constant. Eight tests: `test_minimal_valid_passes` (minimal payload with one person, empty lists for other entities — asserts jsonschema validates without error); `test_missing_top_level_required_fails` (deletes `events` key — asserts `ValidationError`); `test_person_missing_citation_fails` (deletes `citation` from a person entry — asserts `ValidationError`); `test_event_with_date_inference_kind_validated` (appends an event with a valid `inference_kind="explicit_reign_zhou"` — asserts validates); `test_event_with_invalid_inference_kind_fails` (appends an event with `inference_kind="bogus"` — asserts `ValidationError`); `test_prompt_template_version_constant_exists` (asserts `PROMPT_TEMPLATE_VERSION` starts with `"v"`); `test_person_accepts_valid_social_category` (sets `social_category="royalty"` on a person — asserts validates); `test_person_rejects_invalid_social_category` (sets `social_category="wizard"` — asserts `ValidationError`). Tests use `jsonschema.validate` directly with no database or filesystem fixtures.

## Phase 2 constants tests

`tests/unit/test_config.py::test_phase2_constants_exist` (Task 12) validates that Phase 2 configuration constants are present and have correct types and ranges: `EXTRACTION_DIR` is a string; `QA_SAMPLE_FRACTION` and `QA_MISMATCH_THRESHOLD` are in (0, 1); `QA_SAMPLE_FLOOR < QA_SAMPLE_CEILING`; and all five entity kinds in `GOLDEN_PR_THRESHOLDS` (person, event, place, state, relation) have precision and recall values in (0, 1]. This guards against typos in constant names and ensures the threshold structure is valid before the constants are read by stage-3 extraction (Task 22), sampling QA (Task 31), and the golden-eval CLI (Task 29).

## resolve_relative_dates tests

`tests/unit/test_dates_relative.py` (Phase 2 Task 14) exercises
`pipeline.dates.resolve_relative_dates` and `RelativeResolveError`. Six tests (Task 14):
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

Three additional tests (Task 29 v2 fix) cover the parenthesized-narrative-note convention:
`test_parenthesized_original_treated_as_same_year` (e2 `"(千亩之后)"` and e3
`"(料民回京时)"` both resolve to the same year as the prior anchor — offset=0);
`test_non_parenthesized_unknown_original_stays_null` (unrecognized non-paren token
`"某神秘时间"` leaves year_bce None — no silent date invention);
`test_empty_parens_stays_null` (`"()"` also leaves year_bce None — empty parens carry
no semantic signal). These guard `_offset_from_original`'s parenthesized-shorthand branch.

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

## Stage 3 extract-load tests

`tests/unit/test_extract_load.py` (Phase 2 Task 22) exercises `pipeline.stage3_extract.load_extraction` end-to-end. A shared `setup` fixture builds a minimal `corpus.sqlite` (one document, one chunk with text `'重耳奔狄'`) and an empty `changjuan.sqlite` using `open_corpus_db` / `open_canonical_db` with `tmp_path`. Three tests:

- `test_valid_extraction_loads_to_candidates` — minimal YAML with one person (`重耳`); asserts `persons_written == 1`, no violations, and a `candidate_persons` row with the correct `canonical_name`.
- `test_invalid_record_skipped` — person whose `citation.quote` (`不存在`) is not a substring of the chunk text; asserts `persons_written == 0` and `len(invariant_violations) == 1`.
- `test_loads_event_place_state_relation` — all five entity kinds plus one `event_participant` relation; asserts written counts are each ≥ 1 and `relations_written ≥ 1`.

The fixture uses corpus `'dongzhoulieguozhi'` (the CHECK constraint on `documents.corpus` prohibits the generic `'test'` value used in the spec sketch).

## Stage 3 invariant validator tests

`tests/unit/test_stage3_validator.py` (Phase 2 Task 21) exercises `pipeline.stage3_extract.validate_record` and `InvariantError`. Five tests cover the four static invariants:

- `test_verbatim_quote_passes_when_substring` — happy path; NFC-normalized `citation.quote` is a substring of `chunk.text`.
- `test_verbatim_quote_fails_when_not_substring` — quote not in chunk text → `InvariantError` matching `"verbatim"`.
- `test_justification_must_be_non_empty` — empty string in `justifications` dict → `InvariantError` matching `"justification"`.
- `test_justification_must_be_substring_of_quote` — justification present but not a substring of the quote → `InvariantError` matching `"justification"`.
- `test_chunk_id_mismatch_fails` — `citation.chunk_id` does not match the target chunk's `id` → `InvariantError` matching `"chunk_id"`.

Helper functions `_chunk` and `_person_record` produce minimal dicts; no fixtures or database are needed.

## Extract pre-flight tests

`tests/unit/test_extract_preflight.py` (Phase 2 Task 24) exercises `pipeline.cli.extract` — the non-LLM pre-flight verb. Three tests:

- `test_preflight_fails_when_no_corpus` — invokes `extract --chapter 1` against a `tmp_path` with only an empty `data/` dir; asserts non-zero exit and `✗` in stdout.
- `test_preflight_fails_when_chapter_has_no_chunks` — seeds an empty `corpus.sqlite` (schema applied, no rows); asserts non-zero exit and `✗` (chapter-chunks check fails).
- `test_preflight_passes_when_chunks_and_skill_present` — seeds `corpus.sqlite` with two chunks for chapter 1, creates a `.claude/skills/changjuan-extract/` directory with `SKILL.md`, `system-prompt.md`, and a `extraction-schema.yaml` generated via `yaml.safe_dump(EXTRACT_OUTPUT_SCHEMA)`; asserts exit 0, `✓` in stdout, and `/changjuan-extract` in stdout (skill invocation is printed). Uses `corpus = 'dongzhoulieguozhi'` to satisfy the `documents.corpus` CHECK constraint.

## re-extract CLI tests

`tests/unit/test_re_extract.py` (Phase 2 Task 28) exercises the `re-extract` subcommand via `typer.testing.CliRunner`. A `_seed_corpus_with_one_chunk` helper creates a minimal `corpus.sqlite` and `changjuan.sqlite` under `tmp_path/data/`. Two tests:

- `test_missing_extraction_file_instructs_user` — invokes `re-extract --chapter 1 --prompt-version v2` with no YAML file present; asserts non-zero exit code and that stdout contains both a "Invoke"/"Claude Code" guidance string and "changjuan-extract" (the skill name).
- `test_reload_when_file_exists` — seeds `data/extractions/ch01/extract-v1.yaml` with an empty-payload YAML; invokes `re-extract --chapter 1 --prompt-version v1`; asserts exit 0 (empty payload passes all invariants, zero records written).

Tests use `corpus = 'dongzhoulieguozhi'` to satisfy the `documents.corpus` CHECK constraint, matching the pattern established in `test_extract_load.py`.

## golden-eval CLI tests

`tests/unit/test_golden_eval_cli.py` (Phase 2 Task 29) exercises the `golden-eval` subcommand via `typer.testing.CliRunner`. A `_seed_minimal` helper creates minimal `corpus.sqlite` and `changjuan.sqlite` under `tmp_path/data/` and inserts one `pipeline_runs` row with `stage='extract-load'` and `scope_json.chapter=1`. A `_write_golden` helper writes a one-person golden set (one person `重耳`, one citation) into `tmp_path/tests/golden/ch01/`. Two tests:

- `test_golden_eval_with_no_candidates_reports_recall_zero` — invokes `golden-eval --chapter 1` with no candidate rows present; asserts non-zero exit and `✗` in stdout (person recall=0 below threshold).
- `test_golden_eval_with_matching_candidate_passes` — seeds a `candidate_persons` row with `canonical_name='重耳'` and `pipeline_run_id='run:test'`; invokes `golden-eval --chapter 1`; asserts exit 0 and `✓` in stdout (1/1 match; all other kinds empty→1.0).

These tests verify the verb's end-to-end path: `pipeline_runs` lookup → candidate-table queries → `compute_pr` → threshold gate → exit code.

## QA sampling tests

`tests/unit/test_qa_sampling.py` (Phase 2 Task 31) exercises `pipeline.qa_sampling.select_sample` — the deterministic 5% sampler for sampling QA. Five tests:

- `test_sample_is_deterministic_across_runs` — same input list produces identical output across two calls (hash-based membership is stable).
- `test_sample_size_approx_five_percent` — 1000-fact input yields 30–70 samples (5% ± jitter from hash distribution).
- `test_sample_floor_kicks_in_for_small_runs` — 100-fact input yields at least 30 samples (floor applies).
- `test_sample_ceiling_kicks_in_for_huge_runs` — 10000-fact input yields at most 250 samples (ceiling applies).
- `test_sample_floor_caps_at_input_size` — 10-fact input (below floor) yields all 10 samples (no padding).

A `_facts` helper builds minimal synthetic fact dicts with `pipeline_run_id`, `record_id`, and `field` keys. No fixtures or database are needed; tests call `select_sample` directly with hand-constructed inputs.

## QA CLI tests

`tests/unit/test_qa_cli.py` (Phase 2 Task 33) exercises the `qa-sample` and `qa-load` CLI verbs via `typer.testing.CliRunner`. A `_seed_corpus` helper creates minimal `corpus.sqlite` and `changjuan.sqlite` under `tmp_path/data/`. Three tests:

- `test_qa_sample_emits_yaml_with_triples` — seeds one `candidate_persons` row; invokes `qa-sample run:1`; asserts exit 0, stdout is valid YAML, and the list has at least one entry. Exercises the fallback path (candidate_facts unpopulated).
- `test_qa_load_writes_qa_samples_and_updates_stats` — seeds a `pipeline_runs` row; writes a 2-verdict YAML (`yes` + `no`); invokes `qa-load --run-id run:1 --qa-file <path>`; asserts exit 0, both `qa_samples` rows present, and `stats_json.claim_defensible_sample` has `sample_size=2`, `yes=1`, `no=1`.
- `test_qa_load_breaches_threshold_when_mismatch_high` — 4 `no` verdicts (mismatch_rate=1.0 > 0.10 threshold); asserts `stats_json.thresholds_breached` contains `"claim_defensible_mismatch_rate"`.

These tests confirm the full `qa-sample` → `qa-load` round-trip path: fact enumeration, YAML output, verdict ingestion, stats patching, and threshold breach detection.

## Golden Ch.1 P/R integration test

`tests/integration/test_golden_ch01.py` (Phase 2 Task 37) is the end-to-end gate test. It:

1. Copies `data/corpus.sqlite` into a `tmp_path` database (skips if absent — allows CI to run without the full corpus).
2. Calls `load_extraction` against `tests/fixtures/ch01-extraction-v1.yaml` (the frozen v2 extraction output, committed in `add4902`).
3. Builds candidate dicts via `_build_candidates`, which mirrors `golden_eval_cmd`'s SELECT logic using the actual canonical schema column names: `from_candidate_event_id`/`to_candidate_event_id` for `candidate_event_relations`, `from_candidate_person_id`/`to_candidate_person_id` for `candidate_person_relations`. Event-relation and person-relation rows store the `kind` column directly as the `"kind"` key in the relation dict (matching how `golden_eval_cmd` reads them).
4. Runs `compute_pr` against `tests/golden/ch01/`.
5. Asserts each kind's P/R meets `pipeline.config.GOLDEN_PR_THRESHOLDS`.

Marked `@pytest.mark.golden`. The fixture was frozen at the levels that satisfy the recalibrated thresholds — this test pins the relationship between the two so any future fixture replacement or threshold tighten will surface the regression.

## Merge regression loader tests

`tests/unit/test_regression_loader.py` (Phase 3 Task 3) exercises `tests.golden.regression_loader.load_regression_set` and `RegressionLoadError`. Seven tests: `test_loads_empty_set` (both top-level lists empty → returns dict with empty lists), `test_loads_populated_set` (one pair in each list → correct entity counts and field access), `test_rejects_missing_top_level_key` (absent `different_person_pairs` → `RegressionLoadError` matching the key name), `test_rejects_pair_missing_required_field` (pair without `rationale`/`source` → `RegressionLoadError` matching "rationale|source"), `test_rejects_pair_missing_person` (pair without `person_b` → `RegressionLoadError` matching "person_b"), `test_rejects_person_missing_canonical_name` (person dict without `canonical_name` → `RegressionLoadError` matching "canonical_name"), `test_rejects_invalid_social_category` (person with `social_category: wizard` → `RegressionLoadError` matching "social_category"). Tests use `tmp_path`-based `reg_dir` fixture writing minimal YAML files. The loader validates `social_category` against the same 11-value `_VALID_SOCIAL_CATEGORIES` frozenset used in `tests/golden/loader.py`. The loader itself lives in `tests/golden/regression_loader.py` — it is test infrastructure consumed by the Phase 3 linker regression test (Task 13), not part of the pipeline package.

## Phase 3 config constants test

`tests/unit/test_config.py::test_phase3_linker_thresholds_exist` (Phase 3 Task 5) validates that `LINKER_AUTO_MERGE_THRESHOLD` and `LINKER_QUEUE_THRESHOLD` are present in `pipeline.config`, are in `(0, 1]`, and satisfy `LINKER_QUEUE_THRESHOLD < LINKER_AUTO_MERGE_THRESHOLD`. Guards against typos in constant names and ensures the Stage 5 dispatch dial is correctly ordered before the linker (Tasks 7–8) reads these constants.

## Person match scorer tests

`tests/unit/test_scoring.py` (Phase 3 Task 6; corrected in Task 6 fix) exercises `pipeline.stage5_link.scoring.person_match_score` — the pure-function scorer at the heart of the Stage 5 linker. A `_p(name, **fields)` helper builds minimal Person record dicts. Eleven tests:

- `test_hard_veto_when_no_variant_overlap` — no shared names → score 0.0, `variant_overlap="none"`.
- `test_strong_variant_overlap_canonical_in_other_variants` — A's canonical appears in B's `variants[]` → `variant_overlap="strong"`, score 0.50 (no other signals).
- `test_partial_variant_overlap_non_canonical_match` — shared alias in both `variants[]` but neither canonical is the other's variant → `variant_overlap="partial"`, score 0.20.
- `test_full_perfect_match` — strong overlap + same state + same clan + same social category + temporal compatible → score 1.0 (clamped).
- `test_state_disagreement_subtracts` — strong overlap + different `state_id` → 0.50 − 0.40 = 0.10.
- `test_clan_disagreement_subtracts` — partial overlap + same state + different clan → 0.20 + 0.20 − 0.20 = 0.20.
- `test_temporal_conflict_subtracts` — strong overlap (A's canonical in B's `variants[]`) + temporal conflict (death 950 BCE, birth 700 BCE → gap 250 > 150) → 0.50 − 0.30 = 0.20.
- `test_one_null_does_not_penalize` — partial overlap + one side missing `state_id` → `state_agreement="one_null"`, no penalty, score 0.20.
- `test_score_clamps_to_zero` — partial overlap + state diff + clan diff + category diff + temporal conflict → heavily negative, clamped to 0.0.
- `test_temporal_compatible_with_partial_overlap_adds_independently` — partial overlap + same state + temporal compatible → 0.20 + 0.20 + 0.10 = 0.50. Verifies temporal applies regardless of overlap level (spec §4 regression walkthrough confirms this).
- `test_score_clamps_to_one` — strong overlap + all-same fields + compatible temporal → sum exceeds 1.0, clamped to 1.0.

Key formula invariant (spec §4): temporal bonus/penalty (+0.10 compatible, −0.30 conflict) is an **independent dimension** — it applies regardless of `variant_overlap` level. The §4 regression walkthrough (召公奭↔召虎: partial + state same + conflict = 0.20 + 0.20 − 0.30 = 0.10) confirms temporal is not gated on strong overlap.

## candidate_pool pre-filter tests (Phase 3 Task 7, hardened Task 7 fix)

`tests/unit/test_candidate_pool.py` exercises `pipeline.stage5_link.candidate_pool.candidate_pool(conn, candidate_id, pipeline_run_id)` — the SQL name-overlap pre-filter for the Stage 5 linker. Fixtures use `open_canonical_db(tmp_path / "changjuan.sqlite")` for a fresh in-memory-style SQLite. Two seeders (`_seed_candidate`, `_seed_canonical`) handle FK-safe insertion (state seeded before person when `state_id` is non-null). Seven tests (six original + one JSON-safety test added in Task 7 fix):

- `test_pool_includes_canonical_with_shared_canonical_name` — canonical and candidate share `canonical_name` "重耳" → pool includes the canonical, `target_kind == "canonical"`.
- `test_pool_includes_same_run_sibling_with_overlap` — two same-run candidates share a name → pool includes the sibling, `target_kind == "candidate"`.
- `test_pool_excludes_self` — the queried candidate never appears in its own pool.
- `test_pool_excludes_other_run_candidates` — a candidate from a different `pipeline_run_id` with the same name is excluded.
- `test_pool_excludes_no_overlap_canonical` — a canonical with a completely different name ("仲山甫") does not appear in the pool for "重耳".
- `test_pool_includes_variant_match` — a canonical named "晋文公" with a `person_variants` row linking it to variant "重耳" appears in the pool for a candidate named "重耳".
- `test_pool_handles_malformed_date_json` — a candidate whose `birth_date_json` is not valid JSON still appears in the pool with `birth_date=None` rather than crashing the linker. Covers `_safe_json_load`, which replaces bare `json.loads` in `_row_to_dict`.

## link_run orchestrator tests (Phase 3 Task 8)

`tests/unit/test_linker.py` exercises `pipeline.stage5_link.linker.link_run` — the Stage 5 dispatch orchestrator. Uses the same `open_canonical_db(tmp_path / "changjuan.sqlite")` pattern as candidate_pool tests. Two seeders (`_seed_canonical`, `_seed_candidate`) handle FK-safe insertion; `_seed_state` inserts a `states` row using the actual column name `name` (not `canonical_name`). Six tests:

- `test_auto_merge_writes_match_target_id_and_audit` — strong(+0.50) + state_same(+0.20) + social_same(+0.10) = 0.80 ≥ 0.75 → `match_target_id` written + `audit_log` row with `actor='link@v1'`.
- `test_queue_writes_merge_candidates_row` — strong(+0.50) + state one_null(±0) = 0.50, in [0.40, 0.75) → `merge_candidates` row written with `kind='person'`, `status='open'`.
- `test_skip_leaves_no_trace` — no variant overlap (hard veto, score=0.0) → nothing written, `skipped=1`.
- `test_cross_run_chain_resolution` — two same-run sibling candidates sharing names; first alphabetically is processed, scores 0.80 against the sibling → `match_target_id` points at the sibling candidate id; sibling is added to `already_matched` set and skipped.
- `test_returns_stats_dict` — empty run → stats dict has exactly the four expected keys.
- `test_variants_denormalized_from_variants_json` — seeds candidate with `variants_json` only (Phase 2 stage 3 pattern); asserts `candidate_person_variants` rows are created by `_denormalize_variants` before scoring.

Score values in tests are calibrated against the actual scorer formula; the queue test uses `state=one_null` (one side has no state_id) to land in [0.40, 0.75), and the cross-run test adds `social_category='royalty'` on both sides to reach 0.80.

## What would invalidate this article

- Adding a second test runner.
- Changing the golden-chapter selection criteria.
- Moving fixtures out of `tests/fixtures/`.
- Changing `apply_schema`'s idempotency contract (currently delegated to DDL).
