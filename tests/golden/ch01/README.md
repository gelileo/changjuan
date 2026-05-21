# Golden Chapter 1 Annotations

## Source

- Corpus: `dongzhoulieguozhi` (sibling repo)
- Edition / SHA: <pinned at annotation time; record here>
- Chapter: 第一回 (Western Zhou collapse)

## Conventions

- **Stable IDs**: `per:<slug>`, `evt:<slug>-<year>bce`, `pla:<slug>`, `sta:<slug>`, `cit:ch01-p<para>-<seq>`.
- **Variants**: every named person carries `canonical_name` + typed `variants[]` (`本名` / `字` / `谥号` / `封号` / `别名`).
- **Dates**: every date is the structured Date dict (year_bce, uncertainty, original, inference_kind).
- **Events**: an event is any deliberate action by a named agent (succession, exile, battle, embassy, marriage, omen) — narrative asides do not count.
- **Phase 2 reality**: variants of the same person stay as separate `per:*` ids (e.g., 重耳 and 晋文公 are TWO entries). Phase 3 stage-5 will merge them; the golden gets updated then.

## Decisions log

(Append-only list of judgment calls made during annotation.)

- YYYY-MM-DD: <decision>
