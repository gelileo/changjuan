# Event + State Prominence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "重要…/全部" default-filter toggle to the Timeline (纪年) and States (列国) reader pages, backed by export-computed `events.prominence(_tier)` and `states.prominence(_tier)` (schema_version 4).

**Architecture:** Mirror the existing persons-prominence feature. Export-side: two new idempotent passes in `pipeline/export_enrich.py` derive event/state prominence from the existing `deed_importance` table; the reader only filters/sorts on the precomputed columns. Event tier is rank-based with reign/state-boundary type promotion; state tier is a curated 14-state allow-list.

**Tech Stack:** Python 3.14 / sqlite3 / uv / pytest (changjuan); React Native + Expo / TypeScript / jest (changjuan-reader).

**Two repos:** Tasks A1–A5 + D1 run in `changjuan/`. Tasks B1, C1–C6 run in `changjuan-reader/`. Do them in order — the reader tests need the schema-4 bundle vendored first.

---

## File Structure

**changjuan/**
- Modify: `pipeline/export_enrich.py` — add `add_event_prominence`, `add_state_prominence`, constants.
- Modify: `pipeline/stage9_export.py` — bump `SCHEMA_VERSION`, call the two passes.
- Modify: `data/books/dzl/prominence_overrides.yaml` — add `states:` allow-list.
- Modify: `tests/unit/test_export_enrich.py` — tests for the two passes.
- Modify: `knowledge/concepts/pipeline/export-contract.md` + `knowledge/log.md`.

**changjuan-reader/**
- Modify: `src/people/prominence.ts` — add `visibleEventIds`, `visibleStateIds`.
- Modify: `src/people/__tests__/prominence.test.ts` — tests for the two selectors.
- Modify: `src/people/listPrefs.ts` — per-page flags `{cast,timeline,states}`.
- Modify: `src/data/queries.ts` — add prominence cols to timeline + states SQL.
- Modify: `src/data/repo.ts` (`StateRow`) + `src/time/eventTime.ts` (`TimelineRow`) — add fields.
- Modify: `app/index.tsx` — migrate `prefs.showAll`→`prefs.cast`.
- Modify: `app/timeline.tsx`, `app/states.tsx` — toggle + count hint + filter.
- Modify: `assets/graph.sqlite` + `assets/manifest.json` + `README.md` — vendor v5.

---

## PART A — changjuan export (schema_version 4)

### Task A1: `add_event_prominence` pass

**Files:**
- Modify: `pipeline/export_enrich.py`
- Test: `tests/unit/test_export_enrich.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_export_enrich.py`:

```python
def test_add_event_prominence_tiers_with_boundary_promotion(tmp_path: Path) -> None:
    """deed-sum ranks event tiers; a low-score reign/state-boundary type is promoted."""
    from pipeline.export_enrich import add_event_prominence

    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE events (id TEXT PRIMARY KEY, type TEXT);")
        c.execute("CREATE TABLE deed_importance (event_id TEXT, person_id TEXT, score REAL);")
        c.executemany(
            "INSERT INTO events VALUES (?,?);",
            [("evt:big", "战"), ("evt:mid", "盟会"), ("evt:acc", "即位"), ("evt:dull", "朝议")],
        )
        c.executemany(
            "INSERT INTO deed_importance VALUES (?,?,?);",
            [("evt:big", "p1", 900.0), ("evt:big", "p2", 100.0), ("evt:mid", "p1", 50.0)],
        )  # evt:acc and evt:dull have no deeds -> score 0

    import pipeline.export_enrich as ee

    orig = (ee.EVENT_MAJOR_TOP, ee.EVENT_NOTABLE_TOP)
    ee.EVENT_MAJOR_TOP, ee.EVENT_NOTABLE_TOP = 1, 2
    try:
        add_event_prominence(graph)
    finally:
        ee.EVENT_MAJOR_TOP, ee.EVENT_NOTABLE_TOP = orig

    with sqlite3.connect(graph) as c:
        tiers = dict(c.execute("SELECT id, prominence_tier FROM events;"))
        scores = dict(c.execute("SELECT id, prominence FROM events;"))
    assert tiers["evt:big"] == "major"      # rank 1 (1000.0)
    assert tiers["evt:mid"] == "notable"    # rank 2 (50.0)
    assert tiers["evt:acc"] == "notable"    # rank 3 -> minor, promoted by 即位 boundary type
    assert tiers["evt:dull"] == "minor"     # rank 4, non-boundary, no deeds
    assert scores["evt:big"] == 1000.0
    assert scores["evt:dull"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_export_enrich.py::test_add_event_prominence_tiers_with_boundary_promotion -v`
Expected: FAIL — `ImportError: cannot import name 'add_event_prominence'`.

- [ ] **Step 3: Write minimal implementation**

In `pipeline/export_enrich.py`, after the existing `PROMINENCE_*` constants (near line 41), add:

```python
# Event prominence tiering. Rank-based on the per-event aggregate deed_importance;
# tunable. Reader timeline defaults to {major, notable}.
EVENT_MAJOR_TOP = 80  # ranks 1..80           -> 'major'
EVENT_NOTABLE_TOP = 280  # ranks 81..280       -> 'notable' (rest -> 'minor')
# Reign/state-boundary event types: narratively pivotal even when participant
# scores are low (accession, succession, regicide, ruler death, state end).
# Any 'minor' event of one of these types is promoted to 'notable' (always
# default-visible). Structural constant, like TYPE_WEIGHTS.
EVENT_BOUNDARY_TYPES = frozenset({"即位", "继位", "嗣位", "立君", "弑君", "薨", "灭国"})
```

Then add the function (place it after `add_prominence`):

```python
def add_event_prominence(graph_db: Path) -> None:
    """Add `events.prominence` (REAL) + `events.prominence_tier` (TEXT:
    'major' | 'notable' | 'minor') to the snapshot.

    `prominence` = SUM(deed_importance.score) over the event's participations — so
    this MUST run after build_deed_importance(). Tier is a rank-based cutoff
    (EVENT_MAJOR_TOP / EVENT_NOTABLE_TOP); then any 'minor' event whose `type` is a
    reign/state boundary (EVENT_BOUNDARY_TYPES) is promoted to 'notable' so reign
    starts/ends and state ends always survive the reader's default filter.
    """
    with sqlite3.connect(graph_db) as g:
        cols = [r[1] for r in g.execute("PRAGMA table_info(events);")]
        if "prominence" not in cols:
            g.execute("ALTER TABLE events ADD COLUMN prominence REAL;")
        if "prominence_tier" not in cols:
            g.execute("ALTER TABLE events ADD COLUMN prominence_tier TEXT;")

        scores = dict(
            g.execute(
                "SELECT event_id, COALESCE(SUM(score),0) FROM deed_importance GROUP BY event_id;"
            )
        )
        events = g.execute("SELECT id, type FROM events;").fetchall()
        ranked = sorted(events, key=lambda r: (-scores.get(r[0], 0.0), r[0]))
        tier: dict[str, str] = {}
        for i, (eid, _type) in enumerate(ranked):
            if i < EVENT_MAJOR_TOP:
                tier[eid] = "major"
            elif i < EVENT_NOTABLE_TOP:
                tier[eid] = "notable"
            else:
                tier[eid] = "minor"
        for eid, etype in events:
            if tier.get(eid) == "minor" and etype in EVENT_BOUNDARY_TYPES:
                tier[eid] = "notable"
        g.executemany(
            "UPDATE events SET prominence = ?, prominence_tier = ? WHERE id = ?;",
            [(round(scores.get(eid, 0.0), 2), tier[eid], eid) for eid, _ in events],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_export_enrich.py::test_add_event_prominence_tiers_with_boundary_promotion -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/export_enrich.py tests/unit/test_export_enrich.py
git commit -m "feat(export): event prominence pass (deed-sum rank + boundary-type promotion)"
```

### Task A2: `add_state_prominence` pass

**Files:**
- Modify: `pipeline/export_enrich.py`
- Test: `tests/unit/test_export_enrich.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_export_enrich.py`:

```python
def test_add_state_prominence_curated_allowlist(tmp_path: Path) -> None:
    """state score = deed-sum over its persons; tier = curated allow-list (major) else minor."""
    from pipeline.export_enrich import add_state_prominence

    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE states (id TEXT PRIMARY KEY, name TEXT);")
        c.execute("CREATE TABLE persons (id TEXT PRIMARY KEY, state_id TEXT);")
        c.execute("CREATE TABLE deed_importance (event_id TEXT, person_id TEXT, score REAL);")
        c.executemany("INSERT INTO states VALUES (?,?);", [("sta:晋", "晋"), ("sta:滑", "滑")])
        c.executemany(
            "INSERT INTO persons VALUES (?,?);",
            [("per:a", "sta:晋"), ("per:b", "sta:晋"), ("per:c", "sta:滑")],
        )
        c.executemany(
            "INSERT INTO deed_importance VALUES (?,?,?);",
            [("e1", "per:a", 300.0), ("e2", "per:b", 100.0), ("e3", "per:c", 5.0)],
        )
    overrides = tmp_path / "ov.yaml"
    overrides.write_text("states:\n  - 晋\n", encoding="utf-8")

    add_state_prominence(graph, overrides)

    with sqlite3.connect(graph) as c:
        tiers = dict(c.execute("SELECT id, prominence_tier FROM states;"))
        scores = dict(c.execute("SELECT id, prominence FROM states;"))
    assert tiers["sta:晋"] == "major"   # on the allow-list
    assert tiers["sta:滑"] == "minor"   # not on the allow-list
    assert scores["sta:晋"] == 400.0    # 300 + 100
    assert scores["sta:滑"] == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_export_enrich.py::test_add_state_prominence_curated_allowlist -v`
Expected: FAIL — `ImportError: cannot import name 'add_state_prominence'`.

- [ ] **Step 3: Write minimal implementation**

In `pipeline/export_enrich.py`, add after `add_event_prominence`:

```python
def add_state_prominence(graph_db: Path, overrides_path: Path | None = None) -> None:
    """Add `states.prominence` (REAL) + `states.prominence_tier` (TEXT:
    'major' | 'minor') to the snapshot.

    `prominence` = SUM(deed_importance.score) over the state's persons — used for
    SORT order only (big states first); MUST run after build_deed_importance().
    `prominence_tier` is 'major' iff the state's name is in the curated allow-list
    under the `states:` key of prominence_overrides.yaml, else 'minor'. Only ~80
    states, so the default reader list is a curated editorial set, not a rank.
    """
    major_names: set[str] = set()
    if overrides_path and overrides_path.exists():
        import yaml

        data = yaml.safe_load(overrides_path.read_text("utf-8")) or {}
        major_names = set(data.get("states") or [])

    with sqlite3.connect(graph_db) as g:
        cols = [r[1] for r in g.execute("PRAGMA table_info(states);")]
        if "prominence" not in cols:
            g.execute("ALTER TABLE states ADD COLUMN prominence REAL;")
        if "prominence_tier" not in cols:
            g.execute("ALTER TABLE states ADD COLUMN prominence_tier TEXT;")

        scores = dict(
            g.execute(
                "SELECT p.state_id, COALESCE(SUM(d.score),0) "
                "FROM deed_importance d JOIN persons p ON p.id = d.person_id "
                "WHERE p.state_id IS NOT NULL GROUP BY p.state_id;"
            )
        )
        states = g.execute("SELECT id, name FROM states;").fetchall()
        g.executemany(
            "UPDATE states SET prominence = ?, prominence_tier = ? WHERE id = ?;",
            [
                (round(scores.get(sid, 0.0), 2), "major" if name in major_names else "minor", sid)
                for sid, name in states
            ],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_export_enrich.py::test_add_state_prominence_curated_allowlist -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/export_enrich.py tests/unit/test_export_enrich.py
git commit -m "feat(export): state prominence pass (deed-sum sort + curated allow-list tier)"
```

### Task A3: Wire passes into export + bump schema_version + overrides

**Files:**
- Modify: `pipeline/stage9_export.py`
- Modify: `data/books/dzl/prominence_overrides.yaml`

- [ ] **Step 1: Bump SCHEMA_VERSION and import the passes**

In `pipeline/stage9_export.py`, change the import block (lines 19-24) to:

```python
from pipeline.export_enrich import (
    add_event_prominence,
    add_pinyin_columns,
    add_prominence,
    add_state_prominence,
    build_citations_table,
    build_deed_importance,
)
```

Change line 26 from:

```python
SCHEMA_VERSION = 3  # v3: persons.prominence + persons.prominence_tier
```

to:

```python
SCHEMA_VERSION = 4  # v4: events.prominence(_tier) + states.prominence(_tier)
```

- [ ] **Step 2: Call the two passes**

In `export_bundle`, after the existing `add_prominence(snap_path, prominence_overrides)` line, add:

```python
    add_event_prominence(snap_path)  # after deed_importance (derives from it)
    add_state_prominence(snap_path, prominence_overrides)  # curated states: allow-list
```

- [ ] **Step 3: Add the `states:` allow-list to overrides**

Append to `data/books/dzl/prominence_overrides.yaml`:

```yaml

# Curated default-visible states for the reader's 列国 list (add_state_prominence).
# tier='major' for these names; everything else 'minor' (hidden unless 全部 /
# bookmarked). Matched on states.name. Edit freely + re-export.
states:
  - 周
  - 郑
  - 鲁
  - 宋
  - 吴
  - 越
  - 晋
  - 赵
  - 魏
  - 齐
  - 楚
  - 秦
  - 韩
  - 燕
```

- [ ] **Step 4: Run the full export test suite**

Run: `uv run pytest tests/unit/test_export_enrich.py tests/unit/test_stage9_export.py -v`
Expected: PASS (all, including the two new tests).

- [ ] **Step 5: Commit**

```bash
git add pipeline/stage9_export.py data/books/dzl/prominence_overrides.yaml
git commit -m "feat(export): schema_version 4 — wire event+state prominence; states allow-list"
```

### Task A4: Update knowledge docs

**Files:**
- Modify: `knowledge/concepts/pipeline/export-contract.md`
- Modify: `knowledge/log.md`

- [ ] **Step 1: Add a section to export-contract.md**

After the `persons.prominence` section (ends ~line 81), add:

```markdown
## `events.prominence` + `states.prominence`: Timeline & States default filters

Added in schema_version **4** by `pipeline/export_enrich.py::add_event_prominence`
and `add_state_prominence`, both running after `build_deed_importance`.

- **events**: `prominence` (REAL) = `SUM(deed_importance.score)` over the event's
  participations; `prominence_tier` = rank-based `major` (top `EVENT_MAJOR_TOP`) /
  `notable` (..`EVENT_NOTABLE_TOP`) / `minor`, then any `minor` event whose `type`
  ∈ `EVENT_BOUNDARY_TYPES` (即位/继位/嗣位/立君/弑君/薨/灭国) is promoted to
  `notable` so reign/state boundaries always survive the default filter. Reader
  Timeline defaults to `tier IN ('major','notable')` (~400 of 1759 dated events).
- **states**: `prominence` (REAL) = `SUM(deed_importance.score)` over the state's
  persons (sort only, big states first); `prominence_tier` = `major` iff the
  state's name is in the `states:` allow-list of `prominence_overrides.yaml`, else
  `minor`. Reader 列国 defaults to `tier = 'major'` (the curated 14).

Both mirror the persons contract: per-user favorites are NOT stored here; the
reader unions its local bookmark ids with the prominent set at read time.
```

Update the "What would invalidate this article" / version-history section: add a v4 entry noting events+states prominence columns and bump the "beyond v4" line.

- [ ] **Step 2: Append a log.md entry**

```markdown

## 2026-06-01 — feat(export): event + state prominence (schema_version 4)

Added events.prominence(_tier) + states.prominence(_tier) for the reader's
Timeline/States default filters (design:
docs/superpowers/specs/2026-06-01-event-state-prominence-design.md). Event tier
= deed-sum rank with reign/state-boundary type promotion (即位/继位/嗣位/立君/
弑君/薨/灭国); state tier = curated 14-state allow-list in prominence_overrides.yaml.

Articles touched: concepts/pipeline/export-contract.md.
```

- [ ] **Step 3: Commit**

```bash
git add knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "docs(export-contract): event+state prominence (schema_version 4)"
```

### Task A5: Re-export v5 + sanity-check

**Files:** none (produces a gitignored bundle).

- [ ] **Step 1: Run the export**

Run: `uv run changjuan export 2026-06-v5`
Expected: `export bundle written to .../data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v5`.

- [ ] **Step 2: Sanity-check the bundle**

Run:
```bash
B=data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v5/graph.sqlite
sqlite3 "$B" "SELECT json_extract(readfile('data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v5/manifest.json'),'\$.schema_version');" 2>/dev/null || python3 -c "import json;print(json.load(open('data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v5/manifest.json'))['schema_version'])"
sqlite3 "$B" "SELECT COUNT(*) FROM events WHERE json_extract(date_json,'\$.year_bce') IS NOT NULL AND prominence_tier IN ('major','notable');"
sqlite3 "$B" "SELECT name FROM states WHERE prominence_tier='major' ORDER BY prominence DESC;"
```
Expected: schema_version `4`; dated major+notable events ≈ **400**; exactly the **14** allow-list states listed (big-state-first).

- [ ] **Step 3: No commit** (bundle is gitignored). If the ~400 target is off by a lot, adjust `EVENT_NOTABLE_TOP` in `export_enrich.py`, re-run Task A3 Step 4 tests + re-export, and amend the A3 commit.

---

## PART B — Re-vendor into the reader

### Task B1: Vendor v5 bundle

**Files (changjuan-reader/):**
- Modify: `assets/graph.sqlite` (gitignored), `assets/manifest.json`, `README.md`

- [ ] **Step 1: Create a branch + copy the bundle**

```bash
cd ../changjuan-reader
git switch -c feat/timeline-states-prominence
SRC=../changjuan/data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v5
cp "$SRC/graph.sqlite" assets/graph.sqlite
cp "$SRC/manifest.json" assets/manifest.json
```

- [ ] **Step 2: Verify the new columns are present**

Run: `sqlite3 assets/graph.sqlite "SELECT COUNT(*) FROM pragma_table_info('events') WHERE name='prominence_tier'; SELECT COUNT(*) FROM pragma_table_info('states') WHERE name='prominence_tier';"`
Expected: `1` and `1`.

- [ ] **Step 3: Confirm existing tests + build still pass on the new bundle**

Run: `npm test && npx expo export -p web`
Expected: 67 tests pass; build `Exported: dist`.

- [ ] **Step 4: Update README vendor path**

In `README.md`, change the live-bundle line + `cp` command from `…-2026-06-v4` to `…-2026-06-v5` (schema_version 4 — adds events/states prominence).

- [ ] **Step 5: Commit**

```bash
git add assets/manifest.json README.md
git commit -m "chore(assets): vendor v5 bundle (schema_version 4: event+state prominence)"
```

---

## PART C — Reader UI (changjuan-reader/, on feat/timeline-states-prominence)

### Task C1: Selectors `visibleEventIds` + `visibleStateIds`

**Files:**
- Modify: `src/people/prominence.ts`
- Test: `src/people/__tests__/prominence.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `src/people/__tests__/prominence.test.ts`:

```typescript
import { visibleEventIds, visibleStateIds } from "../prominence";

const ev = (id: string, tier: "major" | "notable" | "minor" | null) => ({ id, prominence_tier: tier });

test("visibleEventIds: default keeps major+notable, unions bookmarks, drops minor", () => {
  const rows = [ev("e:a", "major"), ev("e:b", "notable"), ev("e:c", "minor"), ev("e:d", "minor")];
  expect([...visibleEventIds(rows, [], false)].sort()).toEqual(["e:a", "e:b"]);
  expect([...visibleEventIds(rows, ["e:c"], false)].sort()).toEqual(["e:a", "e:b", "e:c"]);
  expect([...visibleEventIds(rows, [], true)].sort()).toEqual(["e:a", "e:b", "e:c", "e:d"]);
});

const st = (id: string, tier: "major" | "minor" | null) => ({ id, prominence_tier: tier });

test("visibleStateIds: default keeps only major, unions bookmarks", () => {
  const rows = [st("s:晋", "major"), st("s:滑", "minor"), st("s:息", "minor")];
  expect([...visibleStateIds(rows, [], false)].sort()).toEqual(["s:晋"]);
  expect([...visibleStateIds(rows, ["s:息"], false)].sort()).toEqual(["s:晋", "s:息"]);
  expect([...visibleStateIds(rows, [], true)].sort()).toEqual(["s:息", "s:晋", "s:滑"]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx jest src/people/__tests__/prominence.test.ts`
Expected: FAIL — `visibleEventIds`/`visibleStateIds` not exported.

- [ ] **Step 3: Implement**

Append to `src/people/prominence.ts`:

```typescript
export interface EventProminenceRow {
  id: string;
  prominence_tier: "major" | "notable" | "minor" | null;
}

/** Event ids visible in the Timeline browse list. showAll → all; else
 * tier IN ('major','notable') unioned with bookmarked ids. */
