---
title: Dates, reigns, and inference kinds
type: concept
area: data-model
updated: 2026-05-20
status: thin
load_bearing: true
references:
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/reign_table.json
  - pipeline/dates.py
---

## What this is

Every Date in changjuan is structured: `{year_bce, uncertainty, year_bce_end?, original, era, inference_kind}`. The `inference_kind` records *how* a BCE year was derived — not all dates in 东周列国志 are equally trustworthy. The bundled `pipeline/reign_table.json` provides the canonical 鲁公 and 周王 chronologies (722 BCE – 468 BCE for 鲁, 770 – 476 BCE for 周) so explicit-reign citations like 鲁僖公二十八年 dereference deterministically to 632 BCE.

## Why this shape, not the alternatives

Storing only `year_bce` would lose the distinction between a citation like 鲁僖公二十八年 (high trust) and a relative reference like 其年 (trust inherited from the anchor) or an era-only mention 春秋末 (range, not point). The pipeline's confidence scoring penalizes anything other than explicit-reign citations; without `inference_kind`, that penalty has nothing to attach to.

## What would invalidate this article

- A reign-year citation in the corpus that the reign table can't dereference (i.e., another state's reigns we haven't tabulated). Promotion path: add the state's reign block alongside `lu` and `zhou`.
- A new `inference_kind` becoming necessary as the corpus surfaces new date forms.

## `parse_date` — current surface

`pipeline.dates.parse_date(original: str) -> DateDict` dispatches to pattern-matching helpers in priority order. The Lu parser (`_try_lu`) uses `_LU_PATTERN` which accepts both the full `鲁X公N年` form and lenient prefixes (`鲁X年` / `X公N年`). The Chinese numeral parser (`_cn_to_int`) covers 元 and compound forms up to ~60.

## First commitments

- `pipeline/reign_table.json` source: 杨伯峻《春秋左传注》, cross-checked against 史记·十二诸侯年表.
- `pipeline/dates.py` parsers handle: `explicit_reign_lu`, `explicit_reign_zhou`, `explicit_reign_other` (deferred until needed), `relative_to_prior_event`, `era_only`, `unknown`.
- Reign-year arithmetic: BCE year = `start_bce - (N - 1)` for reign year N.
