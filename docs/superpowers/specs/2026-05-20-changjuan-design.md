# changjuan (长卷) — Tooling-Phase Design

**Date:** 2026-05-20
**Status:** Draft for review
**Scope:** Tooling phase (data pipeline + curation). Reader-facing map UI is a separate, later spec.

---

## 1. Scope & Success Criteria

### Vision

`changjuan` (长卷) lets readers explore Eastern-Zhou history — the events, people, states, and lineages of 春秋 and 战国 — through a living, geographically-anchored, time-driven view. The reader watches a stylized map of late-Zhou China as time scrubs forward: state borders shift, people appear and travel, events flash at their locations, and clicking any marker reveals citations back to the original texts.

The project is named *changjuan* (长卷) — the Chinese long-scroll handscroll painting format — because reading the work should feel like unrolling that scroll: events and figures disclosed gradually with time and geography.

### In scope (this spec, the tooling phase)

- Ingest the 108 chapters of 东周列国志 (already present in `dongzhoulieguozhi/` as both per-chapter text and structured JSON).
- Ingest 左传 and 史记 as parallel corpora for cross-validation.
- Build a Python ETL pipeline that extracts a structured knowledge graph: **persons (with name variants and clan/lineage), events, places, states (polities), dates, source citations**.
- Cross-check extracted facts against 左传 and 史记; surface disagreements as first-class data, not silently dropped.
- Persist everything in a single SQLite file with a clean schema, plus a JSON export contract so the future map UI can consume the data without coupling to the pipeline.
- A Streamlit curation app for retrospective human review of pipeline output.

### Out of scope (deferred)

- The reader-facing living-map / timeline UI.
- Hosting, multi-user, authentication, web deployment. Single user, run locally.
- Additional corpora beyond 东周/左传/史记 (e.g., 战国策, 国语). Schema is designed to accept them later; integration is a follow-up.
- Translation, English UI, accessibility polish.

### Non-goals & deliberate omissions

Each of these came up during design, was considered, and was rejected or deferred with a documented reason. They are listed here as one grep target so the plan stage and any future reader can see the consolidated set of "we decided not to" rather than discovering each justification scattered across sections.

- **`Family` as a first-class entity** — clan politics matter, but clan-level facts may be fully expressible via `person_relations(kind="clan_member")` + a `clan_name` string on Person. Defer until the golden-chapter pass proves the lighter model is insufficient. Promotion path: §2's "Note on Family."
- **Denormalized JSON exports** (`entities/*.json`, `geo-index.json`, `time-index.json`, `search-index.json`) — duplicate SQLite content, drift out of sync, force "which is authoritative?" question on every export. Add only when a concrete UI complaint demands the perf win. §5.
- **Per-record `schema_version`** — over-engineered for a single-curator project with co-evolving producer and consumer. Manifest-level version is enough. §5.
- **Headline counter widgets on the curator home screen** — derivable from the coverage grid and queues; anchoring for metrics nobody has used the tool long enough to know they care about. Defer until a week of curation surfaces which numbers actually get glanced at. §4.
- **`actor_kind` / `actor_id` / `actor_version` column split on `audit_log`** — overloaded `actor` string works for v1 because we mostly filter with prefix-LIKE. Split if "all changes from prompt v2 across the corpus" becomes a hot query. §7.4.
- **Additional source corpora** beyond 东周列国志 + 左传 + 史记 (战国策, 国语, 竹书纪年) — schema accepts them, integration is a follow-up spec.
- **Reader-facing living-map / timeline UI** — separate, later spec. The export bundle is the boundary.
- **Hosting, multi-user, authentication, web deployment** — single-user, run locally.
- **Translation, English UI, accessibility polish** — Chinese-only for tooling phase.
- **LLM agent / tool-loop extraction** (approach C from brainstorm) — gated by stage-3's deterministic prompt approach proving inadequate on specific chapters. Reserved as opt-in "rescue mode," not the default path.
- **Per-citation footnotes from secondary sources** (annotations, scholarly commentary) — the citation model is corpus-only for v1. Secondary annotations can ride on `Conflict.curator_note` or a future `annotations` table if the need is felt.

If a scope expansion is requested mid-build, it should be evaluated against this list — adding any of the above promotes them into scope and should bump the spec's status.

### Audience

Three tiers, but only relevant to the *future* reader UI:

- **Casual readers** — want help keeping people, states, events straight while reading.
- **Students** — want chapter alignment, glossaries, study aids.
- **Enthusiasts / amateur scholars** — want to dig deep, run analytical queries, see novelist embellishment vs. canonical record.

The tooling phase has one user: the curator (project owner).

### Success criteria (tooling phase)

1. End-to-end pipeline runs over all 108 chapters of 东周列国志 and produces a populated SQLite knowledge graph **without requiring any human curation**.
2. Every record carries at least one source citation `(corpus, chapter, paragraph, verbatim quote)` — no anonymous facts.
3. Disagreements between 东周列国志 and 左传/史记 are detected and surfaced as Conflict records with all variants preserved.
4. The curator can clear review queues at sustainable per-queue rates: low-confidence extractions under 30s/record, conflicts under 1 min/record, person merge candidates 3–5 min/record (merge decisions can require reading both contexts and trying to compress them shorter produces bad merges).
5. The exported data is consumable by a separate UI process via a stable, versioned contract — a frozen SQLite snapshot plus a `manifest.json` documenting schema version and corpus editions.
6. The pipeline supports **incremental extraction** (one chapter at a time, or re-extracting one chapter with a newer prompt) without destroying prior state.

