# 长卷 Reader — v1 Design

**Date:** 2026-05-30
**Status:** Draft for review (rev 2 — incorporates first-round review)
**Scope:** The reader-facing companion app. First consumer of the pipeline's export bundle. Distinct from the tooling-phase spec (`2026-05-20-changjuan-design.md`), which ends at the export contract.

---

## 1. Vision & Success Criteria

### Vision

长卷 Reader is a cross-platform **reading companion** for character-dense classical narratives. It dissolves the "cast of thousands" problem: while or after reading a book like 《东周列国志》, the reader can instantly answer *who is this person, when are we, who are they related to, what have they done, and how do we know* — every fact traceable to a source line.

It is **not** a map app (the founding "unroll the scroll" living-map remains deferred until place coordinates exist) and **not** a generic ebook reader. It is a graph-powered comprehension layer, with the original text as a phase-2 surface.

The app is conceived as a **multi-book platform**: 《东周列国志》 ships bundled by default as the first title; future titles arrive as downloadable/purchasable **data bundles**. The platform is genre-flexible via **capability-gated view-packs** (Section 6).

### Success criteria

1. A reader confused by a name in chapter N can find that person — by *any* of their aliases, including pinyin — and understand their identity, allegiances, kin, and acts in **under 15 seconds**.
2. Every displayed fact can be traced, in one tap, to the source passage(s) that justify it.
3. The app runs on Web first, and the **same codebase** compiles to iOS and Android with no rewrite.
4. The app consumes the pipeline's frozen export bundle through a stable contract; re-freezing at a later chapter count requires no app code change.
5. Adding a second book that reuses existing view-packs requires **shipping data only** — no app code change.

> **Risk note (raised in review):** Criterion #1 is the only quantified target, and it rests on the two least-resolved technical items — search latency and Web first-load. The headline metric and the biggest unknowns are the same surface. Section 8 therefore front-loads a **Phase 0 spike** on both rather than treating them as implementation-plan details.

---

## 2. Decisions deliberately deferred / out of scope

Consolidated here as one grep target, mirroring the founding spec's convention. Each was considered during brainstorming and parked with a reason.

- **舆图 Map / geographic views** — blocked: 0 of 425 places currently have `lat`/`lon`. Requires a geocoding sub-project (ancient name → modern equivalent → coordinates). The `map` capability id is reserved.
- **原文 in-app Reader** (chapter text + tappable inline annotations) — **phase 2**, committed. Reuses the person/event cards as annotation popovers. Requires the *full continuous reading text* payload (Section 3), which is deliberately **not** in the v1 web bundle.
- **Native iOS / Android builds** — **phase 2**. v1 ships the Web target only; native is an Expo config/build step on the same code.
- **Library / catalog UI, download manager, purchase / IAP, entitlements, remote book provider** — phase 2/3. v1 ships exactly one bundled book. The *seams* exist (Section 5); the features do not.
- **View-pack registration SDK / capability-negotiation framework / arbitrary per-book schemas** — deferred until **book #2** concretely reveals what varies. v1 keeps views modular and capability-gated but builds no speculative plugin framework. *Design the seam at one book; build the framework at two.*
- **Cross-book entity unification** — explicitly never. Each book is its own graph; the same historical figure in two books is two book-scoped records.
- **Spoiler-scoping ("as of chapter N")** — rejected in favor of full-graph-always (Section 4). Simpler queries; better for re-readers and study.
- **Account-based sync of bookmarks/notes across devices** — deferred; this is the part that genuinely needs a backend. (Local, on-device bookmarks/notes are **in v1** — see Section 7.7. The earlier draft wrongly conflated the two.)
- **English UI / translation** — Chinese-only for v1, consistent with the tooling phase.

If a scope expansion is requested mid-build, evaluate it against this list; promoting any item bumps this spec's status.

---

## 3. Platform & data architecture

### Stack

- **Expo (React Native + React Native Web)** — one TypeScript codebase → Web (v1), iOS + Android (phase 2). Web is a first-class target, which matters for a text-heavy Chinese reading app (real selectable/searchable text).
- **No backend in v1.** All data is queried **locally, on-device**. (Local bookmarks/notes use on-device storage, not a server — Section 7.7.)

### Data: bundled, read-only SQLite, split into graph and text payloads

The pipeline's frozen export is the contract. Review surfaced that it must be **split into two payloads** so the Web cold-load stays small:

- **Graph payload (`graph.sqlite`)** — persons, events, places, states, relations, **and denormalized citation quote text** (see below). This is everything v1 needs. Bundled in-app and queried in place.
- **Text payload (`texts/`)** — the full continuous reading prose per chapter. **Not in the v1 web bundle.** Loaded on demand by the phase-2 Reader (and bundled outright on native, where size is a non-issue).

**Query layer per platform:** native SQLite (`expo-sqlite` / `op-sqlite`) on mobile; **SQLite-WASM in a Web Worker** on Web (keeps the UI thread unblocked). One adapter interface; two implementations.

**One graph DB per book** — books are never merged. Entity IDs (`per:晋文公`) are unique within a book; isolation matches the no-unification decision.

### Export-contract prerequisite (new — gap found in review)

The canonical `changjuan.sqlite` does **not** today contain the text needed to render most citations: `entity_citations` stores only a **chunk pointer** (`citation_id` like `chk:dzl:1:0`); only `events` carry a denormalized `quote`. The export step must therefore **resolve each cited chunk to its passage text and denormalize it into the graph payload** (a `citations(citation_id, quote, chapter, chunk)` table, or an equivalent column). Without this, the one-tap-to-source feature (criterion #2) cannot render. This is a pipeline/export change, listed as a prerequisite in Section 8.

### The export bundle, current state

Built against the **Ch.1–50 freeze** (~700 persons, ~1,000 events, ~330 places, ~60 states, ~12k citations). The app re-bundles when the pipeline re-freezes higher; no app code change required.

---

## 4. Data model the views rely on (read-only projection)

The views are projections over the existing canonical schema. Key relations:

- **Person** — `canonical_name`, `gender`, `birth/death_date_json`, `state_id`, `clan_name`, `social_category`, plus `person_variants` (2,600+ alias rows). Search also indexes a **build-time pinyin** rendering of each variant (Section 7.1).
- **Deeds** = `event_participants(person_id → event_id, role, role_detail, citation_id)`. A "deed" is **one participation edge**, tagged with the person's `role` (主行 / 主将 / 进谏 / 出使 / 死 / 被擒 / 受命 / 梦者 …). All roles are kept — passive involvements (a person's own death, capture, flight) are essential biography. The same event appears on every participant's card with that participant's own role.
- **Relations** — `person_relations(from, to, kind, date_json, citation_id)`: parent / child / sibling / spouse / ally / rival / mentor / `killed_by`.
- **Service over time** — `person_states(person_id, state_id, role, from_date_json, to_date_json, citation_id)`. The `role` vocabulary is **`ruler` / `minister` / `exile` / `defector`** — i.e., flight and defection are *explicitly labeled and citation-backed*, not inferred (see 7.4).
- **Events** — `type`, `date_json` (1,222 of 1,326 carry `year_bce`), `outcome`, `summary`, `primary_place_id`, plus participants/places/relations.
- **Citations** — `entity_citations` + per-edge `citation_id`, resolved to passage text via the denormalization in Section 3.

**Full-graph, always.** No chapter-gating on queries; the entire book's graph is visible regardless of reading position.

---

## 5. Book as a first-class unit (the multi-book seams)

Built in v1 even though only one book ships, because retrofitting these is expensive:

1. **Active-book context.** App state carries the current book. Navigation is conceptually `Library → open book → (views within that book)`. Routes are book-scoped internally even with one book present.
2. **Book provider seam.** Books load through a provider interface: `BundledBookProvider` (v1) and `RemoteBookProvider` (phase 2/3, downloads/purchases). Same interface, so the query layer is untouched when downloads arrive.
3. **Manifest carries book identity + capabilities.** The export `manifest.json` is extended with `title`, `author`/`edition`, `cover`, `corpus_edition`, `schema_version`, entity `counts`, and a **`capabilities`** array (Section 6). The Library can list books without opening each DB.

**Books are data, never code.** A downloaded/purchased book ships graph + texts + manifest only — never executable UI. Required for App Store / Play compliance and security.

---

## 6. Capability-gated view-packs (genre flexibility)

The platform is multi-genre via **first-party view-packs compiled into the app**, each bound to a **capability id**. A book's manifest declares which capabilities it supports; the app enables the matching packs and **renders navigation dynamically from that list**.

