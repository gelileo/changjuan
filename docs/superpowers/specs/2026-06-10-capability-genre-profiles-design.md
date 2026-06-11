# Capability / Genre-Profile Backbone — Design

**Date:** 2026-06-10
**Status:** Draft for review
**Scope:** Make "genre profile" a first-class, declarative concept in the changjuan
pipeline, co-designed with a second profile (cast/literary) so the abstraction is
validated against two real instances. Bounded to the backbone + a thin 红楼梦
vertical slice; full-book extraction and new reader UI are deferred.

---

## 1. Motivation & Scope

### The insight

Chinese classical works the reader targets fall into two broad shapes:

- **Event / time-geo-heavy** (东周列国志, 资治通鉴, 史记): numerous historical
  events, datable chronology, states, places. dzl is this shape today.
- **Cast-heavy** (红楼梦, 水浒传, 三国演义): a huge cast and dense person
  relations; little or no datable historical chronology.

These need **different pipelines that share a common core**. The seam between
"shared" and "genre-specific" is a *genre profile*: a declarative selection of
**mining capabilities** that the ETL turns on for a given book. The reader
already works this way — it gates tabs on a `capabilities` array in the manifest.
This spec pushes the same idea upstream into the factory.

### The universal capability set

Every profile is a subset of:

| Capability | history (dzl) | cast (红楼梦) |
| --- | --- | --- |
| `persons` | ✅ | ✅ (huge cast) |
| `relations` | ✅ political vocab | ✅ kinship/marriage/romance/servitude vocab |
| `events` | ✅ battles/treaties/successions | ✅ feasts/deaths/intrigues |
| `chronology` | ✅ reign-year → BCE engine | off (narrative order only) |
| `geography` | ✅ places + coords | off (fictional settings) |
| `groups` | states | clans/factions (四大家族) |
| `themes` | off (deferred) | ✅ new capability |

Citations/provenance is always-on (every fact links to source) and is not a
toggle.

### In scope (this spec)

- The **declarative profile** mechanism: `profile` + `capabilities` in
  `book-meta.json`, driving prompt-pack selection, capability-guarded stages, and
  the export manifest.
- The **`State` → `Group`** schema generalization (the one shared grouping
  mechanism).
- **Relation-kind vocabulary moved from a DB `CHECK` into profile config.**
- The new **`themes`** capability + entities (mined and exported; reader view
  deferred).
- **Generalizing the hardwired `ingest`** into a book-registry.
- Authoring the **`cast` extraction prompt-pack**.
- Proving the cast profile **end-to-end on a thin slice** — the first ~3–5 回 of
  红楼梦 — through export → depot → reader.
- Reader generalization (`states`→`groups` queries/tab; consume
  `schema_version 7`).

### Out of scope (follow-on specs)

- Full 120-回 红楼梦 extraction.
- Reader **theme-view** UI.
- The living **geo-map** / time-scrubbing reader UI.
- Place-coordinate resolution (CHGIS et al.).

### Prerequisite

A 红楼梦 source text must be acquired and shaped for ingest (analogous to the
`dongzhoulieguozhi` sibling repo). This is a task in the implementation plan.

---

## 2. The Profile Model

A profile is **declarative data**, not code. `book-meta.json` gains:

```jsonc
{
  "book_id": "honglou",
  "profile": "cast",                 // "history" | "cast"
  "capabilities": ["persons", "relations", "events", "groups", "themes"]
}
```

The profile drives exactly three things, each already half-present in the codebase:

1. **Which extraction prompt-pack runs** — selected by profile (the mechanism
   that today selects the v1/v2 extraction skill directory).
2. **Which capability-specific stages execute** — others self-skip.
3. **What the export manifest declares** — the reader gates its tabs on it.

The two concrete profiles defined here:

- **`history`** — the existing dzl pipeline, re-expressed as a profile. Capabilities:
  `persons, relations, events, chronology, geography, groups`.
- **`cast`** — new. Capabilities: `persons, relations, events, groups, themes`.

This is the **thin / declarative** architecture (chosen over a stage-registry or a
full strategy-object design): the smallest change that makes the profile real,
reusing existing machinery. Graduating to a stage-registry is a documented
future option if a third genre ever needs a different *stage order* — a decision
to make with three real instances in hand, not by guessing now.