### Guiding principle

**Automation first, curation optional.** Every pipeline stage produces a complete, usable best-guess result without human intervention. Curation is purely retrospective: a curator can revisit and correct any record at any time, but they are never in the critical path.

---

## 2. Data Model

### Entities

Each entity carries:

- A stable, human-readable `id` (slug-based; see *Stable IDs* below).
- `confidence` ∈ [0, 1] — see *Confidence as a computed score* below; this is **not** the LLM's self-reported probability.
- `provenance` ∈ {`auto`, `curated`}.
- `created_at`, `updated_at`, `pipeline_run_id`.
- One or more `citations`.

### Confidence as a computed score

LLMs do not produce well-calibrated confidence numbers for structured extraction; a self-reported `0.8` from the model means "looked confident in the answer," not "right 80% of the time." Using model self-report as the primary signal would push subtle errors into auto-merge decisions in stage 5.

Confidence in this system is therefore a **deterministic score computed by the pipeline**, with the LLM judge as one input among several:

- For extracted entities/relations: a function of citation strength (quote length, distinctness), redundancy across chunks, and the LLM's per-field justification quality from the stage-3 self-check.
- For stage-5 linking: a function of surface features the pipeline computes itself — variant overlap, `state_id` agreement, temporal proximity, family proximity, place proximity — combined with the LLM judge's verdict as one weighted signal.
- For dates: see `inference_kind` below — explicit reign citations score higher than relative or inferred dates regardless of LLM self-report.

The scoring weights are themselves tuned against the golden chapter set (Section 6) and revised across pipeline runs. Reliability diagrams in `pipeline_runs.stats_json` track whether `0.8` actually means ~80%.

| Entity | Description | Key fields |
| --- | --- | --- |
| **Person** 人物 | A historical figure. | `canonical_name`, `variants[]`, `gender`, `birth_date`, `death_date`, `state_id?`, `clan_name?` |
| **State** 诸侯国 | A polity (周, 齐, 晋, 楚, 秦, 鲁, 卫, 宋, 郑, 陈, 蔡, 燕, 吴, 越, …). | `name`, `founded_date`, `ended_date`, `ruling_clan`, `type`, era-keyed `capitals[]` |
| **Place** 地点 | A typed location (capital, battlefield, pass, river, mountain, meeting site). | `name`, `type`, `lat`, `lon`, `coord_confidence`, `modern_equiv` |
| **Event** 事件 | A typed historical event (battle, 盟会, succession, exile, assassination, marriage, omen, embassy, …). | `type`, `date`, `outcome`, `summary`, `primary_place_id?`, role-typed `participants[]` |
| **Citation** 出处 | Pointer to a verbatim source span. Referenced by every other record. | `corpus`, `chapter`, `paragraph`, `span`, `quote` |
| **Conflict** 异说 | A first-class record of a disagreement between sources. | `subject_kind`, `subject_id`, `field`, `variants[]` (each with citation), `current_best_variant_idx`, `resolution_rule`, `status` |

> **Note on Family.** A first-class `Family` entity was considered and **deferred**. Clan politics (三桓, 田氏代齐, 三家分晋) clearly matter, but the golden-chapter pass has to decide whether clan-level facts exist independently of person-level facts or are fully expressible via `person_relations(kind="clan_member")` + a `clan_name` string on Person + state context. We start with the lighter model and promote `Family` to an entity if and only if the data demands it. The promotion path: add `families` table, migrate `clan_name` strings to `family_id` foreign keys via a deterministic mapping, version-bump the export schema.

### Cross-cutting types (not entities)

**Date** is a structured value, not a primitive:

```json
{
  "year_bce": 632,
  "uncertainty": "point",
  "year_bce_end": 632,
  "original": "鲁僖公二十八年",
  "era": "春秋早期",
  "inference_kind": "explicit_reign_lu"
}
```

Field meanings:

- `uncertainty` ∈ {`point`, `range`, `circa`}.
- `inference_kind` records *how* the BCE year was derived. This is essential because the reign-table approach (鲁公纪年 → BCE) is only the easy case. The novel also uses 周王纪年, occasionally other states' reigns, and relative references like 其年/明年/是冬. Treating all of these as if they were 鲁公 reigns would give a date-normalization bug rate higher than the unit tests suggest.

  Values:
  - `explicit_reign_lu` — direct 鲁公 reign citation; highest trust.
  - `explicit_reign_zhou` — direct 周王 reign citation; high trust, separate table.
  - `explicit_reign_other` — another state's reign (晋/齐/楚/…); medium trust, requires reign-table coverage for that state.
  - `relative_to_prior_event` — "其年", "明年", "是冬" anchored to a previously-dated event in the chunk; trust inherits from anchor.
  - `era_only` — only an era is known (e.g., "春秋末"); `year_bce` set to era midpoint, `uncertainty: "range"`.
  - `unknown` — no temporal anchor; `year_bce` null.

  Anything other than `explicit_reign_lu`/`explicit_reign_zhou` carries a confidence penalty in the scoring function.

**Name variants** — every Person has a `canonical_name` plus a list of `variants[]` typed by kind: `本名` / `字` / `谥号` / `封号` / `别名`. 重耳, 晋文公, 公子重耳 all resolve to one `Person.id`. Without this, the graph fragments.