export function visibleEventIds(
  rows: EventProminenceRow[],
  bookmarkedIds: Iterable<string>,
  showAll: boolean,
): Set<string> {
  if (showAll) return new Set(rows.map((r) => r.id));
  const bookmarked = new Set(bookmarkedIds);
  const visible = new Set<string>();
  for (const r of rows) {
    if (PROMINENT_TIERS.has(r.prominence_tier ?? "minor") || bookmarked.has(r.id)) {
      visible.add(r.id);
    }
  }
  return visible;
}

export interface StateProminenceRow {
  id: string;
  prominence_tier: "major" | "minor" | null;
}

/** State ids visible in the 列国 browse list. showAll → all; else the curated
 * tier='major' set unioned with bookmarked ids. */
export function visibleStateIds(
  rows: StateProminenceRow[],
  bookmarkedIds: Iterable<string>,
  showAll: boolean,
): Set<string> {
  if (showAll) return new Set(rows.map((r) => r.id));
  const bookmarked = new Set(bookmarkedIds);
  const visible = new Set<string>();
  for (const r of rows) {
    if (r.prominence_tier === "major" || bookmarked.has(r.id)) visible.add(r.id);
  }
  return visible;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx jest src/people/__tests__/prominence.test.ts`
Expected: PASS (all, including the original persons tests).

- [ ] **Step 5: Commit**

```bash
git add src/people/prominence.ts src/people/__tests__/prominence.test.ts
git commit -m "feat(reader): visibleEventIds + visibleStateIds selectors"
```

### Task C2: Per-page `listPrefs`

**Files:**
- Modify: `src/people/listPrefs.ts`
- Modify: `app/index.tsx` (migrate `showAll` → `cast`)

- [ ] **Step 1: Rewrite listPrefs with per-page flags**

Replace the entire body of `src/people/listPrefs.ts` with:

```typescript
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useState } from "react";