- v1 packs: `cast`, `timeline`, `states`. Reserved for later: `map`, `genealogy`, `reader`.
- 《东周列国志》 declares `["cast", "timeline", "states"]`.
- A future single-journey narrative might declare `["cast", "timeline", "map"]` → no States tab.
- A **new genre of view** = an app update adding a pack. A **book reusing existing packs** = data only.

**`genealogy` vs. the card's Relations section (boundary clarified in review).** They are the *same edges* (`person_relations`) at two altitudes:

- **Relations** is core, on every person card: the subject's *immediate* kin as tappable chips (父 / 子 / 弟 …). Always present wherever `cast` is.
- **`genealogy`** is a distinct, opt-in pack: a *multi-generation tree/graph visualization* over the transitive closure of those edges (whole-lineage view, e.g. the 晋 ruling house across generations). A book gets it only if it declares the capability.

So the boundary is principled: local one-hop chips (core) vs. whole-lineage visualization (pack), never duplicated.

**Shared KG core, optional extensions.** All books sit on the same knowledge-graph substrate. A future genre needing fields the core lacks gets **optional extension tables** plus a pack that reads them. Arbitrary per-book schemas are **not** supported.

**No speculative framework in v1.** Views are modular and capability-bound; the nav is data-driven. The real pack-registry is deferred until book #2 reveals the right abstraction.

---

## 7. Navigation & views

### Navigation

Bottom-tab bar rendered from the active book's `capabilities`. For 《东周列国志》: **名册 Cast · 纪年 Timeline · 列国 States**, plus a persistent **search** affordance. **Cross-linking is the spine** — every chip/row is a tap: kin chip → that person's card; deed → event detail; state chip → state page; participant → their card. The whole graph is walkable.

### 7.1 名册 Cast & search

Search across all 2,600+ name variants (重耳 = 公子重耳 = 晋文公 resolve to one person), **plus pinyin** of each variant so a reader who can't type the hanzi (or only half-recognizes a name) can still find them. Filter by state / social category / clan. List → person card.

**Search implementation (resolved from open question):** default to an **in-memory index built on first load** — for ~2,600 variant rows it is trivially small, dodges the "is FTS5 compiled into this WASM build?" uncertainty entirely, and is the natural home for pinyin matching. Pinyin is generated **at export build-time** (e.g. `pypinyin`) and shipped as columns, so the client does no romanization work. FTS5 is reached for only if profiling on a real bundle says the in-memory index is insufficient.

### 7.2 Person card — Dossier layout

One vertical scroll, all sections visible (validated over the Hub/tabbed alternative during brainstorming):

1. **Hero** — canonical name + aliases + state / social-role / epithet chips.
2. **生平 Vitals** — reign/birth/death dates, clan.
3. **关系 Relations** — immediate kin chips, each tappable to that person; each carries a 📖 citation count.
4. **事迹 Deeds** — the participation chronicle, **ranked** (see below), with a chronological **"show all" toggle** and **role-filter chips**. Each row: year, summary, role badge.
5. **📖 全文出处 row** — opens the aggregate citations screen (7.5).
6. **★ track / note** affordance (7.7).