**Stable IDs** — slug-based with hash disambiguation when needed:

- `per:jin-wen-gong`
- `evt:cheng-pu-zhi-zhan-632bce`
- `pla:cheng-pu`
- `sta:jin`
- Unnamed entities: `per:_h7f3k2…` (hash).

Slugs are seeded from the curated `canonical_name`, not from raw LLM output, so re-extraction never invalidates them.

### Relationships

Uniform shape: every relation row carries its own `citation_id`, `confidence`, `provenance`.

- `event_participants(event_id, person_id, role, role_detail)` — role ∈ {`主将`, `副将`, `参战`, `死`, `俘`, `使`, `媒`, …}
- `event_places(event_id, place_id, role)` — for multi-place events.
- `event_relations(from_event_id, to_event_id, kind)` — `causes` | `precedes` | `related`.
- `person_relations(from_person_id, to_person_id, kind, date?)` — `parent` | `child` | `spouse` | `sibling` | `mentor` | `ruler` | `minister` | `ally` | `rival` | `killed_by` | `clan_member` | …  (the `clan_member` kind plus a `clan_name` string on Person carries clan/lineage facts until/unless `Family` is promoted.)
- `person_states(person_id, state_id, role, from_date, to_date)` — `ruler` (with reign dates) | `minister` | `exile` | `defector` | …
- `state_capitals(state_id, place_id, from_date, to_date)` — era-keyed.
- `entity_citations(entity_kind, entity_id, citation_id)` — many-to-many.

---

## 3. Pipeline Architecture

Sequential ETL with checkpointed, idempotent stages. Each stage reads the previous stage's output and writes its own. Three stages are LLM-driven (3, 5, 6); all others are deterministic code.

### Stages

1. **Ingest** — read 东周列国志 (already JSON), 左传, 史记 from `corpora/`. Normalize to a common document format with stable paragraph indices. → `corpus.sqlite`.
2. **Chunk** — paragraph-aware splitter with overlap. Each chunk gets a stable `chunk_id` that citations reference. → `chunks` table in `corpus.sqlite`.
3. **Extract (LLM)** ⭐ — per chunk, structured-output call (JSON Schema enforced). Returns candidate Persons / Events / Places / Relations, each carrying `chunk_id`, a verbatim quote span, and a **per-field justification** ("which substring of the quote supports this value?"). The justification is what powers the *claim-defensible-from-quote* invariant below. → `candidate_*` tables in `changjuan.sqlite`.
4. **Normalize** — pure code: parse 鲁公纪年 → BCE via a hardcoded reign table, attach era labels, clean honorifics, split title + name components.
5. **Link & dedup (LLM)** ⭐ **— the highest-stakes stage in the pipeline.** Resolves candidate entities against each other *and against the existing canonical graph* (see Section 7). Surface-feature matching for the easy cases; LLM judge for ambiguous pairs. Errors here compound: a bad merge in chapter 3 contaminates linking in chapter 4, which contaminates chapter 5, and every subsequent extraction reinforces the error. We therefore set the auto-merge threshold deliberately high, accept a large `merge_candidates` queue, and treat that queue as the *first* curation surface to build (see Section 4). Outputs: auto-merges + `merge_candidates` rows for everything below threshold.
6. **Cross-canon check (LLM)** ⭐ — for each high-confidence Event/Person fact, retrieve corresponding passages from 左传/史记 (sparse + dense retrieval), LLM-verify same-event, compare fields, emit Conflict records on disagreement. Gated behind `--with-canon-check`.
7. **Load** — upsert candidates into `changjuan.sqlite` with field-level merge semantics (see Section 7). Auto-resolves uncertain fields by deterministic rules; never blocks on uncertainty.
8. **Curate (human, optional)** — Streamlit app for retrospective review. Never gates downstream stages.
9. **Freeze & export** — snapshot a versioned bundle (`changjuan-export-vN/`) as the stable contract for the future UI.

### Cross-cutting infrastructure

- **LLM cache** — every LLM call keyed by `hash(prompt_template_version, model, input)` → response, with token + cost tracking. Re-runs are free unless prompts or inputs change.
- **Stage checkpoints + dry-run** — every stage takes `--chapters N..M` (or `--chunk-ids …`) for subset runs. Every stage is resumable from the last successful chunk.
- **Two extraction invariants** — the verbatim check is necessary but not sufficient. The two layers are *not* equally rigorous and the spec should be honest about it:
  1. **Verbatim-quote invariant** — every extracted record's `quote` must appear character-for-character in its `chunk`. Enforced at stage 3 output validation. Catches fabricated source spans.
  2. **Claim-defensible-from-quote.** The more common LLM failure is *not* a fabricated quote but a wrong structured claim derived from a real one (subject reversed, wrong action direction, date inferred from nearby context). Two enforcement layers — but they carry very different weight:
     - **Per-field justification (generation-time nudge, not verification):** stage 3 prompts the model for a `justification_quote` per scalar field — a substring of the `quote` that supports each value — and the static check ensures it's non-empty and a substring of the quote. Realistically the model will mostly comply, but for contested fields it can quote a substring that mentions the right entity rather than one that supports the specific value. The static check catches the trivially-empty case, not the trivially-bad case. Treat this layer as *making the model think twice while generating* — it produces a verifiable artifact but the artifact itself is gameable.
     - **Sampling QA (the real backstop):** a deterministic 5% sample per chapter is re-evaluated by a *different* model (or a different prompt template) answering "does this quote support this field?" with yes/no/partial. This is where actual claim-quality verification happens. Results land in `pipeline_runs.stats_json`; sustained mismatch rates above a threshold block the stage-9 freeze.

  **Why 5%.** This is the only number in the pipeline driven by a power calculation rather than intuition. We want to detect a baseline-to-regression shift of 5pp in claim mismatch rate (say, 5% → 10%) with α=0.05, β=0.2. The binomial sample-size formula gives ≈180 verifications corpus-wide for that target. The 108-chapter × ~30-records-per-chapter corpus contains roughly 3000+ scalar facts, so a 5% sample (~150–250 verifications, depending on extraction density) sits comfortably above that floor while staying cheap. The constant lives in `pipeline.config` and should be raised if the target effect size shrinks.

