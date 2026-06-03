---
title: Dates, reigns, and inference kinds
type: concept
area: data-model
updated: 2026-06-02
status: thin
load_bearing: true
references:
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/reign_table.json
  - pipeline/dates.py
  - tests/unit/test_dates_relative.py
  - data/reigns/**
---

## What this is

Every Date in changjuan is structured: `{year_bce, uncertainty, year_bce_end?, original, era, inference_kind, relative_anchor_event_id?}`. The `inference_kind` records *how* a BCE year was derived — not all dates in 东周列国志 are equally trustworthy. The bundled `pipeline/reign_table.json` provides the canonical 鲁公 and 周王 chronologies (722 BCE – 468 BCE for 鲁, 770 – 476 BCE for 周) so explicit-reign citations like 鲁僖公二十八年 dereference deterministically to 632 BCE.

## Why this shape, not the alternatives

Storing only `year_bce` would lose the distinction between a citation like 鲁僖公二十八年 (high trust) and a relative reference like 其年 (trust inherited from the anchor) or an era-only mention 春秋末 (range, not point). The pipeline's confidence scoring penalizes anything other than explicit-reign citations; without `inference_kind`, that penalty has nothing to attach to.

## What would invalidate this article

- A reign-year citation in the corpus that the reign table can't dereference (i.e., another state's reigns we haven't tabulated). Promotion path: add the state's reign block alongside `lu` and `zhou`.
- A new `inference_kind` becoming necessary as the corpus surfaces new date forms.

## `parse_date` — current surface

`pipeline.dates.parse_date(original: str, anchor: DateDict | None = None) -> DateDict` dispatches to pattern-matching helpers in priority order. The function **never raises** — unrecognized inputs return `inference_kind="unknown"` with `year_bce=None`. Dispatch order:

1. `_try_lu` — `鲁X公N年` / lenient prefixes
2. `_try_zhou` — `周X王N年` for all 13 tabulated Zhou kings (平王 through 敬王)
3. `_try_relative` — relative refs (其年/明年/次年/去年/前年/是岁/是年/是+season); requires `anchor` with non-None `year_bce`; falls through to `_unknown` when anchor absent
4. `_try_era` — era-range strings (春秋初/早期/中期/末/晚期, 战国初/早期/中期/末/晚期); returns `uncertainty="range"` with midpoint as `year_bce` and `year_bce_end`
5. `_unknown` — fallback; `year_bce=None`, `uncertainty="point"`

The Chinese numeral parser (`_cn_to_int`) covers 元 and compound forms up to ~60.

## `relative_to_prior_event` resolution

Phase 1 shipped `parse_date(original, anchor=...)` — given an anchor DateDict
with a non-null `year_bce`, it resolves a relative token (其年/明年/次年/
去年/前年/是岁/是年/是+season) via the `_RELATIVE_OFFSETS` table in BCE
arithmetic ("明年" = −1 because BCE years decrease as time advances).

Phase 2 adds `resolve_relative_dates(records, conn)` — a record-walking
wrapper that maintains a rolling anchor across a chunk's records and
dereferences relative dates in order.

**Explicit cross-chunk anchor.** A record's `date.relative_anchor_event_id`
(optional field) names a specific anchor event; resolution looks it up via
`anchor_lookup(conn, event_id)` (default: query canonical events). Explicit
anchor overrides walkback. Cycle detection rejects an anchor chain that
visits the resolving record. Dangling anchors raise `RelativeResolveError`.

**Offset resolution for the explicit-anchor path.** If `original` is a known
token in `_RELATIVE_OFFSETS` → use that. Else, if the curator-supplied
`offset_override` is passed (calendar-years-later) → use `−offset_override`
(negated for BCE). Else → record's year_bce stays null.

### Parenthesized narrative notes — agent convention

The extraction skill emits `original: "(narrative-note)"` (parenthesized) when
no explicit relative-time token (其年/明年/etc.) applies but the event clearly
belongs to the same narrative beat as the prior anchor. The walkback treats
these as offset=0 (same year as the rolling anchor).

Examples emitted by the skill:
- `original: "(千亩之后)"` — "after 千亩" — meaning same-year continuation
- `original: "(料民回京时)"` — "when the 料民 team returned" — same-year
- `original: "(童谣朝议同时)"` — "at the time of the 童谣 council" — same-year

Empty parens `()` are NOT treated as offset=0 — they carry no signal. Non-parenthesized
unknown strings (e.g., "某神秘时间") also return None so the resolver leaves
year_bce as null rather than silently inventing a date.

## Narrative-neighbor backfill (DB-wide)

`pipeline.dates.backfill_narrative_neighbor_dates(conn)` is a whole-DB pass that
fills the residual undated tail that per-chunk `resolve_relative_dates` cannot
reach. It walks **all** canonical events in narrative order — chapter then
paragraph, parsed directly from each event's `chk:dzl:<ch>:<para>` citations
(`MIN` over them; no denormalized table needed) — keeping a rolling "last dated
event". Any event still `year_bce=null` with `inference_kind ==
'relative_to_prior_event'` inherits the rolling year; 东周列国志 narrates
chronologically, so the nearest prior dated event IS what "relative to prior
event" means. The filled date keeps that `inference_kind` but records the
`relative_anchor_event_id` used and a **`narrative_inferred: true`** flag (honest,
low-trust provenance). `era_only` (genuine flashbacks, e.g. 秦文公之时 recounted
in a later chapter) and events without a `chk:` citation are **left undated** —
a narrative-neighbor year would be wrong for them. The pass mutates
`events.date_json` in place and is exposed as the `changjuan backfill-narrative-dates`
CLI verb (writes an `audit_log` row per change). This is what resolves cases like
the 干将莫邪 sword event ("其后吴王知干将匿剑" → 514, anchored to the adjacent 铸剑).

**Still out of scope.** Extending `_RELATIVE_OFFSETS` to numeric patterns
("其后N年"); dating `era_only` flashbacks to their referenced era. Per-chunk
`resolve_relative_dates` remains the first-pass resolver; the backfill is the
deterministic cleanup for what it leaves null. See `concepts/pipeline/incremental.md`.

## `explicit_reign_other` — per-state YAML resolver (Phase 4 Task 2)

For any state other than 鲁 or 周, `resolve_explicit_reign_other(state_id, ruler_ref, reign_year)` reads a per-state YAML from `data/reigns/<slug>.yaml` where the slug is the `state_id` with `:` replaced by `_` (e.g. `sta:jin` → `sta_jin.yaml`).

**Ruler matching** tries three fields in each ruler entry, in order: `id` (fully-qualified canonical id), `posthumous_name` (posthumous title such as 武公), `given_name`. Returns None with a structured `log.warning` if:

- The YAML file doesn't exist (`reign_table_missing`).
- No ruler entry matches the `ruler_ref` (`ruler_ref_not_found`).
- More than one ruler entry matches (`ruler_ref_ambiguous`).

**Out-of-range reign years** (computed `year_bce < reign_end_bce`) still return the computed value but emit a `reign_year_out_of_range` warning. The value is preserved so downstream review can decide; it is not silently dropped.

**Reign-year arithmetic** is identical to the 鲁/周 path: `year_bce = reign_start_bce - (reign_year - 1)`.

**`parse_date` dispatch (Phase 4 Task 7 integration):** `parse_date` recognizes the `<state-prefix><ruler-suffix>X年` pattern (e.g., `晋文公七年`, `齐桓公九年`, `郑庄公二十二年`) via `_try_other` and routes the call to `resolve_explicit_reign_other`. The state prefix maps via `_STATE_PREFIX_TO_ID` (16 known states); the dispatcher tries the ruler_ref in two forms — full (state-prefix + suffix, e.g. `晋文公`) and suffix-only (e.g. `文公`) — falling back to `_unknown` if neither matches. Skips `鲁`/`周` (handled by `_try_lu`/`_try_zhou` against the JSON reign table).

**YAML schema** (committed under `data/reigns/`):

```yaml
state_id: sta:<slug>
state_name: <Chinese name>
sources: [<source>]
rulers:
  - id: <string>
    posthumous_name: <string>
    given_name: <string>
    reign_start_bce: <int>
    reign_end_bce: <int>
    sources: [<source>]
    confidence: high|medium|low
    notes: <string>
```

**`CHANGJUAN_REIGN_DIR` env var** overrides the default `data/reigns/` directory. Tests use this to redirect the loader to a `tmp_path`-based copy of the synthetic fixture. The module-level `_REIGN_YAML_CACHE` dict is cleared between tests via `dates._REIGN_YAML_CACHE.clear()`.

**Phase 4 reign coverage** (Phase 4 Task 5 + post-review trim, committed under `data/reigns/`):

| state | rulers | BCE span | source |
|---|---|---|---|
| `sta:zheng` | 24 | 770-375 | 《史记·郑世家》 |
| `sta:wei` | 23 | 812-451 | 《史记·卫康叔世家》 |
| `sta:qi` | 27 | 794-221 | 《史记·齐太公世家》 + 《史记·田敬仲完世家》 |
| `sta:jin` | 28 | 780-389 | 《史记·晋世家》 |
| `sta:qin` | 32 | 777-221 | 《史记·秦本纪》 |
| `sta:song` | 18 | 799-470 | 《史记·宋微子世家》 |
| `sta:chen` | 14 | 754-478 | 《史记·陈杞世家》 |
| `sta:cai` | 15 | 762-472 | 《史记·管蔡世家》 |
| `sta:shen` | 1 | 770-745 | 《史记·周本纪》 (placeholder; see notes) |

Drafted inline following the schema above; curator-trimmed during Phase 4 Task 5 review to remove 23 out-of-scope 战国-era uncertain entries (wrong data is worse than missing data — Phase 4 covers 770-700 BCE; 战国 entries are restored in Phase 5+ with fresh verification when needed). Phase 5+ also adds states beyond this set (楚, 燕, 吴, 越, etc.) as multi-chapter extraction surfaces references.

## First commitments

- `pipeline/reign_table.json` source: 杨伯峻《春秋左传注》, cross-checked against 史记·十二诸侯年表.
- `pipeline/dates.py` parsers handle: `explicit_reign_lu`, `explicit_reign_zhou`, `explicit_reign_other` (implemented Phase 4 Task 2), `relative_to_prior_event`, `era_only`, `unknown`.
- Reign-year arithmetic: BCE year = `start_bce - (N - 1)` for reign year N.

## Date-quality audit tools (read-only scan + interactive resolve)

`scripts/scan-dates` (read-only) collects suspect deed dates into a ranked
`data/date_issues.yaml` (gitignored). Checks: **reign_window** — an event's
`year_bce` falls outside the reign span of a ruler-participant, matched by
**state + 本名** (avoids same-谥号 collisions) and multi-reign aware; a hit is classified `high` only when (a) the matched reign sits near the event's
*chapter era* (else wrong-ruler collision → `low`), AND (b) the deviation exceeds
`--grace` (default 2y, to absorb 当年改元/逾年改元 boundary fuzz). Pre-accession
violations stay `high` only for sovereign acts (封邑/会盟/任命… as 主行); other
pre-accession acts (谋叛/出奔 by a 公子) → `medium`. Births (`出生`) and posthumous
apparitions (显灵/托梦, by type or role) are exempt. Each issue carries a
`direction` (before_accession / after_reign). A reign_window violation whose ruler-participant already has an open
`preserve_source` conflict on a reign/date field (a recorded novel-vs-史记
discrepancy) is downgraded to severity `adjudicated` and annotated with the
conflict id, so settled cases (e.g. 郑定公 ruling past his 514 death in the novel)
stop resurfacing in the worklist. Plus **chapter_outlier** (year far from chapter median) and an
**undated** backlog grouped by chapter. This is the check that catches the
共叔段 case (events dated 756 vs 郑庄公 reign 743–701).

`scripts/resolve-dates` walks that report and patches `events.date_json.year_bce`
(marking `provenance='curated'` + a `date_json.curated` flag), writing an
`audit_log` row per change. Snapshots the DB first (WAL checkpoint + `.bak-datefix`).
Prefer `--cluster chN YEAR` for `relative_to_prior_event` chains (e.g. the 共叔段
cluster all share one mis-set anchor) over row-by-row fixes; re-run `scan-dates`
afterward to refresh the report.

### Undated backfill: scripts/propose-undated

`scripts/propose-undated` (read-only) proposes `year_bce` for null-year events into
`data/undated_fills.yaml` (gitignored), applied via `resolve-dates --apply-fills`
(audit-logged; stamps `uncertainty` + a `fill_method` marker so approximate fills
stay honest):
- **Tier 0 reign_parse (exact, `point`):** lenient Zhou reign-phrase search reusing
  `pipeline.dates` reign table — catches phrases the Stage-4 resolver's anchored
  `^周…年$` regex misses (e.g. "平王十三年，卫武公薨" → 758).
- **Tier 1 chain_inherit (`circa`):** a `relative_to_prior_event` event inherits the
  dated year of its chunk, nudged by time-word (明年/次年 → −1 BCE; 越N年 → −N). Two
  guards keep it honest: the chunk's dated events must cluster within `--spread` (5y),
  and the result must be within `--chapter-band` (30y) of the event's chapter median
  (rejects mis-chunked anomalies). First run filled 194/576; the remainder need
  narrative ordering or are genuinely undatable.
- **Tier 2 neighborhood_circa (`circa`):** when an event has no tight *same-chunk*
  anchor (Tier 1 missed it, or it is a non-relative undated event), borrow the median
  of dated events in nearby chunks of the *same chapter* — within `--window` (8)
  chunk-indices — provided that local window clusters within `--tier2-spread` (20y).
  Relative events still get the time-word nudge; others take the median as-is. The
  `--chapter-band` guard still applies. This relies on narrative order placing adjacent
  chunks chronologically close. Loose windows (span > 20y) and chapters with no dated
  anchor are deliberately left undated — those go to knowledge-dating. The 2026-06 run
  filled 198/382 this way (median window-spread 0; 187/198 from windows spanning ≤5y).

All three scripts (`scan-dates`, `resolve-dates`, `propose-undated`) default `--db`
to `data/books/dzl/canonical.sqlite` (the multi-book layout); pass `--db` for another
book. `--reigns` stays shared at `data/reigns`.

### Knowledge-dating the long tail (`fill_method=knowledge_date`)

The mechanical tiers bottom out at events with no resolvable in-text or in-chapter
anchor (relative chains whose root is itself undated; anchorless chapters). These are
dated by **historical knowledge** against 春秋/史记/左传 chronology, not arithmetic.
The 2026-06 pass ran a verification workflow (`knowledge-date-undated`): one *dater*
agent per chapter proposed `year_bce` + basis + confidence, then an **independent
skeptic** verified each against era/reign plausibility (accept / adjust / reject).
Only accepted/adjusted fills are written (`uncertainty` honest: `point` only for
firmly attested years like 707 繻葛之战 / 720 周郑交质, else `circa`); rejected ones
stay null. This cleared 180/184, leaving **4 genuinely undatable** folklore events
(干将莫邪剑化青龙, 陈仓陈宝 prophecy, …) — final coverage 2137/2141 (99.8%).

Two cross-checks the skeptic surfaced are worth noting as patterns: (1) a 左传 *flashback*
year ≠ event-occurrence year — e.g. the murder of 急子 is narrated under 左传桓公十六年
(696) but happened ~701 in 卫宣公's reign (he died 700); date the occurrence, not the
narration. (2) the novel narrates some events **out of chronological order** (信陵君迎
侯嬴 ~257 appears in ch94 whose main line is ~298); knowledge-dating assigns the true
historical year, so a resulting `chapter_outlier` flag is correct, not an error. Note:
`evt:任命` is cited in **both ch7 and ch66** (a 郑庄公-era appointment surfacing as a
ch66 flashback) — dated to its true ~701, but the stray ch66 citation is a candidate
event-identity collision for later curation.
