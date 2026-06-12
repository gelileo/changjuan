# Genre Profiles — Plan 3b: Themes Capability

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Add the `themes` capability end-to-end in the factory — canonical + candidate schema, a theme loader, the extraction-output schema, and capability-gated load wiring — so a `themes`-capable profile (cast) can mine + persist + export themes. No LLM extraction here (that's 3c); tested with synthetic candidate data.

**Architecture:** A `themes` entity + a `theme_occurrences` link table (theme ↔ entity ↔ citation), mirroring the existing entity/relation patterns. Extraction stages a `candidate_themes` row (name + description + `occurrences_json` + quote); `load_candidate_themes` promotes it: name-match/create the canonical theme, record its citation, and resolve each occurrence's *local* entity id (e.g. `p1`,`e1`) to canonical via the existing `build_*_id_map` helpers. Load runs themes only when the profile declares the `themes` capability.

**Tech Stack:** Python 3, SQLite, pytest. Spec §3.3. Branch `feat/hlm-cast`.

---

## File Structure
- **Modify** `pipeline/schemas/canonical_schema.sql` — add `themes`, `theme_occurrences`, `candidate_themes`; add `'theme'` to the `entity_citations` kind CHECK.
- **Create** `pipeline/stage7_load/themes.py` — `load_candidate_themes`.
- **Modify** `pipeline/stage7_load/__init__.py` — export `load_candidate_themes`.
- **Modify** `pipeline/schemas/extract_output.py` — add the optional `themes` array.
- **Modify** `pipeline/cli.py` — `load` calls `load_candidate_themes` when the profile has the `themes` capability.
- **Tests:** `tests/test_canonical_schema_themes.py`, `tests/test_load_themes.py`, `tests/test_extract_output_themes.py` (create).
- **Knowledge:** `concepts/data-model/knowledge-graph.md` (themes entity), `concepts/pipeline/profiles.md` (themes capability behavior), `concepts/pipeline/load-and-merge.md` (theme loader), `concepts/pipeline/export-contract.md` (themes tables exported); `log.md`.

---

## Task 1: Themes schema (canonical + candidate)

**Files:** Modify `pipeline/schemas/canonical_schema.sql`; Test `tests/test_canonical_schema_themes.py`.

- [ ] **Step 1: Write the failing test `tests/test_canonical_schema_themes.py`**
```python
import sqlite3
from pathlib import Path
import pytest

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def _conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    return c


def _tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_theme_tables_exist():
    c = _conn()
    t = _tables(c)
    assert {"themes", "theme_occurrences", "candidate_themes"} <= t


def test_theme_occurrence_insert_and_entity_citation_theme_kind():
    c = _conn()
    c.execute("INSERT INTO themes (id,name,confidence,provenance) VALUES ('thm:命运','命运',0.9,'auto')")
    c.execute("INSERT INTO persons (id,canonical_name,confidence,provenance) VALUES ('per:黛玉','林黛玉',0.9,'auto')")
    c.execute("INSERT INTO theme_occurrences (theme_id,entity_kind,entity_id,confidence,provenance) "
              "VALUES ('thm:命运','person','per:黛玉',0.9,'auto')")
    # 'theme' is now an allowed entity_citations kind
    c.execute("INSERT INTO entity_citations (entity_kind,entity_id,citation_id) VALUES ('theme','thm:命运','cit:1')")


def test_candidate_themes_columns():
    c = _conn()
    cols = {r[1] for r in c.execute("PRAGMA table_info(candidate_themes)")}
    assert {"id", "name", "description", "occurrences_json", "confidence",
            "pipeline_run_id", "chunk_id", "quote"} <= cols
```

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_canonical_schema_themes.py -v`.

- [ ] **Step 3: Edit `pipeline/schemas/canonical_schema.sql`**
- Add `'theme'` to the `entity_citations` `entity_kind` CHECK list (append after `'group_seat'`).
- Add the three tables (place the canonical two near the other entity tables; `candidate_themes` in the candidate section):
```sql
CREATE TABLE IF NOT EXISTS themes (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS theme_occurrences (
    theme_id        TEXT NOT NULL REFERENCES themes(id),
    entity_kind     TEXT NOT NULL CHECK (entity_kind IN ('person','event','group','place','chapter')),
    entity_id       TEXT NOT NULL,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (theme_id, entity_kind, entity_id)
);

CREATE TABLE IF NOT EXISTS candidate_themes (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    occurrences_json TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Run, verify PASS** — `uv run pytest tests/test_canonical_schema_themes.py -v`.

- [ ] **Step 5: Commit**
```bash
git add pipeline/schemas/canonical_schema.sql tests/test_canonical_schema_themes.py
git commit -m "feat(schema): themes + theme_occurrences + candidate_themes (entity_citations 'theme')"
```

---

## Task 2: Theme loader

**Files:** Create `pipeline/stage7_load/themes.py`; Modify `pipeline/stage7_load/__init__.py`; Test `tests/test_load_themes.py`.

- [ ] **Step 1: Write the failing test `tests/test_load_themes.py`**
```python
import json
import sqlite3
from pathlib import Path
from pipeline.stage7_load.themes import load_candidate_themes

SCHEMA = Path("pipeline/schemas/canonical_schema.sql").read_text(encoding="utf-8")


def _seed(c):
    # a canonical person the occurrence can resolve to (via name-join id map)
    c.execute("INSERT INTO persons (id,canonical_name,confidence,provenance) "
              "VALUES ('per:黛玉','林黛玉',0.9,'auto')")
    c.execute("INSERT INTO candidate_persons "
              "(id,canonical_name,confidence,pipeline_run_id,chunk_id,quote) "
              "VALUES ('cand:per:r1:p1','林黛玉',0.9,'r1','hlm:1','q')")
    occ = json.dumps([{"entity_kind": "person", "entity_id": "p1"},
                      {"entity_kind": "chapter", "entity_id": "hlm:1"}], ensure_ascii=False)
    c.execute("INSERT INTO candidate_themes "
              "(id,name,description,occurrences_json,confidence,pipeline_run_id,chunk_id,quote) "
              "VALUES ('cand:thm:r1:t1','命运','宿命与无常',?,0.9,'r1','hlm:1','q')", (occ,))


def test_load_candidate_themes_creates_theme_and_resolves_occurrences():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    _seed(c)
    n = load_candidate_themes(c, pipeline_run_id="r1")
    assert n == 1
    th = c.execute("SELECT id, name, description FROM themes").fetchone()
    assert th[0].startswith("thm:") and th[1] == "命运"
    occ = c.execute("SELECT entity_kind, entity_id FROM theme_occurrences ORDER BY entity_kind").fetchall()
    # local 'p1' resolved to canonical 'per:黛玉'; chapter id passes through
    assert ("person", "per:黛玉") in occ
    assert ("chapter", "hlm:1") in occ
    # theme citation recorded
    assert c.execute("SELECT COUNT(*) FROM entity_citations WHERE entity_kind='theme'").fetchone()[0] >= 1


def test_load_candidate_themes_idempotent_name_match():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    _seed(c)
    load_candidate_themes(c, pipeline_run_id="r1")
    load_candidate_themes(c, pipeline_run_id="r1")  # same name → no duplicate theme
    assert c.execute("SELECT COUNT(*) FROM themes").fetchone()[0] == 1
```

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_load_themes.py -v` (ModuleNotFoundError).

- [ ] **Step 3: Create `pipeline/stage7_load/themes.py`**
```python
"""Stage 7 — load_candidate_themes. Promotes candidate_themes → canonical themes +
theme_occurrences. Themes match by name; occurrences resolve a local extraction
entity id (e.g. 'p1','e1') to canonical via the build_*_id_map helpers, except
'chapter' ids which pass through (they are already document ids like 'hlm:1')."""

from __future__ import annotations

import json as _json
import sqlite3

from pipeline.stage7_load.citations import record_citation
from pipeline.stage7_load.helpers import _slugify
from pipeline.stage7_load.id_maps import (
    build_event_id_map,
    build_group_id_map,
    build_person_id_map,
    build_place_id_map,
)


def load_candidate_themes(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote candidate_themes for this run into canonical themes + theme_occurrences.

    Returns the number of candidate themes processed. Idempotent on theme name and on
    (theme_id, entity_kind, entity_id) occurrence keys.
    """
    maps = {
        "person": build_person_id_map(conn, pipeline_run_id),
        "event": build_event_id_map(conn, pipeline_run_id),
        "group": build_group_id_map(conn, pipeline_run_id),
        "place": build_place_id_map(conn, pipeline_run_id),
    }
    cands = conn.execute(
        "SELECT id, name, description, occurrences_json, chunk_id, confidence "
        "FROM candidate_themes WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ).fetchall()

    n = 0
    for cand_id, name, description, occurrences_json, chunk_id, confidence in cands:
        existing = conn.execute("SELECT id FROM themes WHERE name = ?", (name,)).fetchone()
        if existing is None:
            theme_id = f"thm:{_slugify(name)}"
            conn.execute(
                "INSERT INTO themes (id, name, description, provenance, confidence, pipeline_run_id) "
                "VALUES (?, ?, ?, 'auto', ?, ?)",
                (theme_id, name, description, confidence, pipeline_run_id),
            )
        else:
            theme_id = existing[0]
            if description:
                conn.execute(
                    "UPDATE themes SET description = COALESCE(description, ?), "
                    "updated_at = datetime('now') WHERE id = ?",
                    (description, theme_id),
                )
        record_citation(conn, "theme", theme_id, chunk_id)

        for occ in _json.loads(occurrences_json or "[]"):
            kind = occ.get("entity_kind")
            local = occ.get("entity_id")
            if not kind or not local:
                continue
            entity_id = local if kind == "chapter" else maps.get(kind, {}).get(local)
            if entity_id is None:
                continue  # unresolved local id (entity not promoted) — skip
            conn.execute(
                "INSERT OR IGNORE INTO theme_occurrences "
                "(theme_id, entity_kind, entity_id, provenance, confidence) "
                "VALUES (?, ?, ?, 'auto', ?)",
                (theme_id, kind, entity_id, confidence),
            )
        n += 1
    conn.commit()
    return n
```

- [ ] **Step 4: Modify `pipeline/stage7_load/__init__.py`** — add `from pipeline.stage7_load.themes import load_candidate_themes` and add `"load_candidate_themes"` to `__all__`.

- [ ] **Step 5: Run, verify PASS** — `uv run pytest tests/test_load_themes.py -v`.

- [ ] **Step 6: Commit**
```bash
git add pipeline/stage7_load/themes.py pipeline/stage7_load/__init__.py tests/test_load_themes.py
git commit -m "feat(load): load_candidate_themes — promote themes + resolve occurrences"
```

---

## Task 3: Extraction-output `themes` array

**Files:** Modify `pipeline/schemas/extract_output.py`; Test `tests/test_extract_output_themes.py`.

- [ ] **Step 1: Write the failing test `tests/test_extract_output_themes.py`**
```python
from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA as SCHEMA


def test_themes_is_an_optional_top_level_array():
    props = SCHEMA["properties"]
    assert "themes" in props
    assert props["themes"]["type"] == "array"
    # themes are capability-gated, so NOT in the always-required list
    assert "themes" not in SCHEMA["required"]


def test_theme_item_shape():
    item = SCHEMA["properties"]["themes"]["items"]
    assert "name" in item["properties"]
    assert "occurrences" in item["properties"]
```

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_extract_output_themes.py -v`.

- [ ] **Step 3: Edit `pipeline/schemas/extract_output.py`** — add a `_THEME_SCHEMA` near the other `_*_SCHEMA` definitions and register it as an optional top-level `themes` array (do NOT add to `required`):
```python
_THEME_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["name", "citation", "justifications"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "occurrences": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["entity_kind", "entity_id"],
                "additionalProperties": False,
                "properties": {
                    "entity_kind": {"type": "string", "enum": ["person", "event", "group", "place", "chapter"]},
                    "entity_id": {"type": "string"},
                },
            },
        },
        "citation": _CITATION_SCHEMA,
        "justifications": {"type": "array"},
    },
}
```
Then in `EXTRACT_OUTPUT_SCHEMA["properties"]`, add: `"themes": {"type": "array", "items": _THEME_SCHEMA},`. Leave `required` unchanged (themes optional / capability-gated).

- [ ] **Step 4: Run, verify PASS** — `uv run pytest tests/test_extract_output_themes.py -v`.

- [ ] **Step 5: Commit**
```bash
git add pipeline/schemas/extract_output.py tests/test_extract_output_themes.py
git commit -m "feat(extract-schema): optional themes array (capability-gated)"
```

---

## Task 4: Capability-gated load wiring + export + knowledge

**Files:** Modify `pipeline/cli.py`; Tests covered by Tasks 1–3 + a gating assertion; knowledge.

- [ ] **Step 1: Wire the load command** — in `pipeline/cli.py`'s `load` command, after the existing `load_candidate_relations(...)` call, add capability-gated theme loading. Add the import `from pipeline.stage7_load import load_candidate_themes` (or extend the existing stage7_load import). Insert:
```python
        from pipeline.profile import PROFILES
        n_themes = 0
        if "themes" in PROFILES.get(profile, {}).get("capabilities", []):
            n_themes = load_candidate_themes(conn, pipeline_run_id=pipeline_run_id)
```
and include `themes={n_themes}` in the echo line.

- [ ] **Step 2: Verify gating with a test** — append to `tests/test_load_themes.py`:
```python
def test_history_profile_has_no_themes_capability():
    from pipeline.profile import PROFILES
    assert "themes" not in PROFILES["history"]["capabilities"]
    assert "themes" in PROFILES["cast"]["capabilities"]
```

- [ ] **Step 3: Verify themes export through the snapshot** — the canonical-only export enumerates tables dynamically, so `themes`/`theme_occurrences` are included automatically. Confirm with a quick check (no code change expected):
```bash
uv run python -c "
import sqlite3, pathlib
SCHEMA = pathlib.Path('pipeline/schemas/canonical_schema.sql').read_text('utf-8')
c = sqlite3.connect(':memory:'); c.executescript(SCHEMA)
names = {r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'candidate_%'\")}
assert 'themes' in names and 'theme_occurrences' in names, names
print('themes tables present in canonical (export-visible):', sorted(n for n in names if 'theme' in n))
"
```

- [ ] **Step 4: Full suite** — `uv run pytest -q` (green). Verify the CLI builds: `uv run python -c "from pipeline.cli import app"`.

- [ ] **Step 5: Knowledge updates (same-task rule)**
- `concepts/data-model/knowledge-graph.md` — add the `themes` entity + `theme_occurrences` link (theme ↔ person/event/group/place/chapter, with citation); new `entity_citations` kind `'theme'`.
- `concepts/pipeline/profiles.md` — themes capability: mined into `candidate_themes`, promoted by `load_candidate_themes`, load is gated on the profile's `themes` capability (history off, cast on).
- `concepts/pipeline/load-and-merge.md` — the theme loader (name-match, occurrence resolution via id maps, chapter passthrough).
- `concepts/pipeline/export-contract.md` — `themes`/`theme_occurrences` exported automatically; reader theme-view still deferred.
- Prepend `knowledge/log.md`.

- [ ] **Step 6: Commit**
```bash
git add pipeline/cli.py tests/test_load_themes.py knowledge/
git commit -m "feat(load): capability-gated theme loading; Plan 3b complete — themes capability"
```

---

## Self-Review
1. **Spec coverage (§3.3):** `themes`/`theme_occurrences` schema (T1) ✓; new entity_kind `'theme'` (T1) ✓; mined+persisted via loader (T2) ✓; extraction schema (T3) ✓; exported when capability on / gated load (T4) ✓; reader theme-view deferred (unchanged, per spec). Actual theme *extraction* (the cast prompt emitting themes) is **Plan 3c**.
2. **Placeholders:** none — code shown for every step.
3. **Symbol consistency:** `load_candidate_themes(conn, pipeline_run_id)`, tables `themes`/`theme_occurrences`/`candidate_themes`, theme id `thm:<slug>`, occurrence resolution via `build_*_id_map` — consistent across tasks.