### Why three separate LLM stages

Extraction, linking, and canon-checking are different problems with different prompts, different evaluation criteria, and different cost profiles. Keeping them separate lets each be tuned and tested in isolation, and lets stage 6 be gated off entirely while stages 1-5 mature.

---

## 4. Curation UI (Streamlit)

Single-page Streamlit app, run locally. Reads/writes `changjuan.sqlite`. **All review queues are filters over a live, complete graph — not gates on delivery.**

### Home screen

Deliberately spartan in v1: the **108-cell chapter coverage grid** — the one element with clear day-one value (see Section 7.5), letting the curator spot stale chapters at a glance — plus three queue entry points and a free-form search. No headline counters yet: most of them (chapters extracted, total entities, conflicts auto-resolved, decisions to date) are derivable from the grid and the queues, and adding them on day one is anchoring for metrics nobody has used the tool long enough to know they care about. Counters can come back once a week's worth of curation surfaces the numbers that actually get glanced at.

### Three review queues (filters over the graph)

Built in this order — merge candidates first because that's where the graph actually gets ruined:

1. **Unresolved Person merge candidates** — pairs that the auto-merge threshold declined to combine but the linker flagged as possible duplicates. The most cognitively expensive queue; gets the richest UI. **Target: 3–5 min/decision** — these sometimes require reading both source contexts in full, and pushing under that target produces bad merges. Built **first** because stage-5 errors compound through the rest of the graph.
2. **Open Conflicts** — auto-resolved disagreements where the curator may want to override the pipeline's pick. **Target: <1 min/decision.**
3. **Low-confidence extractions** — records below a configurable confidence threshold. Sorted by chapter so the curator can work in narrative order. **Target: <30s/decision.**

### Review screen layout (uniform shell)

- **Left (40%)** — verbatim source quote in context. The relevant span highlighted. "Show ±2 paragraphs" toggle. This is the evidence; never paraphrased.
- **Center (40%)** — the structured record, every field editable in place. For merge candidates: a side-by-side of the two records, shared/distinct attributes color-coded. For conflicts: each variant with its citation and quote.
- **Right (20%)** — action panel: **Accept** / **Edit & accept** / **Reject** / **Defer** / **Split**. Curator free-text note. Keyboard shortcuts `a`/`e`/`r`/`d`/`s`.

### Ergonomics

- Keyboard-driven; under 200ms per record (prefetch next 5).
- Every decision writes an `audit_log` entry with `before/after`. Decisions are fully reversible.
- A **re-extract button** on each chapter view — calls stage 3 with the current prompt version, surfaces a diff against the curated state, applies merge rules without destroying curator decisions.

---

## 5. Storage Schema & Export Contract

Two SQLite databases, one export bundle.

### `corpus.sqlite` (read-only after stage 1)

Source corpus. Immutable so the rest of the system can rely on stable chunk IDs.

- `documents(id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at)`
- `chunks(id, document_id, paragraph_start, paragraph_end, text, hash)`
- `citations(id, chunk_id, span_start, span_end, quote)` — referenced by every record in `changjuan.sqlite`.

### `changjuan.sqlite` (canonical store + candidate staging)

The single source of truth. Tables:

#### Entity tables

Each row has `id`, `confidence`, `provenance`, `created_at`, `updated_at`, `pipeline_run_id`. Field-level history is reconstructed from `audit_log` via a view (see Section 7), not stored as a JSON blob on the row.

- `persons(id, canonical_name, gender, birth_date_json, death_date_json, notes, state_id?, clan_name?)`
- `person_variants(id, person_id, variant, kind)`
- `states(id, name, founded_date_json, ended_date_json, ruling_clan, type)`
- `state_capitals(id, state_id, place_id, from_date_json, to_date_json)`
- `places(id, name, type, lat, lon, coord_confidence, modern_equiv)`
- `events(id, type, date_json, outcome, summary, primary_place_id?)`

#### Relation tables

Uniform shape: `id, ..., citation_id, confidence, provenance, ...`

- `event_participants(event_id, person_id, role, role_detail, …)`
- `event_places(event_id, place_id, role, …)`
- `event_relations(from_event_id, to_event_id, kind, …)`
- `person_relations(from_person_id, to_person_id, kind, date_json?, …)` — includes `kind="clan_member"` until/unless `Family` is promoted to a first-class entity.
- `person_states(person_id, state_id, role, from_date_json, to_date_json, …)`
- `entity_citations(entity_kind, entity_id, citation_id)`

#### Candidate tables