export type ListPage = "cast" | "timeline" | "states";

/** Persisted per-page "show all rather than prominent-only" flags. */
export interface ListPrefs {
  cast: boolean;
  timeline: boolean;
  states: boolean;
}

const KEY = "changjuan.personList";
const DEFAULTS: ListPrefs = { cast: false, timeline: false, states: false };

export async function loadListPrefs(): Promise<ListPrefs> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const p = JSON.parse(raw) as Partial<ListPrefs> & { showAll?: boolean };
    return {
      cast: p.cast ?? p.showAll ?? false, // migrate legacy {showAll}
      timeline: p.timeline ?? false,
      states: p.states ?? false,
    };
  } catch {
    return DEFAULTS;
  }
}
async function saveListPrefs(p: ListPrefs): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* ignore */
  }
}
export function useListPrefs() {
  const [prefs, setPrefs] = useState<ListPrefs>(DEFAULTS);
  useEffect(() => {
    let on = true;
    loadListPrefs().then((p) => {
      if (on) setPrefs(p);
    });
    return () => {
      on = false;
    };
  }, []);
  const setShowAll = useCallback(
    (page: ListPage, value: boolean) =>
      setPrefs((c) => {
        const n = { ...c, [page]: value };
        void saveListPrefs(n);
        return n;
      }),
    [],
  );
  return { prefs, setShowAll };
}
```

- [ ] **Step 2: Update the Cast page to the new shape**

In `app/index.tsx`: change `const { prefs, setShowAll } = useListPrefs();` usage —
- replace `prefs.showAll` with `prefs.cast` (2 occurrences: the `rows` memo guard and the toggle's `selected` checks),
- replace `setShowAll(opt.value)` with `setShowAll("cast", opt.value)`,
- in the toggle's `backgroundColor`/`color` ternaries replace `prefs.showAll === opt.value` with `prefs.cast === opt.value`.

- [ ] **Step 3: Type-check + run tests**

Run: `npx tsc --noEmit && npm test`
Expected: clean; 69 tests pass (67 + 2 new selector tests).

- [ ] **Step 4: Commit**

```bash
git add src/people/listPrefs.ts app/index.tsx
git commit -m "feat(reader): per-page listPrefs (cast/timeline/states), migrate legacy showAll"
```

### Task C3: Add prominence columns to timeline + states queries

**Files:**
- Modify: `src/data/queries.ts`
- Modify: `src/time/eventTime.ts` (`TimelineRow`)
- Modify: `src/data/repo.ts` (`StateRow`)

- [ ] **Step 1: Update the timeline SQL**

In `src/data/queries.ts`, replace `TIMELINE_ALL_SQL` and `TIMELINE_BY_STATE_SQL` with versions that also select `prominence_tier` (and keep ordering):

```typescript
export const TIMELINE_ALL_SQL =
  `SELECT id, type, summary, primary_place_id, prominence_tier,
          json_extract(date_json,'$.year_bce') AS year_bce
   FROM events
   WHERE json_extract(date_json,'$.year_bce') IS NOT NULL
   ORDER BY year_bce DESC, id;`;

