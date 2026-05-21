# Golden Chapter 1 Annotations

## Source

- Corpus: `dongzhoulieguozhi` (sibling repo)
- Edition / SHA: <pinned at annotation time; record the dongzhoulieguozhi commit SHA here when committing Task 9>
- Chapter: 第一回 (Western Zhou collapse)

## Conventions

- **Stable IDs**: `per:<slug>`, `evt:<slug>-<year>bce`, `pla:<slug>`, `sta:<slug>`, `cit:ch01-p<para>-<seq>`.
- **Hash IDs for unnamed entities**: `per:_<descriptor>-ch01` (the leading `_` flags unnamed; the `-ch01` scope ensures stable cross-chapter merge candidates for stage 5).
- **Variants**: every named person carries `canonical_name` + typed `variants[]` (`本名` / `字` / `谥号` / `封号` / `别名`).
- **Dates**: every date is the structured Date dict (year_bce, uncertainty, original, inference_kind).
- **Events**: an event is any deliberate action by a named agent (succession, exile, battle, embassy, marriage, omen) — narrative asides do not count.
- **Phase 2 reality**: variants of the same person stay as separate `per:*` ids if they would require stage-5 linking to merge. The one exception in Ch.1 is short-form ↔ canonical-form folding (e.g., `宣王` ↔ `周宣王`) — these stay as ONE record with `variants[]`.

## Decisions log

Append-only list of judgment calls made during annotation. These rules feed into the eventual `changjuan-extract` skill's system prompt (Task 27).

### Scope: who/what gets recorded in this chapter

- **2026-05-21: Active agents only.** Record named figures who participate in events of this chapter's narrative, plus unnamed-but-acting figures (the executed wife, the man who found the 女婴, the 老宫人, the 女婴 herself, the unnamed officials who *act* in scene). Background figures named only in the opening dynastic recap (武王, 厉王, 周公-the-Western-Zhou-original, 方叔, 申伯, 桀王, etc.) are **NOT** recorded — they belong to chapters where they act, or to a separate "background mentions" pass if that ever becomes needed.
- **2026-05-21: Active agents vs background figures, applied to unnamed.** Unnamed background figures (e.g., "many officials at court", attending courtiers without lines or named action) are NOT included. Unnamed figures who *act* in the narrative — particularly when they intersect with named figures who matter in later chapters — ARE included with hash-style ids (e.g., `per:_lao-gong-ren-ch01`, `per:_nv-ying-ch01`).
- **2026-05-21: Forward-link awareness.** The 女婴 found at the 清水河 is almost certainly the later 褒姒 (named in subsequent chapters), but Phase 2 records her as a separate `per:*` entry per the spec — stage 5 (Phase 3) will link. 隰叔 is included even though Ch.1's narrative arc ends with 785 BCE events, because his flight to 晋 has follow-on impact in subsequent chapters.
- **2026-05-21: Commented-out events for completeness.** The 46-year 东郊游猎 hunt (782 BCE) appears in the text but does not advance Ch.1's narrative arc — the chapter's beat ends with the ghost-vision and Western Zhou's collapse trajectory, not the hunt that triggers them. Recorded as a commented-out block in `events.yaml` with rationale; the 显灵 ghost-vision IS recorded because that's the narrative-critical beat. If the chapter is re-annotated in a future pass with different scope rules, the commented block is the audit trail.

### Date handling

- **2026-05-21: Reign-year anchors.** 周宣王's reign years (39 / 43 / 46) map to BCE 789 / 785 / 782 via the Phase 1 reign table with `inference_kind: explicit_reign_zhou`.
- **2026-05-21: Within-narrative sequence markers.** Phrases like "次日"、"自此"、"颁胙之后"、"是岁" get `inference_kind: relative_to_prior_event`. Within-chunk anchors do **not** require an explicit `relative_anchor_event_id` — Stage 4's `resolve_relative_dates` walkback fills the year_bce automatically. Cross-chunk anchors **do** require explicit `relative_anchor_event_id` per the spec's curator path.
- **2026-05-21: Explicit anchors for within-chunk chains, when readability matters.** Sometimes we set `relative_anchor_event_id` even for an in-chunk anchor (e.g., `evt:zuo-ru-suicide-785bce` → `evt:du-bo-executed-785bce`). The Stage 4 walkback would resolve it without the explicit field, but the chain reads more clearly in the golden with the link spelled out. Treat the explicit anchor as a documentation aid, not a functional necessity, for in-chunk cases.