---

## 3. Data Model Changes

Export `schema_version` bumps **6 → 7**.

### 3.1 `State` → `Group` (clean full rename)

The `states` table generalizes to `groups`, gaining a typed column:

```
groups(id, name, ruling_clan, group_type, prominence, prominence_tier)
       group_type ∈ {state | clan | faction | sect}
```

Cascading renames (clean, full — one consumer, controlled):

- `persons.state_id` → `persons.group_id`
- `person_states` → `person_groups`
- `state_capitals` → `group_seats` (history-only in practice)
- `candidate_states` → `candidate_groups`, `candidate_person_states` →
  `candidate_person_groups`
- `entity_citations.entity_kind` value `'state'` → `'group'`

dzl rows migrate to `group_type = 'state'`; 红楼梦's 四大家族 become
`group_type = 'clan'`.

**Reign/date resolution is unchanged.** It remains a `chronology`-capability stage
that only ever operates on `group_type = 'state'`. The reign-table keying
(`sta:jin`, …) and `pipeline/dates.py` logic are untouched; clans never enter
that path. This compartmentalization is what keeps the rename mechanical rather
than a logic rewrite.

### 3.2 Relation vocabulary: DB `CHECK` → profile config

Today `person_relations.kind` is constrained by a hardcoded
`CHECK (kind IN ('ally','rival','killed_by','clan_member', …))`. Adding cast
vocabulary would mean editing a constraint per genre.

**Change:** drop the `CHECK`; each profile declares its allowed `kind` set, and
the **loader validates** `kind` against the active profile's vocabulary.

- `history`: `ally · rival · killed_by · clan_member · …` (current set preserved)
- `cast`: `父子 · 母子 · 夫妻 · 兄弟 · 主仆 · 恋慕 · 收养 · …`

The same treatment applies to `event_relations.kind` if cast needs vocab beyond
`causes/precedes/related` (decided during prompt-pack authoring).

### 3.3 Themes — new capability + entities

```
themes(id, name, description, prominence)
theme_occurrences(theme_id, entity_kind, entity_id, citation_id)
```

`theme_occurrences` links a theme to a person / event / chapter with its source
quote. New `entity_kind = 'theme'`. Mined by the cast prompt-pack and persisted by
a theme loader; exported when the `themes` capability is on. The reader
theme-view is deferred (capability-gated; no tab built yet) — the pipeline mines
and exports the data; rendering is a follow-on.

### 3.4 Export & the two capability vocabularies

The canonical-only export snapshot enumerates canonical tables dynamically, so
renamed/added tables flow through once the schema + loaders change.

There are **two capability vocabularies**, deliberately kept separate:

- **Profile (ETL) capabilities** — fine-grained: `persons, relations, events,
  chronology, geography, groups, themes`. They govern extraction and which stages
  run. This is the factory concept.
- **Reader (tab) capabilities** — coarse, what the reader already gates on:
  `cast, timeline, groups, themes`.

At export, the manifest's **reader capabilities are derived** from the profile's
ETL capabilities, so the reader's gating logic is unchanged (only the `states`→
`groups` rename touches it). The derivation:

| Reader tab | Lights up when ETL capabilities include… |
| --- | --- |
| `cast` (名册) | `persons` (relations render inside it) |
| `timeline` (纪年) | `chronology` (a dateless event list is not a timeline) |
| `groups` (列国/世家) | `groups` |
| `themes` | `themes` (tab deferred — derived but no view yet) |

So **events are mined and exported regardless**, but the chronology-oriented
`timeline` tab only appears when `chronology` is on. For cast, events exist in the
graph with no dedicated reader surface in this spec (deferred, like the theme
view).

---

## 4. Pipeline Changes

Core stages always run and stay genre-agnostic. The only structural code change
is generalizing `ingest`; everything else is guards + prompt-pack selection (the
thin approach).

```
ingest      generalized: book-registry, no longer hardwired to the dzl JSON path
chunk       always
extract     prompt-pack by profile  (history-pack = current v2; cast-pack = new)
link/dedup  always (surface-feature linker works for both)
load        relation-kind validated vs profile vocab; group loader
export      canonical snapshot + manifest(capabilities)
```

**Capability-guarded behaviors (self-skip when their capability is off):**