export const TIMELINE_BY_STATE_SQL =
  `SELECT DISTINCT e.id, e.type, e.summary, e.primary_place_id, e.prominence_tier,
          json_extract(e.date_json,'$.year_bce') AS year_bce
   FROM events e
   JOIN event_participants ep ON ep.event_id = e.id
   JOIN persons p ON p.id = ep.person_id
   WHERE p.state_id = ? AND json_extract(e.date_json,'$.year_bce') IS NOT NULL
   ORDER BY year_bce DESC, e.id;`;
```

- [ ] **Step 2: Update the states SQL**

In `src/data/queries.ts`, replace `STATES_LIST_SQL` with:

```typescript
export const STATES_LIST_SQL =
  `SELECT id, name, ruling_clan, type, prominence, prominence_tier
   FROM states ORDER BY prominence DESC, name;`;
```

- [ ] **Step 3: Extend the row types**

In `src/time/eventTime.ts`, add a field to `TimelineRow`:

```typescript
export interface TimelineRow {
  id: string;
  type: string;
  summary: string | null;
  year_bce: number;
  primary_place_id: string | null;
  prominence_tier: "major" | "notable" | "minor" | null;
}
```

In `src/data/repo.ts`, extend `StateRow`:

```typescript
export interface StateRow {
  id: string;
  name: string;
  ruling_clan: string | null;
  type: string | null;
  prominence: number | null;
  prominence_tier: "major" | "minor" | null;
}
```

- [ ] **Step 4: Type-check + run tests**

Run: `npx tsc --noEmit && npm test`
Expected: clean; 69 tests pass (the node bundle query tests read the v5 bundle, which has the columns).

- [ ] **Step 5: Commit**

```bash
git add src/data/queries.ts src/time/eventTime.ts src/data/repo.ts
git commit -m "feat(reader): select prominence cols in timeline + states queries"
```

### Task C4: Timeline toggle + count hint + filter

**Files:**
- Modify: `app/timeline.tsx`

- [ ] **Step 1: Add imports + hooks**

In `app/timeline.tsx`, add imports near the others:

```typescript
import { useListPrefs } from "../src/people/listPrefs";
import { useBookmarks } from "../src/bookmarks/store";
import { visibleEventIds } from "../src/people/prominence";
```

Inside `TimelineScreen`, after the existing `useState` hooks, add:

```typescript
  const { prefs, setShowAll } = useListPrefs();
  const { list: bookmarks } = useBookmarks();
  const bookmarkedEventIds = useMemo(
    () => bookmarks.filter((b) => b.kind === "event").map((b) => b.id),
    [bookmarks],
  );