**Deed ranking (refined from review — was open question #9).** Pure *global* event-type weighting (战/会盟/弑 > 探病/割地) has a known failure: a minor figure whose single defining act is a low-weight type gets that act buried. Ranking therefore **blends two components**:

- a **global** component (event-type weight × participant-count × citation-count), and
- a **within-person salience** component — a deed that is *rare in the corpus but central to this person's own record* surfaces even when its global weight is low (TF-IDF-style: importance relative to the person, not just the world).

For low-deed-count figures the question is moot — all deeds show. The blend matters for mid-to-high-density cards. Computed **build-time** (thin client, inspectable, tunable) but treated as **a parameter to iterate on with real cards in front of us**, not a formula finalized up front. The Phase-0 spike (Section 8) produces sample cards to tune against.

### 7.3 纪年 Timeline

Vertical year-scroll over the 1,222 dated events. Filter by state / person / event-type. Tap an event → event detail (participants grouped by role, place, outcome, citations). Filtered to one person, doubles as that person's life-spine. Event detail is the home of `event` data; there is no separate Events tab.

### 7.4 列国 States

The ~60 polities. Each state page = **ruler succession over time** + a **roster by labeled role** drawn from `person_states`: `ruler` / `minister` / `exile` / `defector`, each row carrying its own citation and date range. "Who rose, who defected, who fled" is shown **only from the explicit role label**, never inferred from a bare membership change — preserving the traceability promise. Tap anyone → their card.

### 7.5 Citations — two altitudes

- **Per-item drill-down (primary):** tapping any Relation chip, Deed row, or service-role row opens a transient popover with *exactly* that claim's source passage(s) — rendered from the denormalized quote text (Section 3) — plus the role/year attested. Claim → its evidence.
- **全文出处 aggregate (complement):** a per-person screen listing every passage in the book that mentions them, ordered by chapter — built from the same denormalized citation quotes, so it needs no full-text payload. Breadth, not per-claim proof.
- They never share screen space (popover over the touched item vs. a route behind a labeled row).

### 7.6 Navigation stack & "back" (new — raised in review)

The cross-linking spine produces deep walks (person → kin → deed → event → participant → …), so "back" must be explicit:

- The app maintains its own **navigation stack** scoped to the active book; "back" pops it.
- On **Web**, the stack integrates with **browser history** (the OS/browser back button and the in-app back gesture pop the same stack; deep state is URL-addressable so links/refresh work). On native, the platform back button/gesture drives the same stack.
- The **active-book context is preserved** across the walk; popping past a book's root returns to the Library (phase 2) or app root (v1).

### 7.7 Local bookmarks & notes (new — reconsidered from review)

On-device only, **no backend** (the constraint the architecture avoids is *server sync*, not local persistence):

- **★ Track** any person / event / state — a local list of followed entities for quick return. The core re-reader/study affordance.
- **Notes** — short local annotations attached to an entity.
- Stored in on-device storage (a local writable SQLite table or platform key-value store), kept **separate from the read-only book graph** so book re-bundles never clobber user data, and so bookmarks can reference entity IDs across book updates.
- Cross-device **sync** of this data is the part that needs a backend → deferred (Section 2).

---

## 8. Phasing

- **Phase 0 — spike first (de-risks criterion #1).** Before committing the UI: (a) measure SQLite-WASM **cold-load + first-query latency** on the real Ch.1–50 `graph.sqlite` (gzipped size, worker streaming vs. full load, loading-state UX); (b) prototype **search** (in-memory index + pinyin) and confirm sub-second lookup; (c) generate a handful of **real person cards** to tune the deed-ranking blend. These are the headline-metric risks, not implementation trivia.
- **Phase 1 (v1):** Web target. 名册 Cast + 纪年 Timeline + 列国 States + person/event/state detail + citations (both altitudes) + local bookmarks/notes, over the bundled 《东周列国志》 **graph** payload. Book-as-unit + provider seam + capability-driven nav present but exercised by one book.
- **Phase 2:** 原文 in-app Reader (loads the text payload; inline annotation popovers reuse the cards); native iOS / Android builds.
- **Phase 3+ / blocked:** Library + download + purchase/IAP + `RemoteBookProvider` + bookmark sync; 舆图 Map (after geocoding); additional books and view-packs as real second cases arrive.

**Pipeline/export prerequisites (must land before / alongside Phase 1):**

1. Denormalize cited passage text into the graph payload (Section 3) — *blocks citations entirely*.
2. Split export into `graph.sqlite` + `texts/` payloads (Section 3).
3. Extend `manifest.json` with book identity + `capabilities` (Section 5).
4. Build-time **pinyin** columns on variants (Section 7.1).
5. Build-time **deed-importance** values (Section 7.2).

---

## 9. Open questions for the implementation plan

- **Deed-ranking weights** — the *tuning* of the global × within-person blend (7.2). The mechanism is decided; the constants are an iterate-with-real-cards task seeded by the Phase-0 spike.
- **WASM cold-load budget** — actual gzipped `graph.sqlite` size after the text split + quote denormalization; whether the worker streams or fully loads; loading-state UX. (Phase-0 spike.)
- **Pinyin matching quality** — tone-marked vs. toneless, multi-syllable name handling, collision behavior (many names share romanizations); acceptance bar for "found in <15s".
- **Manifest schema_version handshake** — how the app declares versions it understands and degrades gracefully on mismatch.
- **Local-store schema** for bookmarks/notes and its forward-compatibility across book re-bundles (7.7).
- **Chinese typography / vertical-text** stance for the phase-2 reader (does not block v1).
