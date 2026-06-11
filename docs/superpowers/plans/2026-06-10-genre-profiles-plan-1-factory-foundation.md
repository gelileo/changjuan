# Genre Profiles — Plan 1: Factory Foundation + State→Group Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "genre profile" a declarative, first-class concept in the changjuan factory and rename the `State` entity to a general `Group`, while proving dzl re-exports identically (schema_version 7).

**Architecture:** A profile is data in `book-meta.json` (`profile` + ETL `capabilities`). A new `pipeline/profile.py` holds the profile registry (capability sets + relation-kind vocabularies + the ETL→reader capability derivation). The `states` entity is renamed to `groups` (with a typed `group_type` column) across the canonical schema, candidate tables, extraction schema, loaders, linker, and export. dzl's existing `canonical.sqlite` is migrated in place (states→groups, `group_type='state'`) so **no re-extraction occurs** — the export strips candidates anyway, so canonical migration alone guarantees parity.

**Tech Stack:** Python 3, SQLite, Typer CLI, pytest. Spec: `docs/superpowers/specs/2026-06-10-capability-genre-profiles-design.md`.

---

## File Structure

**New files:**
- `pipeline/profile.py` — profile registry: `PROFILES`, `relation_kinds_for()`, `derive_reader_capabilities()`.
- `pipeline/migrations/0001_state_to_group.py` — one-time migration of an existing canonical.sqlite (states→groups).
- `tests/test_profile.py` — profile registry + capability derivation unit tests.
- `tests/test_state_to_group_migration.py` — migration unit test against a synthetic fixture.
- `tests/test_dzl_export_parity.py` — the acceptance-A regression test (synthetic + integration).
- `tests/test_relation_vocab.py` — relation-kind validation against profile vocab.

**Renamed/modified (canonical layer):**
- `pipeline/schemas/canonical_schema.sql` — `states`→`groups` (+`group_type`), `persons.state_id`→`group_id`, `person_states`→`person_groups`, `state_capitals`→`group_seats`, `candidate_states`→`candidate_groups`, `candidate_person_states`→`candidate_person_groups`, `entity_citations` value `'state'`/`'state_capital'`→`'group'`/`'group_seat'`, drop the `person_relations.kind` CHECK.
- `pipeline/stage7_load/states.py` → `pipeline/stage7_load/groups.py` (`load_candidate_states`→`load_candidate_groups`).
- `pipeline/stage7_load/id_maps.py` — `build_state_id_map`→`build_group_id_map`.
- `pipeline/stage7_load/relations.py`, `persons.py`, `__init__.py` — column/import renames + relation-vocab validation.
- `pipeline/stage5_link/scoring.py`, `candidate_pool.py`, `merge.py` — `state_id`→`group_id`, `state_agreement`→`group_agreement`, `person_states`→`person_groups`, table refs.
- `pipeline/export_enrich.py` — `add_state_prominence`→`add_group_prominence` (reads `groups`, `persons.group_id`).
- `pipeline/stage9_export.py` — `SCHEMA_VERSION = 7`; derive reader capabilities for the manifest.
- `pipeline/schemas/extract_output.py` — `states`→`groups`, `state_id`→`group_id` pattern, `state`/`state_capital` entity_kinds → `group`/`group_seat`.
- `pipeline/cli.py` — `load`/`export` echo wording; pass profile through.
- `data/books/dzl/book-meta.json` — add `profile: "history"` + ETL `capabilities`.

**Knowledge (same-task rule):** `knowledge/concepts/pipeline/profiles.md` (new), updates to `knowledge-graph.md`, `extraction.md`, `architecture.md`, `export-contract.md`, the CLAUDE.md article-mapping table, `knowledge/log.md`.

---

## Identifier rename map (apply consistently everywhere)

| Old | New |
| --- | --- |
| table `states` | `groups` |
| `states.type` | `groups.group_type` |
| `persons.state_id` | `persons.group_id` |
| table `person_states` | `person_groups` |
| `person_states.state_id` | `person_groups.group_id` |
| table `state_capitals` | `group_seats` |
| `state_capitals.state_id` | `group_seats.group_id` |
| table `candidate_states` | `candidate_groups` |
| table `candidate_person_states` | `candidate_person_groups` |
| `candidate_person_states.candidate_state_id` | `candidate_person_groups.candidate_group_id` |
| `entity_citations` value `'state'` | `'group'` |
| `entity_citations` value `'state_capital'` | `'group_seat'` |
| id prefix `sta:` (in ids) | **unchanged** — state-type group ids stay `sta:` |
| reign tables / `dates.py` | **unchanged** — operate on id values, not the column |
| `build_state_id_map` | `build_group_id_map` |
| `load_candidate_states` | `load_candidate_groups` |
| `add_state_prominence` | `add_group_prominence` |
| linker feature `state_agreement` | `group_agreement` |