```

- [ ] **Step 2: Apply the prominence filter before grouping**

Replace the `sections` useMemo (lines 45-58) with:

```typescript
  // Prominence/search filter → group by year. Search is intent-driven (matches
  // ALL events regardless of the toggle); otherwise the default obeys the toggle.
  const visibleCount = useMemo(() => {
    const qTrimmed = q.trim().toLowerCase();
    if (qTrimmed) return null; // count hint only meaningful in browse mode
    if (prefs.timeline) return rows.length;
    const visible = visibleEventIds(rows, bookmarkedEventIds, false);
    return rows.filter((r) => visible.has(r.id)).length;
  }, [rows, q, prefs.timeline, bookmarkedEventIds]);

  const sections = useMemo(() => {
    const qTrimmed = q.trim().toLowerCase();
    let filtered = rows;
    if (qTrimmed) {
      filtered = rows.filter(
        (r) =>
          (r.summary ?? "").toLowerCase().includes(qTrimmed) ||
          r.type.toLowerCase().includes(qTrimmed),
      );
    } else if (!prefs.timeline) {
      const visible = visibleEventIds(rows, bookmarkedEventIds, false);
      filtered = rows.filter((r) => visible.has(r.id));
    }
    return groupByYear(filtered).map((g) => ({
      title: yearLabel(g.year_bce),
      data: g.rows,
    }));
  }, [rows, q, prefs.timeline, bookmarkedEventIds]);
