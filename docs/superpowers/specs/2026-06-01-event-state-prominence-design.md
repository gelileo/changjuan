# Design — Event + State Prominence (Timeline & States default filters)

**Status:** Approved for planning
**Date:** 2026-06-01
**Repos:** `changjuan` (export-side) + `changjuan-reader` (UI)
**Extends:** the persons prominence feature (`2026-05-31-prominent-persons-default-list-prd.md`)

---

## 1. Summary

Add a "重要…/全部" default-filter toggle to the **纪年 (Timeline)** and **列国
(States)** pages, mirroring the Cast page. Like persons, importance is
**precomputed at export** — the reader only filters/sorts on precomputed columns,
it never computes prominence.

`deed_importance` (already in the bundle) is the single "narrative weight"
currency, aggregated along three axes:
- **person** prominence = SUM over the person's deeds (existing).
- **event** prominence = SUM over the event's participants (new).
- **state** prominence = SUM over the state's persons (new, for sort only).

## 2. Data contract (new in schema_version 4)

Bump `SCHEMA_VERSION` 3 → **4** in `pipeline/stage9_export.py`. Two new column
pairs, added by new passes in `pipeline/export_enrich.py` that run after
`build_deed_importance` (they derive from it):

### 2.1 `events.prominence` (REAL) + `events.prominence_tier` (TEXT)
- `prominence` = `COALESCE(SUM(deed_importance.score) over the event's participants, 0)`.
- `prominence_tier` ∈ `{major, notable, minor}`: rank all events by `prominence`
  DESC (stable tiebreak by id) → `major` = top `EVENT_MAJOR_TOP`, `notable` =
  next up to `EVENT_NOTABLE_TOP`, else `minor`.
- **Boundary promotion:** any `minor` event whose `type` ∈ `EVENT_BOUNDARY_TYPES`
  = `{即位, 继位, 嗣位, 立君, 弑君, 薨, 灭国}` is promoted to `notable`. These mark
  reign starts (即位/继位/嗣位/立君), reign ends (弑君/薨), and state ends (灭国);
  they are narratively pivotal even when participant-scores are low.
  `EVENT_BOUNDARY_TYPES` is a code constant (structural, like `TYPE_WEIGHTS`).
- Cutoffs (`EVENT_MAJOR_TOP`, `EVENT_NOTABLE_TOP`) are tunable; **initial target:
  dated `major ∪ notable` ≈ 400** of 1759 dated events. Verified at export
  (top-280-by-score ∪ 136 boundary types = 400 dated, measured 2026-06-01).

### 2.2 `states.prominence` (REAL) + `states.prominence_tier` (TEXT)
- `prominence` = `COALESCE(SUM(deed_importance.score) over persons WHERE state_id = this, 0)`
  — used for **sort order only** (big states first).
- `prominence_tier` ∈ `{major, minor}`: `major` iff the state is in a **curated
  allow-list**, else `minor`. No rank-based tiering for states (only 80, and the
  curated set is the editorial intent).
- The allow-list lives in `prominence_overrides.yaml` under a new top-level
  `states:` key (list of state names, matched on `states.name`). Initial list (14):
  **周, 郑, 鲁, 宋, 吴, 越, 晋, 赵, 魏, 齐, 楚, 秦, 韩, 燕**.

Both passes are idempotent (check `PRAGMA table_info` before `ALTER`), mirroring
`add_prominence`/`add_pinyin_columns`.

## 3. Reader behavior (changjuan-reader)

### 3.1 Pure selectors (`src/people/prominence.ts`)
Add siblings to `visiblePersonIds`, unit-tested the same way:
- `visibleEventIds(rows, bookmarkedIds, showAll)` — default keeps
  `tier IN (major,notable)` ∪ bookmarks; `showAll` → all.
- `visibleStateIds(rows, bookmarkedIds, showAll)` — default keeps `tier = major`
  ∪ bookmarks; `showAll` → all.
(Generalize the existing tier-set logic; null tier → treated as the hidden tier.)

### 3.2 Timeline (`app/timeline.tsx`)
- Query selects `prominence, prominence_tier`; keep `ORDER BY year_bce DESC`.
- Default visible = `tier IN (major,notable)` ∪ bookmarked event ids.
- "重要事件 / 全部" toggle (persisted), count hint `显示 N / 1759`.
- Search is intent-driven: searches **all** events regardless of toggle (mirrors Cast).

### 3.3 States (`app/states.tsx`)
- Query selects `prominence, prominence_tier`; sort `prominence DESC, name`.
- Default visible = `tier = major` ∪ bookmarked state ids.
- "重要列国 / 全部" toggle (persisted), count hint `显示 14 / 80`.

### 3.4 Persistence (`src/people/listPrefs.ts`)
Extend to **independent per-page** flags: `{ castShowAll, timelineShowAll,
statesShowAll }` (migrating the existing `showAll` → `castShowAll`, defaulting
absent keys to `false`). Each page flips only its own flag.

## 4. Build order
1. changjuan: implement both export passes + schema_version 4 + overrides `states:`
   key; update knowledge (`export-contract.md`) + `log.md`; verify counts; commit.
2. Re-export **`2026-06-v5`**; sanity-check (dated visible ≈ 400; 14 major states;
   `齐桓公` etc. unaffected). Re-vendor `graph.sqlite` + `manifest.json` into
   `changjuan-reader/assets/`; bump README vendor path.
3. changjuan-reader: selectors (TDD) → timeline + states toggles → listPrefs;
   `npm test` + web build; browser-verify acceptance criteria.

## 5. Acceptance criteria
- Timeline default lists ≈400 dated events; "全部" lists 1759. Major battles
  (城濮 etc.) present; a minor 即位/灭国 event present by default (boundary
  promotion); a routine low-score event absent by default, present under 全部.
- States default lists **14** (the curated set, sorted big-state-first); "全部"
  lists 80. A minor state (e.g. 滑) absent by default, present under 全部,
  present by default if bookmarked.
- Bookmarked event/state always visible even when its tier is hidden.
- Deep-link / direct nav to any event or state still opens (filter is list-only).
- Each page's toggle persists independently across reload.

## 6. Non-goals
- No reader-side recomputation of prominence (export-side only).
- No new event tiers beyond major/notable/minor; states stay binary (major/minor).
- Per-reign/state boundary detection beyond the `EVENT_BOUNDARY_TYPES` type-set
  (no reign-table cross-referencing in v1).
