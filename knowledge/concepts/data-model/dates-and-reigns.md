---
title: Dates, reigns, and inference kinds
type: concept
area: data-model
updated: 2026-05-21
status: thin
load_bearing: true
references:
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/reign_table.json
  - pipeline/dates.py
  - tests/unit/test_dates_relative.py
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

**Out of scope (Phase 2).** Automatic cross-chunk dereferencing (the
walkback only sees records in the current batch). Extending
`_RELATIVE_OFFSETS` to cover numeric patterns ("其后N年"). Both surface
in `concepts/pipeline/incremental.md` as Phase 3+ work.

## First commitments

- `pipeline/reign_table.json` source: 杨伯峻《春秋左传注》, cross-checked against 史记·十二诸侯年表.
- `pipeline/dates.py` parsers handle: `explicit_reign_lu`, `explicit_reign_zhou`, `explicit_reign_other` (deferred until needed), `relative_to_prior_event`, `era_only`, `unknown`.
- Reign-year arithmetic: BCE year = `start_bce - (N - 1)` for reign year N.