```

- [ ] **Step 3: Add the toggle + count hint UI**

In the returned JSX, immediately after the search-box `</View>` (line 87) and before the state-filter `ScrollView`, insert:

```tsx
      {/* Prominence toggle + count hint */}
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          paddingHorizontal: 12,
          paddingBottom: 6,
        }}
      >
        <View
          style={{
            flexDirection: "row",
            borderWidth: 1,
            borderColor: "#c8b89a",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          {[
            { label: "重要事件", value: false },
            { label: "全部", value: true },
          ].map((opt) => (
            <Pressable
              key={String(opt.value)}
              accessibilityLabel={opt.label}
              onPress={() => setShowAll("timeline", opt.value)}
              style={{
                paddingVertical: 6,
                paddingHorizontal: 14,
                backgroundColor: prefs.timeline === opt.value ? "#b8860b" : "#fff",
              }}
            >
              <Text
                style={{
                  fontSize: 13,
                  fontWeight: "600",
                  color: prefs.timeline === opt.value ? "#fff" : "#7a6040",
                }}
              >
                {opt.label}
              </Text>
            </Pressable>
          ))}
        </View>
        {visibleCount !== null && (
          <Text style={{ fontSize: 12, color: "#7a6040" }}>
            显示 {visibleCount} / {rows.length}
          </Text>
        )}
      </View>
```

- [ ] **Step 4: Type-check + build**

Run: `npx tsc --noEmit && npx expo export -p web`
Expected: clean; `Exported: dist`.

- [ ] **Step 5: Commit**

```bash
git add app/timeline.tsx
git commit -m "feat(reader): 重要事件/全部 toggle on Timeline"
```

### Task C5: States toggle + count hint + filter

**Files:**
- Modify: `app/states.tsx`

- [ ] **Step 1: Add imports + hooks**

In `app/states.tsx`, add imports:

```typescript
import { Pressable as _P } from "react-native"; // (Pressable already imported; skip if present)
import { useListPrefs } from "../src/people/listPrefs";
import { useBookmarks } from "../src/bookmarks/store";
import { visibleStateIds } from "../src/people/prominence";
```

(Real change: ensure `useListPrefs`, `useBookmarks`, `visibleStateIds` are imported; `Pressable`/`Text`/`View` already are.)

Inside `StatesScreen`, after `const [q, setQ] = useState("")`, add:

```typescript
  const { prefs, setShowAll } = useListPrefs();
  const { list: bookmarks } = useBookmarks();
  const bookmarkedStateIds = useMemo(
    () => bookmarks.filter((b) => b.kind === "state").map((b) => b.id),
    [bookmarks],
  );
```

- [ ] **Step 2: Apply the prominence filter**

Replace the `rows` useMemo (lines 15-20) with:

```typescript
  const rows = useMemo<StateRow[]>(() => {
    if (!states) return [];
    const trimmed = q.trim();
    if (trimmed) return states.filter((s) => s.name.includes(trimmed)); // search: all
    if (prefs.states) return states;
    const visible = visibleStateIds(states, bookmarkedStateIds, false);
    return states.filter((s) => visible.has(s.id));
  }, [states, q, prefs.states, bookmarkedStateIds]);
```

- [ ] **Step 3: Add the toggle + count hint UI**

In the returned JSX, immediately after the search-box `</View>` (line 49) and before the `FlatList`, insert:

```tsx
      {/* Prominence toggle + count hint */}
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          paddingHorizontal: 12,
          paddingBottom: 6,
        }}
      >
        <View
          style={{
            flexDirection: "row",
            borderWidth: 1,
            borderColor: "#c8b89a",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          {[
            { label: "重要列国", value: false },
            { label: "全部", value: true },
          ].map((opt) => (
            <Pressable
              key={String(opt.value)}
              accessibilityLabel={opt.label}
              onPress={() => setShowAll("states", opt.value)}
              style={{
                paddingVertical: 6,
                paddingHorizontal: 14,
                backgroundColor: prefs.states === opt.value ? "#b8860b" : "#fff",
              }}
            >
              <Text
                style={{
                  fontSize: 13,
                  fontWeight: "600",
                  color: prefs.states === opt.value ? "#fff" : "#7a6040",
                }}
              >
                {opt.label}
              </Text>
            </Pressable>
          ))}
        </View>
        {q.trim() === "" && (
          <Text style={{ fontSize: 12, color: "#7a6040" }}>
            显示 {rows.length} / {states.length}
          </Text>
        )}
      </View>
```

- [ ] **Step 4: Type-check + build**

Run: `npx tsc --noEmit && npx expo export -p web`
Expected: clean; `Exported: dist`.

- [ ] **Step 5: Commit**

```bash
git add app/states.tsx
git commit -m "feat(reader): 重要列国/全部 toggle on States"
```

### Task C6: Browser-verify + finish branch

**Files:** none (verification).

- [ ] **Step 1: Serve the build**

```bash
npx serve -s dist -l 4192 &
```

- [ ] **Step 2: Verify Timeline** (Playwright MCP) at `http://localhost:4192/timeline`:
  - Default count hint `显示 ~400 / 1759`; clicking 全部 → `显示 1759 / 1759` (label "全部" via `getByLabel`).
  - A reign-boundary event (e.g. a 即位/灭国) appears by default; a routine low-score 朝议 absent by default, present under 全部.
  - Reload → toggle persists (`localStorage["changjuan.personList"]` has `timeline:true`).

- [ ] **Step 3: Verify States** at `http://localhost:4192/states`:
  - Default lists 14 states (周郑鲁宋吴越晋赵魏齐楚秦韩燕), big-state-first; count hint `显示 14 / 80`; 全部 → `显示 80 / 80`.
  - A minor state (滑) absent by default, present under 全部; bookmark 滑 (on its page) → present by default, count `15 / 80`.
  - Cast page still works (`prefs.cast` migration) — default ~263.

- [ ] **Step 4: Stop server + run full check**

Run: `pkill -f "serve -s dist -l 4192"; npm test && npx tsc --noEmit`
Expected: 69 tests pass; tsc clean.

- [ ] **Step 5: Finish the branch** (superpowers:finishing-a-development-branch): verify tests on merged result, `git merge --ff-only`, delete branch.

---

## PART D — changjuan housekeeping

### Task D1: (already covered) 

The changjuan commits land on `main` in Tasks A1–A4. No separate task; ensure `uv run pytest -q` is green before the reader work (the pre-existing `test_curator_smoke` failure is unrelated — see knowledge/log.md).

---

## Self-Review notes
- **Spec coverage:** event score+tier+boundary promotion (A1), state score+curated tier (A2), schema_version 4 + wiring + overrides (A3), docs (A4), v5 export (A5), vendor (B1), selectors (C1), per-page persistence (C2), queries/types (C3), Timeline UI (C4), States UI (C5), acceptance criteria (C6). All spec sections mapped.
- **Type consistency:** `visibleEventIds`/`visibleStateIds` signatures match their tests and call sites; `TimelineRow.prominence_tier` + `StateRow.prominence(_tier)` match the SQL columns; `ListPrefs` `{cast,timeline,states}` matches all three call sites and the `setShowAll(page,value)` signature.
- **Boundary-types constant** identical in spec, A1 code, and A4 doc.