> **`sta:` ids stay.** Renaming the *table* to `groups` does not change existing primary-key values like `sta:jin`. State-type groups keep `sta:` ids so reign resolution (`dates.py`, `data/reigns/sta_*.yaml`) is untouched. New non-state groups (Plan 3) will use their own prefixes.

---

## Task 1: Profile registry module

**Files:**
- Create: `pipeline/profile.py`
- Test: `tests/test_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile.py
import pytest
from pipeline.profile import (
    PROFILES,
    relation_kinds_for,
    derive_reader_capabilities,
    UnknownProfileError,
)


def test_history_profile_has_expected_etl_capabilities():
    assert PROFILES["history"]["capabilities"] == [
        "persons", "relations", "events", "chronology", "geography", "groups",
    ]


def test_history_person_relation_kinds_match_legacy_set():
    assert relation_kinds_for("history", "person") == {
        "parent", "child", "spouse", "sibling", "mentor", "ruler", "minister",
        "ally", "rival", "killed_by", "clan_member",
    }


def test_history_event_relation_kinds():
    assert relation_kinds_for("history", "event") == {"causes", "precedes", "related"}


def test_unknown_profile_raises():
    with pytest.raises(UnknownProfileError):
        relation_kinds_for("nonsuch", "person")


def test_derive_reader_capabilities_for_history():
    etl = ["persons", "relations", "events", "chronology", "geography", "groups"]
    assert derive_reader_capabilities(etl) == ["cast", "timeline", "groups"]


def test_derive_reader_capabilities_for_cast_like_set():
    etl = ["persons", "relations", "events", "groups", "themes"]
    assert derive_reader_capabilities(etl) == ["cast", "groups", "themes"]


def test_derive_reader_capabilities_is_order_stable():
    # canonical tab order regardless of input order
    etl = ["groups", "themes", "persons", "chronology"]
    assert derive_reader_capabilities(etl) == ["cast", "timeline", "groups", "themes"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.profile'`.

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/profile.py
"""Genre-profile registry.

A profile is declarative data selecting which *capabilities* the ETL mines for a
book. It drives: the extraction prompt-pack, which capability-specific stages run,
the relation-kind vocabulary the loader validates against, and (via
derive_reader_capabilities) the coarse reader-tab capabilities written to the
export manifest.

Two capability vocabularies (see spec §3.4):
  - ETL (fine): persons, relations, events, chronology, geography, groups, themes
  - Reader (coarse tabs): cast, timeline, groups, themes
"""

from __future__ import annotations


class UnknownProfileError(KeyError):
    """Raised when a profile name is not in PROFILES."""


_HISTORY_PERSON_KINDS = {
    "parent", "child", "spouse", "sibling", "mentor", "ruler", "minister",
    "ally", "rival", "killed_by", "clan_member",
}
_HISTORY_EVENT_KINDS = {"causes", "precedes", "related"}

PROFILES: dict[str, dict] = {
    "history": {
        "capabilities": ["persons", "relations", "events", "chronology", "geography", "groups"],
        "person_relation_kinds": _HISTORY_PERSON_KINDS,
        "event_relation_kinds": _HISTORY_EVENT_KINDS,
    },
    # "cast" profile lands in Plan 3 (red-chamber slice).
}

# ETL capability → reader tab. Order here defines canonical tab order.
_READER_TAB_RULES: list[tuple[str, str]] = [
    ("cast", "persons"),       # relations render inside the cast tab
    ("timeline", "chronology"),  # a dateless event list is not a timeline
    ("groups", "groups"),
    ("themes", "themes"),
]


def relation_kinds_for(profile: str, relation: str) -> set[str]:
    """Return the allowed relation `kind` vocabulary for a profile.

    relation is 'person' or 'event'. Raises UnknownProfileError on unknown profile.
    """
    if profile not in PROFILES:
        raise UnknownProfileError(profile)
    key = f"{relation}_relation_kinds"
    return PROFILES[profile][key]


def derive_reader_capabilities(etl_capabilities: list[str]) -> list[str]:
    """Map fine-grained ETL capabilities to coarse reader-tab capabilities."""
    have = set(etl_capabilities)
    return [tab for tab, required in _READER_TAB_RULES if required in have]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profile.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/profile.py tests/test_profile.py
git commit -m "feat(profile): genre-profile registry + reader-capability derivation"
```

---

## Task 2: Canonical schema rename (State→Group, drop relation CHECK)

**Files:**
- Modify: `pipeline/schemas/canonical_schema.sql`
- Test: `tests/test_canonical_schema_groups.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_canonical_schema_groups.py
import sqlite3
from pathlib import Path

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def _conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    return c