The staging area for unvetted extractor output — same shape as the canonical tables but tagged by `pipeline_run_id` and never read by export. Collapsed into `changjuan.sqlite` rather than a separate file so stage 5→7 runs in a single transaction.

- `candidate_persons`, `candidate_events`, `candidate_places`, `candidate_states`, `candidate_*_relations`
- `candidate_facts(id, subject_kind, subject_candidate_id, field, value_json, justification_quote, justification_span, pipeline_run_id)` — the per-field justifications from the stage-3 self-check.

#### Bookkeeping

- `conflicts(id, subject_kind, subject_id, field, variants_json, current_best_variant_idx, resolution_rule, status, curator_note?)`
- `audit_log(id, entity_kind, entity_id, field?, change_kind, before_json, after_json, actor, at, citation_id?, pipeline_run_id?)` — `field` column added so this table can also serve as the per-field history source. **Shape of `before_json` / `after_json` for field-level changes** (i.e., when `field IS NOT NULL`): `{"value": <scalar or json>, "confidence": <float>, "source_excerpt": <optional string>}`. Record-level changes (`field IS NULL`) carry the full entity snapshot instead. The `field_history` view in Section 7.4 relies on this shape; changing it requires updating the view in lockstep.
- `pipeline_runs(id, stage, started_at, ended_at, prompt_version, model, scope_json, stats_json, stats_schema_version)` — `stats_json` is a structured blob with the shape committed below.
- `llm_cache(id, key_hash, model, prompt_template_version, request_json, response_json, tokens, cost, created_at)`
- `merge_candidates(id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, llm_judgment_json, status)` — first curation queue built (Section 4).
- `qa_samples(id, pipeline_run_id, record_kind, record_id, field, verdict, verifier_model, at)` — output of the 5% sampling QA.

#### `pipeline_runs.stats_json` schema (v1)

Seven metric families with heterogeneous shapes will accumulate in this blob. Without a documented schema the dashboard's parser would have to be defensive on every read. v1 commits to the following shape, versioned by `stats_schema_version` so the dashboard knows what it's looking at:

```json
{
  "schema_version": 1,
  "extraction": {
    "per_entity_type": {
      "person":  {"precision": 0.91, "recall": 0.88, "tp": …, "fp": …, "fn": …},
      "event":   {"precision": 0.84, "recall": 0.79, "tp": …, "fp": …, "fn": …},
      "...":     "..."
    }
  },
  "claim_defensible_sample": {
    "sample_size": 187, "yes": 162, "partial": 18, "no": 7, "mismatch_rate": 0.134
  },
  "linking": {
    "merge_regression_set": {"correct": 23, "total": 25, "accuracy": 0.92},
    "duplicate_person_rate_golden": 0.04
  },
  "canon_check": {
    "conflicts_emitted": 412,
    "conflict_precision_against_golden": 0.81,
    "golden_coverage": 0.74,
    "oldest_open_conflict_age_days": 12
  },
  "confidence_calibration": {
    "stage3": [{"bin": "0.7-0.8", "predicted": 0.75, "observed": 0.71, "n": 412}, ...],
    "stage5": [...],
    "stage6": [...]
  },
  "cost": {"tokens_in": …, "tokens_out": …, "usd": …},
  "thresholds_breached": ["claim_defensible_mismatch_rate"]
}
```

A `thresholds_breached` field is the gate for the stage-9 freeze: any name in this list blocks export. The dashboard reads `schema_version` and degrades gracefully on older runs.

#### Views

- `field_history(entity_kind, entity_id, field, value_json, confidence, source, citation_id, at)` — reconstructed from `audit_log` filtered to scalar-field changes; powers the curation UI's "how do we know this?" view without a redundant JSON blob on the entity row.

#### Indexes

- B-tree on `json_extract(date_json, '$.year_bce')` for events, persons, person_relations — enables time-range queries.
- Spatial-ish index on `places(lat, lon)` for map bbox queries.
- Trigram on `persons.canonical_name` and `person_variants.variant` for name search.
- Index on `audit_log(entity_kind, entity_id, field)` to keep the `field_history` view fast.

### Export bundle: `changjuan-export-vN/`

A frozen, versioned, self-contained bundle consumed by any future UI. v1 is deliberately minimal — SQLite is the single source of truth in the bundle; the UI builds its own in-memory indices on first load.

```text
changjuan-export-2026-05-vN/
├── manifest.json         # version, generated_at, scope, counts, schema_version, source_corpus_editions
└── changjuan.sqlite         # read-only snapshot (canonical tables only; candidate_* tables stripped)
```

Denormalized JSON variants (entity files, geo-index, time-index, search-index) are deliberately **out of v1**. They duplicate SQLite content, drift out of sync with it, and add a "which is authoritative?" question on every export. Add them only when a concrete UI complaint demands the perf win; bump `schema_version` and document them in the manifest at that point.

Schema version lives only in the manifest, not per record — this is a single-curator project with co-evolving producer and consumer. Per-record `schema_version` would be over-engineered.

**Stripping candidate tables from the export.** Because `changjuan.sqlite` now holds both canonical *and* candidate-staging tables, the export step must omit the latter. To make this fail-loud rather than fail-quiet when a future schema change adds new `candidate_*` tables:

- The export script enumerates *canonical* tables by **prefix exclusion** (`name NOT LIKE 'candidate\_%' ESCAPE '\'` and not in the bookkeeping/view block-list), rather than by an explicit allowlist that someone has to remember to update.
- A blocking CI test (see §6) opens the produced export bundle and asserts there are no tables matching `candidate_%`. Belt and suspenders.

---

## 6. Quality, Testing, Risks

### Testing strategy

Tests fall into two kinds, treated differently. **Blocking tests** must pass for CI to be green; any failure halts merging or stops the pipeline at the stage boundary. **Tracked metrics** are signals the pipeline computes on every run; they don't break CI but a threshold breach blocks the stage-9 freeze and surfaces a curator warning.

#### Blocking tests (CI-fail if these break)

- **Verbatim-quote invariant** — every extracted record's `quote` is a literal substring of its `chunk`. Enforced at stage-3 output validation.
- **Per-field justification static check** — every scalar field's `justification_quote` is non-empty and a substring of the record's `quote`. Catches the trivially-empty case (the trivially-bad case is the sampling QA's job — see §3).
- **Schema validation** at every stage boundary. JSON Schema; malformed output never reaches downstream stages.
- **Idempotence** — re-running any stage on unchanged inputs with cache produces identical outputs modulo timestamps and `pipeline_run_id`.
- **Date-conversion unit tests, per `inference_kind`** — separate test buckets for `explicit_reign_lu`, `explicit_reign_zhou`, `explicit_reign_other`, `relative_to_prior_event`, `era_only`. Each bucket has its own targeted parity (e.g., relative-references must dereference correctly across a chunk's prior events). A green-but-incomplete bucket cannot hide a bug in another bucket.
- **Era-keyed `state_capitals` test** — for each golden-chapter `state_capital` row, the `from_date_json.year_bce` must equal (or fall within) the date of the **specific event in the source chunk that the capital fact is attributed to** — *not* the chunk's overall date range, since a chunk can span years and contain multiple events. The extractor is therefore obliged to pick a sourcing event for every capital fact, and the test asserts the join. Catches the case where stage 3 extracts "晋's capital is 新田" without binding the fact to the 585 BCE move that establishes it.
- **Stage-5 merge regression set** — a small curated list of known same-person pairs (重耳/晋文公) and known different-person pairs (different 公子重耳 across states). Stage 5 must reproduce each decision on every run.
- **Round-trip test** — export bundle → load into fresh SQLite → counts and key facts match canonical store.
- **Export contains no staging tables** — open the produced export bundle and assert that no table matches `candidate_%`. The export's prefix-exclusion logic and this assertion are the belt-and-suspenders pair guarding against a future schema change leaking candidate data into the export.

#### Tracked metrics (block stage-9 freeze on threshold breach; otherwise inform)

Stored in `pipeline_runs.stats_json`; surfaced on the curator dashboard.

- **Extraction precision/recall per entity type** vs. the golden chapter set.
- **Stage-3 claim-defensible sampling rate** — the 5% sample's yes/no/partial verdict distribution. Sustained mismatch rate above the configured threshold blocks freeze.
- **Stage-5 auto-merge accuracy** — % correct against the merge regression set; also the duplicate-Person rate against the golden set.
- **Stage-6 Conflict precision** — % of stage-6 Conflicts that survive curator review as real disagreements.
- **Confidence calibration** — reliability diagrams per stage (does `confidence=0.8` mean ~80% correct?).
- **Conflict queue staleness** — age of the oldest unreviewed Conflict, measured in days. The check is *armed only on the first stage-9 freeze attempt*; before that, staleness is recorded but does not block anything. Once armed, a configurable max-age (default 30 days) blocks subsequent freezes. This prevents the metric from being perpetually breached during the initial extraction sweep, when the queue is naturally large simply because nothing has been reviewed yet.
- **Cross-canon golden coverage** — % of the known-disagreement list flagged by stage 6.

### Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| **Stage 5 false-positive merge** (silently fuses two different people) | High | **Severe** — errors compound across the rest of the graph and every subsequent extraction reinforces them | High auto-merge threshold; `merge_candidates` queue built first; per-merge audit trail makes splits reversible |
| LLM produces wrong structured claim from a real quote | High | Severe — graph contains plausible-looking falsehoods | Two invariants (verbatim + claim-defensible-from-quote), per-field justifications, 5% sampling QA blocks freeze if mismatch rate too high |
| LLM fabricates entities/quotes not in source | Medium | Severe | Verbatim-quote invariant; reject at stage-3 validation |
| Date mapping errors (non-鲁公 reigns, relative references) | High | Medium — wrong years on otherwise-correct events | `inference_kind` on every Date; confidence penalty for non-`explicit_reign_lu/zhou`; unit tests over the golden set per inference kind |
| LLM "confidence" treated as ground truth | Medium | Medium | Confidence is a deterministic computed score (Section 2); LLM self-report is one weighted input only |
| Cross-canon retrieval matches wrong passage | High | Medium — false positives are visible *if reviewed*, but Conflicts are queue #2 and will backlog; bad Conflicts then shape later canon-check decisions and leak into the export | LLM verifies same-event before field comparison; **Conflict queue staleness** is tracked in `pipeline_runs.stats_json` (oldest open Conflict age); the staleness check is *armed only on the first stage-9 freeze attempt and afterward*, with a 30-day default max-age, so it stays dormant during the initial extraction sweep when the queue is naturally large; the curator coverage grid surfaces stale chapters |
| Schema churn mid-project | Medium | Low | Manifest-level `schema_version`; idempotent migrations; `candidate_*` staging tables make re-extraction cheap |
| LLM cost overrun | Medium | Low | Content-hash cache, per-run budget cap, `--chapters N..M` dry runs |
| 左传 / 史记 corpora vary by edition | Medium | Low | Document exact source in `documents.source_edition`; check editions into the repo at a known SHA |
| Place geocoding uncertainty | Low | Low | `coord_confidence` field; UI renders uncertainty visually later |
| Stage 6 (cross-canon) hardest to get *right* | High | Medium — individual false positives are visible, but a sustained false-positive rate erodes trust in *all* Conflicts including the true ones | Gate behind `--with-canon-check`; build stages 1–5 + 7–9 fully first; track Stage 6 precision against the cross-canon golden cases and block freeze if precision drops below threshold |

### Open questions (resolved during plan writing or first plan steps)

1. **LLM provider/model.** Recommendation: Anthropic Claude (Sonnet for stages 3/5, Opus for stage 6). The cache layer abstracts the choice.
2. **Reign-table source.** Recommendation: bundled JSON curated from 杨伯峻's 《春秋左传注》 chronology; ~50 reign entries.
3. **左传 / 史记 source edition.** Recommendation: ctext.org plain-text exports, archived into the repo at a known SHA.
4. **Place coordinates source.** Recommendation: CHGIS (Harvard) for known historical places; fall back to "modern_equiv + geocode lookup" for the rest. Confirm license.
5. **Golden-chapter selection.** Recommendation: Chapter 1 (Western Zhou collapse — people-light, event-heavy) and Chapter ~40 (城濮之战 — people-dense, conflict-rich).

### Suggested build sequence

This isn't part of the spec's normative scope (the plan document will fix the actual order), but it shapes risk and is worth flagging here. **LLM stages are the expensive failures; doing the cheap deterministic work first makes those failures easier to see.**

Recommended order:

1. **Corpus ingest + stages 1, 2 (Ingest, Chunk)** — gets `corpus.sqlite` populated with stable chunk IDs from the three corpora. No LLM cost. The whole rest of the system references chunk IDs that don't exist yet.
2. **Stage 4 (Normalize) skeleton + reign tables** — pure code, fully unit-testable against the date-conversion buckets without any LLM in the loop.
3. **Stage 7 (Load) skeleton + the canonical schema** — so there's a real load path to write into.
4. **Stage 9 (Export) skeleton + round-trip test** — closes the loop end-to-end before any LLM call exists.
5. **Hand-annotate golden chapter #1** directly into the target schema — this *is* the schema's first user, and the act of annotating it will surface schema bugs before the prompt is written.
6. **Stage 3 (Extract)** — by this point you have a real schema to validate against, a real chapter to test on, a real load path to write into, and a real round-trip test that proves the deterministic stages work.
7. **Stage 5 (Link & dedup)** with the merge regression set as the testbed.
8. **Stage 8 (Curate)** — merge-candidates queue first (the dangerous one), Conflicts second, low-confidence last.
9. **Stage 6 (Cross-canon)** — only after 1–5 + 7–9 are working end-to-end. Gated behind `--with-canon-check` so a partially-working stage 6 doesn't block the rest.

---

## 7. Incremental Semantics

The pipeline's unit of work is a chunk, not the book. You can extract chapter 1 today, chapters 2–5 next week, re-extract chapter 27 next month after fixing a prompt, and the canonical store accumulates correctly. Three mechanisms make this work.

### 7.1 Stage 5 (Link & dedup) considers the existing canonical graph

When a new chunk's candidates arrive at the linker, the candidate pool includes both the current batch's other candidates *and* all existing canonical entities loaded from `changjuan.sqlite` (filtered by relevance: matching name variants, overlapping state, overlapping era). Matching uses:

- **Surface features**: shared name variants (`canonical_name`, all `variants[]`), `state_id` overlap, temporal proximity, place proximity.
- **LLM judge** for ambiguous cases — given the full citations of both candidates, decide same-or-different with a confidence score.

Outcomes:

- High confidence match → auto-merge into existing entity.
- Below threshold → create as new entity, store the close-match as a `merge_candidate` row for retrospect.
- No nearby candidate → create as new entity.

### 7.2 Stage 7 (Load) is an upsert with field-level merge semantics

When a candidate is matched to an existing entity, fields don't replace — they merge by rule:

| Field type | Merge rule |
| --- | --- |
| **Citations** | Always accumulate. Every appearance adds a citation; nothing overwrites. |
| **Name variants** | Union. New variants accumulate with their own citation and `kind`. |
| **Scalar facts** (birth year, death year, gender, state-of-birth, …) | If existing is `auto` and new has higher confidence → update + log. If existing is `curated` → never silently overwrite; emit Conflict for curator. If new disagrees at similar confidence → emit Conflict, preserve both variants. |
| **Date fields** | Same as scalars, but a more-precise date (range → point, or improved `uncertainty`) wins over a less-precise one even at lower confidence. |
| **Relations** | Add if not already present. Contradictory relations (`A killed B` vs `B killed A`) → Conflict on the relation row. |
| **Notes** | Append, never overwrite. |

Every merge writes an `audit_log` entry with `before/after`. Every change is fully reversible.

### 7.3 Re-extraction is a first-class operation

Command: `changjuan re-extract --chapter 27 --prompt-version 3`.

1. Pull chunks of ch. 27 from `corpus.sqlite` (unchanged).
2. Run stage 3 with the new prompt version. Output → `candidate_*` tables in `changjuan.sqlite` tagged with the new `prompt_version`.
3. Stage 5 links new candidates against the existing canonical graph (which may include curator overrides).
4. Stage 7 applies merge rules. **`curated` records are never silently overwritten** — divergences become Conflict records.
5. Optional: stage 6 re-runs against changed records (input = "records changed since timestamp T", not a chapter range).

Improving a prompt is always safe — re-extraction adds findings, never destroys curator work.

### 7.4 Per-field history via the `field_history` view

A redundant JSON-blob `provenance_chain` column on each entity row was considered and rejected: it can't be indexed, every update rewrites the whole blob, and "what did we believe about X's birth year as of run R" requires JSON parsing in every query. We already have an `audit_log` table; field-level history is just a particular slice of it.

We expose that slice as a view:

```sql
CREATE VIEW field_history AS
SELECT
  entity_kind, entity_id, field,
  json_extract(after_json,  '$.value')      AS value_json,
  json_extract(after_json,  '$.confidence') AS confidence,
  actor                                      AS source,   -- 'extract@v2', 'canon-check@v1', 'curator:kun', ...
  citation_id, at, pipeline_run_id
FROM audit_log
WHERE field IS NOT NULL
ORDER BY entity_kind, entity_id, field, at;
```

For a Person's `birth_year` we get exactly the timeline we want — every prior value with its source, confidence, citation, and timestamp — without storing the data twice. The curation UI joins on this view to render "how do we know this?" The composite index on `audit_log(entity_kind, entity_id, field)` keeps lookups fast.

**The `actor` string convention.** `actor` overloads "who did this" with "which version" in one column: `kind:id@version`. Examples: `extract@v2`, `canon-check@v1`, `link@v3`, `curator:kun`, `normalize@v1`. This is fine for v1 because we mostly query by entity + field and only filter by actor with prefix-LIKE patterns. If "give me all changes from prompt v2 across the corpus" becomes a hot query, the migration path is to split into `actor_kind`, `actor_id`, `actor_version` columns on `audit_log`. Not worth the schema cost today; do worth flagging so future-us doesn't have to reverse-engineer the format.

### 7.5 Coverage telemetry

A `chapter_coverage` view summarizes for each of the 108 chapters: last extracted at, prompt version used, # entities created, # entities updated, # conflicts opened, # curator decisions. The Streamlit dashboard renders this as a 108-cell grid — green for recent + curated, yellow for stale, grey for not-yet-extracted.

---

## Appendix A — File layout (proposed)

The project repo `changjuan/` sits next to sibling source-corpus repos (`dongzhoulieguozhi/` already exists; `zuozhuan/` and `shiji/` are added later). The project owns its `corpora/` directory and points at each sibling via a symlink, so stage 1 has stable in-tree paths without duplicating source data into the repo.

```text
mpklu/unroll/                          # workspace (not a git repo)
├── dongzhoulieguozhi/                 # external — existing source corpus repo
├── zuozhuan/                          # external — to be added
├── shiji/                             # external — to be added
└── changjuan/                         # ← this project (its own git repo)
    ├── corpora/                       # symlinks into sibling source repos
    │   ├── dongzhoulieguozhi -> ../../dongzhoulieguozhi/
    │   ├── zuozhuan          -> ../../zuozhuan/
    │   └── shiji             -> ../../shiji/
    ├── pipeline/                      # Python ETL package
    │   ├── stage1_ingest.py
    │   ├── stage2_chunk.py
    │   ├── stage3_extract.py
    │   ├── stage4_normalize.py
    │   ├── stage5_link.py
    │   ├── stage6_canon_check.py
    │   ├── stage7_load.py
    │   ├── stage9_export.py
    │   ├── prompts/                   # versioned prompt templates
    │   ├── schemas/                   # JSON Schemas per stage boundary
    │   ├── llm_cache.py
    │   ├── reign_table.json           # 鲁公纪年 → BCE lookup
    │   └── cli.py                     # `changjuan extract`, `changjuan re-extract`, ...
    ├── curation/                      # Streamlit app
    │   └── app.py
    ├── data/                          # generated; in .gitignore except export bundles
    │   ├── corpus.sqlite              # immutable after stage 1
    │   ├── changjuan.sqlite           # canonical + candidate_* staging tables
    │   └── exports/
    │       └── changjuan-export-2026-05-v1/
    ├── tests/
    │   ├── golden/                    # annotated chapters as ground truth
    │   ├── unit/
    │   └── integration/
    └── docs/
        └── superpowers/
            └── specs/
                └── 2026-05-20-changjuan-design.md
```

## Appendix B — Glossary

- **东周列国志** — Eastern-Zhou Chronicles, the source novel by 冯梦龙 / 蔡元放; 108 chapters covering ~770–221 BCE.
- **左传** — Zuo Zhuan, the canonical narrative commentary on the 春秋 annals.
- **史记** — Shiji, Sima Qian's universal history; covers the same period plus much more.
- **鲁公纪年** — dating by 鲁 ducal reign years (the convention used in 春秋); requires conversion to BCE for our schema.
- **CHGIS** — China Historical GIS, Harvard's project providing historical coordinate data.
- **Curator** — the human reviewer of pipeline output. For this project, the project owner.