| Behavior | Guarded by | history | cast |
| --- | --- | --- | --- |
| date-resolution (reign-tables → BCE) | `chronology` | on | off → dates stay narrative-order/unknown |
| place-coordinate resolution + geo export | `geography` | on | off |
| 左传/史记 cross-canon verification (already opt-in) | `cross-canon` | on | off |
| theme extraction + theme loader | `themes` | off | on |

### Prompt-packs

The existing v2 extraction skill content **becomes the `history` pack**. A new
`cast` pack is authored: 世情小说 entity guidance, the kinship/romance/servitude
relation vocabulary, group-as-clan extraction, and theme mining. The profile in
`book-meta.json` selects the pack (same mechanism that selects v1/v2 today).

### Export → reader contract

- **Gating logic needs no reader change** — already capability-driven; the export
  derives reader capabilities from the profile (§3.4).
- Reader **does** change: `states` queries + the 列国 tab generalize to `groups`
  (labeled by `group_type`: 列国 for states, 世家 for clans); reader consumes
  `schema_version 7`.
- 红楼梦 (cast), profile capabilities `[persons, relations, events, groups,
  themes]`, derives reader capabilities `[cast, groups]` → reader shows 名册 (with
  relations) + 世家 (clans). `timeline` (纪年) is hidden (no `chronology`); the
  states-flavored 列国 label does not apply. Cast events + themes are exported but
  have no reader surface in this spec.

---

## 5. Acceptance Criteria

- **A. dzl is unchanged.** dzl re-exported under `schema_version 7` (groups all
  `group_type = state`) renders functionally identical in the reader — same
  名册 / 纪年 / 列国 / 原文 / 收藏, same content. Guarded by a regression test
  diffing pre/post reader query results against the dzl golden output.
- **B. Tabs gate correctly.** The cast book derives reader capabilities
  `[cast, groups]` and shows 名册 (with relations) + 世家, hides 纪年 (no
  chronology), shows no theme tab. The history book derives
  `[cast, timeline, groups]` and renders exactly as it does today (see A).
- **C. Cast graph is valid.** The 红楼梦 slice yields persons, cast-vocab
  relations, `group_type = clan` groups (四大家族), and themes — each with
  citations.

---

## 6. Testing

- **dzl-parity regression test** — the spine of criterion A. Diff reader query
  results (and/or export counts per table) for dzl pre- and post-migration.
- **Cast golden fixture** — one 红楼梦 回 with hand-labeled expected entities;
  precision/recall thresholds analogous to the dzl golden set, calibrated after a
  first baseline run.
- **Profile-config validation tests** — relation-kind vocabulary enforcement
  (a cast `kind` rejected under the history profile and vice-versa).
- **Capability-guard tests** — chronology / geography / cross-canon / themes each
  skip or run according to the declared capability list.

---

## 7. Knowledge Updates (same-task rule)

- **New** `concepts/pipeline/profiles.md` — the capability / genre-profile model.
- **New** `concepts/corpora/honglou.md` — the 红楼梦 corpus integration.
- **Update** `concepts/data-model/knowledge-graph.md` — `State` → `Group`.
- **Update** `concepts/pipeline/extraction.md` — prompt-packs by profile.
- **Update** `concepts/pipeline/architecture.md` — capability-guarded stages.
- **Update** `concepts/pipeline/export-contract.md` — `schema_version 7`.
- **Update** the CLAUDE.md article-mapping table + append a `knowledge/log.md`
  entry.

---

## 8. Decisions Made (during brainstorming)

- Test book is **红楼梦**, not 资治通鉴 — 资治通鉴 spans many eras/calendars and is
  itself multi-domain; 红楼梦 is bounded, public-domain, a different genre, and a
  compelling cast-graph product. Chosen to **co-design** the backbone (two real
  instances beat one).
- Profile depth: **declarative / thin** (config + prompt-pack + guards), not a
  stage-registry or strategy-object. YAGNI until a third genre.
- Groupings: **generalize** `State` → `Group` (one shared mechanism), via a
  **clean full rename**, not a name-preserving semantic broadening.
- Themes: **included now** as a first-class capability (mined + exported; reader
  view deferred).
- Constraints (user): the reader must gate tabs correctly **and** dzl's rendered
  result must not change.