### Chunk choice when paragraphs overlap

- **2026-05-21: Earliest-chunk rule.** Paragraphs that appear in multiple overlapping chunks (chk:dzl:1:0 vs :9, :9 vs :10, :10 vs :14, :14 vs :17) get cited from the **earliest** chunk containing the passage. This keeps the citation→chunk mapping stable: any future re-chunking that changes chunk boundaries would have to actively remove the early chunk for these citations to become invalid.

### Span offsets

- **2026-05-21: Two-pass span workflow.** Spans are written as `[0, 0]` placeholders during the prose-annotation pass, then computed by `scripts/fill-spans` (which reads chunk text from `data/corpus.sqlite`, finds the quote, writes the real `[start, end]` offsets). This decouples the annotator's judgment work (what to cite) from mechanical character counting (what offsets correspond). Quote-not-found errors at fill time indicate the annotator's transcription drifted from source — most commonly via Chinese-quote-mark confusion (`"` vs `'`) or by including/excluding trailing punctuation.

### Variants and identity

- **2026-05-21: Short-form folding only.** The only variant fold in Ch.1 is `宣王` ↔ `周宣王` — same person, just abbreviated form within the chapter. These stay as ONE record with `variants[]`. Any cross-name identification that would require stage-5 reasoning (e.g., 女婴 ↔ 褒姒) stays as SEPARATE records; stage 5 (Phase 3) is responsible for those merges.

### State coverage

- **2026-05-21: Ch.1's polity set.** Four states attested: 周 (the central 王朝), 姜戎 and 犬戎 (戎 tribes named as antagonists), and 晋 (named only as 隰叔's flight destination — the chapter says nothing about 晋's structure or rulers; it's an attested-by-name state only).

### Place coordinates

- **2026-05-21: Geocoding deferred.** All `lat` / `lon` / `coord_confidence` are left `null`. Geocoding is a separate pass against CHGIS (per spec §6 open questions); coordinates aren't required to validate extraction precision/recall.
- **2026-05-21: 太原 disambiguation.** The chapter's own gloss "那太原，即今固原州" pins this 太原 to modern 宁夏固原, NOT modern Shanxi 太原. Captured in `modern_equiv` as a curator hint so geocoding doesn't anchor to the wrong city.

### Quote selection

- **2026-05-21: Smallest defensible quote.** Quotes are short substrings that attest the specific claim being cited, not paragraph-sized blocks. Long quotes inflate span lookup ambiguity and don't strengthen the citation. Typical quote length: 5–30 characters.
- **2026-05-21: Avoid bracketing punctuation.** When a quote ends at a sentence boundary, drop the trailing 。/！/，/" rather than including them. Punctuation in the citation makes the verbatim check fragile (full-width vs half-width vs typographer's quote marks differ in unicode codepoint) without strengthening the attestation.

### Relation coverage strategy

- **2026-05-21: Relations completeness rules** (drawn from `relations.yaml`):
  - **event_participant**: every event in `events.yaml` gets at least one `event_participant` entry naming who acted and in what role. Multi-participant events (e.g., the ministerial council on the 童谣) get one row per (event, person, role) tuple.
  - **event_place**: only when a *non-primary* place is meaningful in addition to the event's `primary_place_id`. (The primary place is already on the event record itself; emitting an event_place duplicate for it would just inflate counts.)
  - **person_relation**: kinship (`parent` / `child` / `spouse`), friendship/alliance/rivalry, and recommender-style relationships.
  - **person_state**: ruler / minister / exile-to / defector-out role facts. Reign dates on rulers go on the `from_date` / `to_date` fields.
  - **state_capital**: 周's capital is 镐京 in this period — one row capturing that fact, citing the chapter's attestation.
  - **event_relation** (causes / precedes / related): not used in the Ch.1 pass — the within-narrative sequencing is already encoded by each event's `relative_anchor_event_id`, and adding event_relation rows would double-encode the same fact.