def _tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cols(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def test_groups_table_replaces_states():
    c = _conn()
    tables = _tables(c)
    assert "groups" in tables and "states" not in tables
    assert "group_type" in _cols(c, "groups")


def test_person_and_junctions_renamed():
    c = _conn()
    tables = _tables(c)
    assert "group_id" in _cols(c, "persons") and "state_id" not in _cols(c, "persons")
    assert "person_groups" in tables and "person_states" not in tables
    assert "group_seats" in tables and "state_capitals" not in tables
    assert "candidate_groups" in tables and "candidate_states" not in tables
    assert "candidate_person_groups" in tables


def test_person_relations_has_no_kind_check():
    # CHECK is gone — vocab is now validated in the loader against the profile.
    c = _conn()
    c.execute("INSERT INTO persons (id, canonical_name, confidence, provenance) "
              "VALUES ('per:a','A',0.9,'auto'),('per:b','B',0.9,'auto')")
    # An arbitrary kind that the old CHECK would have rejected now inserts fine.
    c.execute("INSERT INTO person_relations "
              "(from_person_id,to_person_id,kind,confidence,provenance) "
              "VALUES ('per:a','per:b','恋慕',0.9,'auto')")


def test_entity_citations_kind_values():
    c = _conn()
    # 'group' and 'group_seat' accepted; 'state' rejected.
    c.execute("INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
              "VALUES ('group','sta:jin','cit:1')")
    c.execute("INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
              "VALUES ('group_seat','sta:jin','cit:2')")
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
                  "VALUES ('state','sta:jin','cit:3')")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_canonical_schema_groups.py -v`
Expected: FAIL (tables still named `states`/`person_states`, CHECK present).

- [ ] **Step 3: Edit the schema**

In `pipeline/schemas/canonical_schema.sql` apply the identifier rename map:
- `persons.state_id TEXT REFERENCES states(id)` → `group_id TEXT REFERENCES groups(id)`.
- Rename `CREATE TABLE ... states (` → `groups (`, and the column `type TEXT` → `group_type TEXT`.
- Rename `state_capitals` → `group_seats` and its `state_id ... REFERENCES states(id)` → `group_id ... REFERENCES groups(id)`.
- In `person_relations`, replace the entire `kind TEXT NOT NULL CHECK (kind IN (...))` with `kind TEXT NOT NULL` (drop the CHECK; keep `NOT NULL`).
- Rename `person_states` → `person_groups`; its `state_id ... REFERENCES states(id)` → `group_id ... REFERENCES groups(id)`; PK `(person_id, state_id, role, from_date_json)` → `(person_id, group_id, role, from_date_json)`.
- In `entity_citations` CHECK list: replace `'state'` with `'group'` and `'state_capital'` with `'group_seat'`.
- Rename `candidate_states` → `candidate_groups`; `candidate_person_states` → `candidate_person_groups` with `candidate_state_id` → `candidate_group_id` and PK update.
- `merge_candidates.kind` CHECK: replace `'state'` with `'group'`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_canonical_schema_groups.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/schemas/canonical_schema.sql tests/test_canonical_schema_groups.py
git commit -m "refactor(schema): rename states->groups, drop person_relations.kind CHECK"
```

---

## Task 3: Rename the state loader → group loader

**Files:**
- Rename: `pipeline/stage7_load/states.py` → `pipeline/stage7_load/groups.py`
- Modify: `pipeline/stage7_load/__init__.py`
- Test: `tests/test_load_groups.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_load_groups.py
import sqlite3
from pathlib import Path
from pipeline.stage7_load.groups import load_candidate_groups

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def test_load_candidate_groups_creates_group_type_state():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    c.execute(
        "INSERT INTO candidate_groups "
        "(id,name,group_type,ruling_clan,confidence,pipeline_run_id,chunk_id,quote) "
        "VALUES ('cand:grp:r1:s1','晋','state','姬',0.9,'r1','ch:1','晋侯')"
    )
    n = load_candidate_groups(c, pipeline_run_id="r1")
    assert n == 1
    row = c.execute("SELECT id, name, group_type FROM groups WHERE name='晋'").fetchone()
    assert row[0].startswith("sta:") and row[2] == "state"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_load_groups.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.stage7_load.groups'`.

- [ ] **Step 3: Rename + edit the loader**

```bash
git mv pipeline/stage7_load/states.py pipeline/stage7_load/groups.py
```

In `pipeline/stage7_load/groups.py` apply:
- `load_candidate_states` → `load_candidate_groups`.
- `_STATE_SCALAR_FIELDS = ("type", ...)` → `_GROUP_SCALAR_FIELDS = ("group_type", "ruling_clan", "founded_date_json", "ended_date_json")`.
- The SELECT from `candidate_states` → `candidate_groups`, selecting `group_type` instead of `type`.
- All `INSERT INTO states` / `UPDATE states` / `SELECT ... FROM states` → `groups`; column `type` → `group_type`.
- `_audit(conn, "state", ...)` → `_audit(conn, "group", ...)`; `record_citation(conn, "state", ...)` → `record_citation(conn, "group", ...)`.
- Keep the `state_id` local variable name as `group_id` for clarity; the generated id still uses the `sta:` prefix: `group_id = f"sta:{_slugify(name)}"` (state-type groups keep `sta:` per the rename map).
- The local `stype` variable → `gtype`.

In `pipeline/stage7_load/__init__.py`:
- `from pipeline.stage7_load.states import load_candidate_states` → `from pipeline.stage7_load.groups import load_candidate_groups`.
- Update `__all__` (`"load_candidate_states"` → `"load_candidate_groups"`) and the module-layout docstring line.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_load_groups.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add -A pipeline/stage7_load/ tests/test_load_groups.py
git commit -m "refactor(load): states loader -> groups loader (group_type=state)"
```

---

## Task 4: Rename id-map builder

**Files:**
- Modify: `pipeline/stage7_load/id_maps.py`
- Test: extend `tests/test_load_groups.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_load_groups.py
from pipeline.stage7_load.id_maps import build_group_id_map


def test_build_group_id_map_resolves_local_to_canonical():
    import sqlite3
    from pathlib import Path
    SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    c.execute("INSERT INTO candidate_groups "
              "(id,name,group_type,confidence,pipeline_run_id,chunk_id,quote) "
              "VALUES ('cand:grp:r1:s1','晋','state',0.9,'r1','ch:1','q')")
    load_candidate_groups(c, pipeline_run_id="r1")
    m = build_group_id_map(c, "r1")
    assert m["s1"].startswith("sta:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_load_groups.py::test_build_group_id_map_resolves_local_to_canonical -v`
Expected: FAIL with `ImportError: cannot import name 'build_group_id_map'`.

- [ ] **Step 3: Edit id_maps.py**

- `build_state_id_map` → `build_group_id_map`; docstring `candidate_state_id`/`states` → `candidate_group_id`/`groups`.
- prefix `f"cand:sta:{run_id}:"` → `f"cand:grp:{run_id}:"`.
- SELECT `FROM candidate_states cs JOIN states s ON s.name = cs.name` → `FROM candidate_groups cs JOIN groups s ON s.name = cs.name`.
- Update the module docstring's candidate-id format line: `candidate_states.id format: cand:sta:...` → `candidate_groups.id format: cand:grp:...`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_load_groups.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/stage7_load/id_maps.py tests/test_load_groups.py
git commit -m "refactor(load): build_state_id_map -> build_group_id_map (cand:grp prefix)"
```

---

## Task 5: Relation-kind validation against profile vocab

**Files:**
- Modify: `pipeline/stage7_load/relations.py`
- Test: `tests/test_relation_vocab.py` (create)

The loader today rejects kinds outside hardcoded `_VALID_PERSON_RELATION_KINDS` / `_VALID_EVENT_RELATION_KINDS`. Replace those constants with a profile lookup.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_relation_vocab.py
import sqlite3
from pathlib import Path
from pipeline.stage7_load.relations import _valid_person_kinds

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def test_valid_person_kinds_from_history_profile():
    kinds = _valid_person_kinds("history")
    assert "clan_member" in kinds and "ally" in kinds
    assert "恋慕" not in kinds  # cast vocab not valid under history
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_relation_vocab.py -v`
Expected: FAIL with `ImportError: cannot import name '_valid_person_kinds'`.

- [ ] **Step 3: Edit relations.py**

- Add imports: `from pipeline.profile import relation_kinds_for`.
- Replace the module constant `_VALID_PERSON_RELATION_KINDS = {...}` with:

```python
def _valid_person_kinds(profile: str) -> set[str]:
    return relation_kinds_for(profile, "person")


def _valid_event_kinds(profile: str) -> set[str]:
    return relation_kinds_for(profile, "event")
```

- Thread a `profile: str = "history"` parameter into `load_candidate_relations` and its `_load_*_relations` helpers; replace the `kind not in _VALID_PERSON_RELATION_KINDS` guard with `kind not in _valid_person_kinds(profile)` (and the event equivalent).
- Default `profile="history"` keeps existing callers working until Task 9 threads the real profile through the CLI.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_relation_vocab.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/stage7_load/relations.py tests/test_relation_vocab.py
git commit -m "feat(load): validate relation kinds against profile vocab, not a DB CHECK"
```

---

## Task 6: Column renames in relations.py, persons.py, stage5_link

**Files:**
- Modify: `pipeline/stage7_load/relations.py`, `pipeline/stage7_load/persons.py`
- Modify: `pipeline/stage5_link/scoring.py`, `candidate_pool.py`, `merge.py`
- Verify: grep

This is a mechanical column/table rename. Apply the identifier rename map, then verify with grep.

- [ ] **Step 1: Apply renames**

- `relations.py`: `from pipeline.stage7_load.id_maps import build_state_id_map` → `build_group_id_map`; any `person_states`→`person_groups`, `state_id`→`group_id`, `candidate_state_id`→`candidate_group_id`, `candidate_states`→`candidate_groups`, `build_state_id_map(`→`build_group_id_map(`.
- `persons.py`: `state_id`→`group_id` in SQL column lists and INSERT/UPDATE for `persons`; `candidate_persons.state_id`→`candidate_persons.group_id` if read.
- `stage5_link/scoring.py`: feature key `"state_agreement"`→`"group_agreement"`; `_classify_field_agreement(a, b, "state_id")`→`"group_id"`; comment/threshold references to `state_agreement` → `group_agreement`.
- `stage5_link/candidate_pool.py`: `_resolve_state_local_to_canonical`→`_resolve_group_local_to_canonical`; `raw_state_id`→`raw_group_id`; `state_id`→`group_id` in SELECT lists and dict keys; `JOIN states s`→`JOIN groups s`; `candidate_states`→`candidate_groups`; `_row_to_dict_with_resolved_state`→`_row_to_dict_with_resolved_group`.
- `stage5_link/merge.py`: `_SNAPSHOTTABLE_TABLES` `"states"`→`"groups"`; `_resolve_collisions_person_states`→`_resolve_collisions_person_groups`; `person_states`→`person_groups`; `state_id`→`group_id`; `_LOCAL_STATE_ID_RE`→`_LOCAL_GROUP_ID_RE` (regex pattern `s\d+` unchanged — local extraction ids are still `s1`-style); `SELECT 1 FROM states`→`FROM groups`; the snapshot column list `state_id`→`group_id`.

> Local extraction ids (`s1`, `s2`) are unchanged — only canonical column/table names move. The `cand:grp:` prefix (Task 4) is the candidate *row* id; the FK *value* a relation points at is still the local `s1`.

- [ ] **Step 2: Verify no stale identifiers remain**

Run:
```bash
grep -rn "state_id\|person_states\|candidate_states\|build_state_id_map\|state_agreement\|state_capitals\|add_state_prominence\|load_candidate_states\|FROM states\|INTO states\|UPDATE states" pipeline/ --include="*.py" | grep -v __pycache__
```
Expected: only matches in `pipeline/dates.py` (reign resolution — intentionally unchanged) and `pipeline/discovery.py` `STATE_NAMES` (history extraction helper — unchanged). **No matches in stage5_link/ or stage7_load/.**

- [ ] **Step 3: Run the full suite (expect failures only in not-yet-renamed modules)**

Run: `pytest -x -q 2>&1 | tail -20`
Expected: failures localized to `export_enrich`/`extract_output`/`cli` (Tasks 7-9) and any tests asserting old names; the renamed modules import cleanly.

- [ ] **Step 4: Commit**

```bash
git add pipeline/stage7_load/relations.py pipeline/stage7_load/persons.py pipeline/stage5_link/
git commit -m "refactor(load,link): state_id->group_id column + state_agreement->group_agreement"
```

---

## Task 7: export_enrich + stage9 (prominence rename, schema_version, reader caps)

**Files:**
- Modify: `pipeline/export_enrich.py`, `pipeline/stage9_export.py`
- Test: `tests/test_export_reader_caps.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_reader_caps.py
from pipeline.stage9_export import SCHEMA_VERSION, manifest_reader_capabilities


def test_schema_version_is_7():
    assert SCHEMA_VERSION == 7


def test_manifest_reader_capabilities_derives_from_profile_caps():
    meta = {"book_id": "dzl", "capabilities":
            ["persons", "relations", "events", "chronology", "geography", "groups"]}
    assert manifest_reader_capabilities(meta) == ["cast", "timeline", "groups"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_reader_caps.py -v`
Expected: FAIL (`SCHEMA_VERSION == 6`; `manifest_reader_capabilities` undefined).

- [ ] **Step 3: Edit export + export_enrich**

In `pipeline/stage9_export.py`:
- `SCHEMA_VERSION = 6` → `SCHEMA_VERSION = 7` (update the inline comment to: `# v7: states->groups rename; profile-derived reader capabilities`).
- Add import: `from pipeline.profile import derive_reader_capabilities`.
- Add helper:

```python
def manifest_reader_capabilities(book_meta: Mapping[str, object]) -> list[str]:
    """The coarse reader-tab capabilities for the manifest, derived from the
    book's fine-grained ETL capabilities (spec §3.4)."""
    return derive_reader_capabilities(list(book_meta["capabilities"]))
```

- In `export_bundle`, change the import `add_state_prominence` → `add_group_prominence`, the call `add_state_prominence(...)` → `add_group_prominence(...)`, and set `"capabilities": manifest_reader_capabilities(book_meta)` in the manifest dict (replacing `book_meta["capabilities"]`).

In `pipeline/export_enrich.py`:
- `add_state_prominence` → `add_group_prominence`; `PRAGMA table_info(states)` → `(groups)`; `SELECT p.state_id ... WHERE p.state_id IS NOT NULL GROUP BY p.state_id` → `p.group_id`; `SELECT id, name FROM states` → `FROM groups`; `UPDATE states SET ...` → `UPDATE groups SET ...`. The `prominence_overrides.yaml` key stays `states:` OR rename to `groups:` — **keep `states:`** for now (it is a curated allow-list of names, not a schema name; renaming it would require editing `data/books/dzl/prominence_overrides.yaml`; defer to a follow-up). Add a code comment noting the key name is historical.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_reader_caps.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/stage9_export.py pipeline/export_enrich.py tests/test_export_reader_caps.py
git commit -m "feat(export): schema_version 7, group prominence, profile-derived reader caps"
```

---

## Task 8: Extraction-output schema rename

**Files:**
- Modify: `pipeline/schemas/extract_output.py`
- Test: `tests/test_extract_output_groups.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract_output_groups.py
from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA as SCHEMA


def test_top_level_has_groups_not_states():
    props = SCHEMA["properties"]
    assert "groups" in props and "states" not in props
    assert "groups" in SCHEMA["required"] and "states" not in SCHEMA["required"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extract_output_groups.py -v`
Expected: FAIL (top-level still has `states`).

- [ ] **Step 3: Edit extract_output.py**

- `persons[].state_id` pattern `^(s\d+|sta:[\w\-]+)$` → property `group_id` with pattern `^(s\d+|sta:[\w\-]+)$` (local `s1` ids and `sta:` canonical ids unchanged).
- `_STATE_SCHEMA` → `_GROUP_SCHEMA`; add a `group_type` property; rename top-level `"states"` array key → `"groups"`; `"required": [..., "states", ...]` → `"groups"`.
- entity_kind enum entries `"person_state"` → `"person_group"`, `"state_capital"` → `"group_seat"` (and `"state"`→`"group"` if present).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract_output_groups.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/schemas/extract_output.py tests/test_extract_output_groups.py
git commit -m "refactor(extract-schema): states->groups, state_id->group_id"
```

---

## Task 9: CLI wiring (profile threading + echo wording)

**Files:**
- Modify: `pipeline/cli.py`
- Test: covered by Task 11 integration.

- [ ] **Step 1: Edit cli.py**

- In the `load` command: read the book's profile from `book-meta.json` (`meta.get("profile", "history")`) and pass `profile=...` to `load_candidate_relations(...)`. Rename the echo `states=` → `groups=` and the `n_states = load_candidate_states(...)` call → `n_groups = load_candidate_groups(...)`; update the import.
- In the `export`/`publish-depot` commands: no change needed (export reads capabilities from meta; derivation is internal).

- [ ] **Step 2: Verify CLI imports**

Run: `python -c "from pipeline.cli import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add pipeline/cli.py
git commit -m "feat(cli): thread profile into load; groups echo wording"
```

---

## Task 10: One-time dzl canonical.sqlite migration

**Files:**
- Create: `pipeline/migrations/0001_state_to_group.py`
- Test: `tests/test_state_to_group_migration.py`

This migrates an **existing** populated canonical.sqlite (old `states` schema) to the new `groups` schema in place, setting `group_type='state'` for every migrated row. dzl's data is preserved exactly (parity).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state_to_group_migration.py
import sqlite3
from pipeline.migrations import migrate_0001_state_to_group as migrate

OLD_SCHEMA = """
CREATE TABLE states (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT,
    ruling_clan TEXT, founded_date_json TEXT, ended_date_json TEXT,
    confidence REAL NOT NULL, provenance TEXT NOT NULL, pipeline_run_id TEXT,
    created_at TEXT, updated_at TEXT);
CREATE TABLE persons (id TEXT PRIMARY KEY, canonical_name TEXT, state_id TEXT,
    confidence REAL NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE person_states (person_id TEXT, state_id TEXT, role TEXT,
    from_date_json TEXT, confidence REAL NOT NULL, provenance TEXT NOT NULL,
    PRIMARY KEY (person_id, state_id, role, from_date_json));
CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT,
    PRIMARY KEY (entity_kind, entity_id, citation_id));
"""


def test_migration_preserves_rows_and_sets_group_type_state():
    c = sqlite3.connect(":memory:")
    c.executescript(OLD_SCHEMA)
    c.execute("INSERT INTO states (id,name,type,confidence,provenance) "
              "VALUES ('sta:jin','晋','诸侯国',0.9,'auto')")
    c.execute("INSERT INTO persons (id,canonical_name,state_id,confidence,provenance) "
              "VALUES ('per:x','重耳','sta:jin',0.9,'auto')")
    c.execute("INSERT INTO person_states VALUES ('per:x','sta:jin','ruler',NULL,0.9,'auto')")
    c.execute("INSERT INTO entity_citations VALUES ('state','sta:jin','cit:1')")

    migrate.run(c)

    g = c.execute("SELECT id,name,group_type FROM groups").fetchone()
    assert g == ("sta:jin", "晋", "state")
    assert c.execute("SELECT group_id FROM persons WHERE id='per:x'").fetchone()[0] == "sta:jin"
    assert c.execute("SELECT group_id FROM person_groups").fetchone()[0] == "sta:jin"
    assert c.execute("SELECT entity_kind FROM entity_citations").fetchone()[0] == "group"
    # old tables gone
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "states" not in names and "person_states" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_to_group_migration.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the migration**

```python
# pipeline/migrations/__init__.py
from pipeline.migrations import migrate_0001_state_to_group  # noqa: F401
```

```python
# pipeline/migrations/0001_state_to_group.py
"""One-time, idempotent migration of an existing canonical.sqlite from the
states-named schema to the groups-named schema. Sets group_type='state' on every
migrated row. Used to bring dzl's canonical.sqlite to schema_version 7 WITHOUT
re-extraction (preserves all data exactly)."""

from __future__ import annotations

import sqlite3


def run(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    names = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "groups" in names and "states" not in names:
        return  # already migrated (idempotent)

    cur.execute("PRAGMA foreign_keys = OFF;")

    # 1. groups <- states (+ group_type='state')
    cur.execute(
        "CREATE TABLE groups (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "founded_date_json TEXT, ended_date_json TEXT, ruling_clan TEXT, "
        "group_type TEXT, confidence REAL NOT NULL, provenance TEXT NOT NULL, "
        "pipeline_run_id TEXT, created_at TEXT, updated_at TEXT);"
    )
    cur.execute(
        "INSERT INTO groups (id,name,founded_date_json,ended_date_json,ruling_clan,"
        "group_type,confidence,provenance,pipeline_run_id,created_at,updated_at) "
        "SELECT id,name,founded_date_json,ended_date_json,ruling_clan,"
        "'state',confidence,provenance,pipeline_run_id,created_at,updated_at FROM states;"
    )
    cur.execute("DROP TABLE states;")

    # 2. persons.state_id -> persons.group_id (rebuild column)
    cur.execute("ALTER TABLE persons RENAME COLUMN state_id TO group_id;")

    # 3. person_states -> person_groups
    cur.execute("ALTER TABLE person_states RENAME TO person_groups;")
    cur.execute("ALTER TABLE person_groups RENAME COLUMN state_id TO group_id;")

    # 4. state_capitals -> group_seats (if present)
    names = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "state_capitals" in names:
        cur.execute("ALTER TABLE state_capitals RENAME TO group_seats;")
        cur.execute("ALTER TABLE group_seats RENAME COLUMN state_id TO group_id;")

    # 5. entity_citations value rename
    cur.execute("UPDATE entity_citations SET entity_kind='group' WHERE entity_kind='state';")
    cur.execute(
        "UPDATE entity_citations SET entity_kind='group_seat' WHERE entity_kind='state_capital';"
    )

    conn.commit()
```

> `ALTER TABLE ... RENAME COLUMN` requires SQLite ≥ 3.25 (bundled with Python 3.11+). Verify with `python -c "import sqlite3; print(sqlite3.sqlite_version)"` (expect ≥ 3.25).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_state_to_group_migration.py -v`
Expected: PASS.

- [ ] **Step 5: Add a CLI entry point + commit**

Add to `pipeline/cli.py` a `migrate` command:

```python
@app.command()
def migrate(book_id: str = typer.Option("dzl"), repo_root: Path | None = typer.Option(None)) -> None:
    """Run the one-time state->group migration on a book's canonical.sqlite."""
    from pipeline.migrations import migrate_0001_state_to_group
    cfg = _cfg(repo_root, book_id)
    with connect(cfg.canonical_db) as conn:
        migrate_0001_state_to_group.run(conn)
    typer.echo(f"migrated {cfg.canonical_db} to groups schema")
```

```bash
git add pipeline/migrations/ tests/test_state_to_group_migration.py pipeline/cli.py
git commit -m "feat(migrate): one-time state->group canonical migration (group_type=state)"
```

---

## Task 11: dzl book-meta + export-parity regression test (acceptance A)

**Files:**
- Modify: `data/books/dzl/book-meta.json`
- Test: `tests/test_dzl_export_parity.py` (create)

- [ ] **Step 1: Update dzl book-meta**

In `data/books/dzl/book-meta.json`, add/replace:
```json
"profile": "history",
"capabilities": ["persons", "relations", "events", "chronology", "geography", "groups"]
```
(The manifest's reader-facing capabilities are now *derived* — they become `["cast","timeline","groups"]`.)

- [ ] **Step 2: Write the parity test (synthetic + integration)**

```python
# tests/test_dzl_export_parity.py
import json
import shutil
import sqlite3
from pathlib import Path
import pytest

from pipeline.migrations import migrate_0001_state_to_group as migrate
from pipeline.stage9_export import manifest_reader_capabilities


def test_reader_caps_for_dzl_meta():
    meta = json.loads(Path("data/books/dzl/book-meta.json").read_text("utf-8"))
    assert meta["profile"] == "history"
    assert manifest_reader_capabilities(meta) == ["cast", "timeline", "groups"]


@pytest.mark.integration
def test_dzl_migration_preserves_counts(tmp_path):
    """Migrating dzl canonical.sqlite preserves row counts: groups == old states,
    person_groups == old person_states, and persons.group_id non-null count is
    identical to the pre-migration persons.state_id non-null count."""
    src = Path("data/books/dzl/canonical.sqlite")
    if not src.exists():
        pytest.skip("dzl canonical.sqlite not present")
    work = tmp_path / "canonical.sqlite"
    shutil.copyfile(src, work)
    c = sqlite3.connect(work)
    n_states = c.execute("SELECT COUNT(*) FROM states").fetchone()[0]
    n_person_states = c.execute("SELECT COUNT(*) FROM person_states").fetchone()[0]
    n_state_fk = c.execute("SELECT COUNT(*) FROM persons WHERE state_id IS NOT NULL").fetchone()[0]

    migrate.run(c)

    assert c.execute("SELECT COUNT(*) FROM groups").fetchone()[0] == n_states
    assert c.execute("SELECT COUNT(*) FROM person_groups").fetchone()[0] == n_person_states
    assert c.execute("SELECT COUNT(*) FROM persons WHERE group_id IS NOT NULL").fetchone()[0] == n_state_fk
    assert c.execute("SELECT COUNT(*) FROM groups WHERE group_type='state'").fetchone()[0] == n_states
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_dzl_export_parity.py -v`
Expected: unit test PASS; integration test PASS (or SKIP if the DB is absent).

- [ ] **Step 4: End-to-end smoke (manual, documented)**

Run on a copy of dzl:
```bash
cp data/books/dzl/canonical.sqlite /tmp/dzl-canon-backup.sqlite
uv run changjuan migrate --book-id dzl
uv run changjuan export 2026-06-v9-groups --book-id dzl
```
Expected: export succeeds; `manifest.json` shows `"schema_version": 7` and `"capabilities": ["cast","timeline","groups"]`; `graph.sqlite` has a `groups` table with `group_type='state'` and no `states` table.

- [ ] **Step 5: Commit**

```bash
git add data/books/dzl/book-meta.json tests/test_dzl_export_parity.py
git commit -m "test(parity): dzl profile=history + state->group migration count parity"
```

---

## Task 12: Full suite green + knowledge updates

**Files:**
- Modify: knowledge articles + CLAUDE.md table + log.md

- [ ] **Step 1: Run the whole suite**

Run: `pytest -q`
Expected: all pass (integration tests may skip without data). Fix any remaining references to old identifiers surfaced by failures.

- [ ] **Step 2: Update knowledge (same-task rule)**

- Create `knowledge/concepts/pipeline/profiles.md` — the capability/genre-profile model, the two vocabularies, `derive_reader_capabilities`, relation-vocab-as-config, the `sta:` id-stability rule.
- Update `knowledge/concepts/data-model/knowledge-graph.md` — `State` entity → `Group` (`group_type`), `person_groups`, `group_seats`.
- Update `knowledge/concepts/pipeline/extraction.md` — relation kinds validated against the profile, not a DB CHECK; extraction-schema `groups`.
- Update `knowledge/concepts/pipeline/architecture.md` — capability-guarded stages (note guards land fully in later plans; profile threading begins here).
- Update `knowledge/concepts/pipeline/export-contract.md` — `schema_version 7`; manifest capabilities are derived.
- Add a row to the CLAUDE.md article-mapping table: `pipeline/profile.py` → `concepts/pipeline/profiles.md`.
- Append a `knowledge/log.md` entry listing the articles touched.

- [ ] **Step 3: Commit**

```bash
git add knowledge/ CLAUDE.md
git commit -m "docs(knowledge): profiles model + State->Group across articles (schema 7)"
```

---

## Self-Review Checklist (run after drafting, before execution)

1. **Spec coverage:** profile model (Task 1, 9, 11) · State→Group rename all layers (Tasks 2–9) · relation-vocab-as-config (Tasks 2, 5) · capability derivation (Tasks 1, 7) · schema_version 7 (Task 7) · dzl parity / acceptance A (Tasks 10, 11) · knowledge (Task 12). Themes + cast prompt-pack + ingest generalization are **Plan 3** (out of scope here, per spec §1).
2. **Placeholder scan:** none — every code step shows code; every rename step lists exact identifiers + a grep verification.
3. **Symbol consistency:** `load_candidate_groups`, `build_group_id_map`, `add_group_prominence`, `manifest_reader_capabilities`, `derive_reader_capabilities`, `relation_kinds_for`, `group_id`, `group_type`, `group_agreement` used identically across tasks.
