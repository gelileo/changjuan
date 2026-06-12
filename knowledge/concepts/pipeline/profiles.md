---
title: Genre profiles — capability selection and relation-kind vocabulary
type: concept
area: pipeline
updated: 2026-06-11
implemented: feat/genre-profiles (2026-06-11); 2026-06-11 default_group_type added to each profile entry; 2026-06-11 cast profile implemented with domestic relation vocab
status: current
load_bearing: true
references:
  - concepts/pipeline/extraction.md
  - concepts/pipeline/export-contract.md
  - concepts/pipeline/load-and-merge.md
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/profile.py
  - pipeline/**/profile*.py
---

## What a profile is

A profile is declarative data in `data/books/<book_id>/book-meta.json` that tells the pipeline which capabilities to mine for a book and what relation-kind vocabulary is valid. Two fields:

- `"profile"` — a string key selecting a profile from `pipeline/profile.py::PROFILES` (e.g. `"history"`).
- `"capabilities"` — a list of fine-grained ETL capability strings (e.g. `["persons","relations","events","chronology","geography","groups"]`).

The profile drives: extraction prompt-pack selection, which pipeline stages are active, and relation-kind validation in the loader.

## Two capability vocabularies

The pipeline uses two distinct vocabularies that must not be confused:

| Layer | Vocabulary | Where declared |
|---|---|---|
| ETL (fine-grained) | `persons`, `relations`, `events`, `chronology`, `geography`, `groups`, `themes` | `book-meta.json "capabilities"` |
| Reader tabs (coarse) | `cast`, `timeline`, `groups`, `themes` | derived; written to `manifest.json "capabilities"` |

The ETL capabilities control what the pipeline extracts. The reader capabilities control which tabs the reader app surfaces. They are never the same field.

### Derivation table

`pipeline/profile.py::derive_reader_capabilities(etl_caps)` maps fine-grained → coarse via `_READER_TAB_RULES` (order preserved — defines canonical tab order):

| Reader tab | Required ETL cap |
|---|---|
| `cast` | `persons` |
| `timeline` | `chronology` |
| `groups` | `groups` |
| `themes` | `themes` |

Only tabs whose required ETL cap is present in the book's capability list appear in the manifest. Relations render inside the cast tab; a dateless event list does not qualify as a timeline.

### Export plumbing

`pipeline/stage9_export.py::manifest_reader_capabilities(book_meta)` calls `derive_reader_capabilities` and writes the result to `manifest.json "capabilities"`. `SCHEMA_VERSION = 7` marks bundles produced under the full State→Group rename + genre-profile backbone.

## default_group_type — loader-set collective kind

Each profile entry in `PROFILES` carries a `default_group_type` key (string). `pipeline/profile.py::default_group_type(profile)` returns this value; it raises `UnknownProfileError` for an unknown profile (consistent with `relation_kinds_for`). The Stage 7 groups loader (`load_candidate_groups`) calls this helper and stamps `groups.group_type = default_group_type(profile)` on every new group it creates. This value is NEVER merged from `candidate_groups` — it is profile-driven, not extraction-driven.

The history profile sets `default_group_type = 'state'`. Future profiles (e.g. `cast` for 红楼梦 family networks) may set `'clan'`, `'faction'`, etc.

## Relation-kind vocabulary as profile config

Before the genre-profile backbone, `person_relations.kind` was validated by a DB CHECK constraint in `canonical_schema.sql`. That constraint was removed when the profile registry landed; validation now happens in the loader (`pipeline/stage7_load/relations.py`) against `_VALID_PERSON_RELATION_KINDS` and `_VALID_EVENT_RELATION_KINDS`, which mirror the profile registry.

`pipeline/profile.py::relation_kinds_for(profile, relation)` returns a set copy of the allowed kinds for a given profile and relation type (`"person"` or `"event"`). Returns a copy — callers cannot mutate the live registry. Raises `UnknownProfileError` for an unknown profile; raises `ValueError` if `relation` is not `"person"` or `"event"`.

### history profile relation kinds

Person relations (11): `parent`, `child`, `spouse`, `sibling`, `mentor`, `ruler`, `minister`, `ally`, `rival`, `killed_by`, `clan_member`.

Event relations (3): `causes`, `precedes`, `related`.

## The `sta:` id stability rule

The grouping entity is now `groups` (table, columns, and code vocabulary), but `sta:` id prefixes on data values (e.g. `sta:jin`, `sta:zhou`) are **unchanged**. State-type groups keep `sta:` ids so that reign resolution in `pipeline/dates.py` and `data/reigns/sta_*.yaml` requires no data migration. The rename is a schema/code rename, not a data rename. `group_type = 'state'` identifies these rows.

## Defined profiles

| Profile | Capabilities | Use case |
|---|---|---|
| `history` | persons, relations, events, chronology, geography, groups | 东周列国志 and similar dynastic histories |
| `cast` | persons, relations, events, groups, themes | 红楼梦 slice — adds `themes`; no chronology/geography |

The `cast` profile uses domestic relation vocabulary (spouse, master, servant, romantic, concubine, etc.) with no history-specific terms (ruler, minister, killed_by); default `group_type = 'clan'`.

## Capability-guarded behaviors

Any pipeline stage or export step that is gated on a capability checks the book-meta `"capabilities"` list directly. Examples: a book without `"chronology"` produces no timeline tab; without `"groups"` the reader shows no groups tab. Future stages (themes indexer, etc.) gate similarly.

## What would invalidate this article

- Adding a new ETL capability or reader tab to `_READER_TAB_RULES`.
- Adding a new profile to `PROFILES` (add a row to the defined-profiles table above).
- Changing the `relation_kinds_for` signature or error types.
- Re-introducing a DB CHECK constraint for relation kinds (would conflict with the profile-config approach).
