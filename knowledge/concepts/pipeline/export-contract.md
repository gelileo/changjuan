---
title: Export contract
type: concept
area: pipeline
updated: 2026-05-30
status: thin
load_bearing: true
affects:
  - pipeline/stage9_export.py
---

## What this is

Stage 9 (`pipeline/stage9_export.py`) produces a versioned export bundle in `data/exports/changjuan-export-<version>/` with two artefacts:

1. **`graph.sqlite`** — a read-only SQLite snapshot of all canonical tables.
2. **`manifest.json`** — metadata describing the bundle contents.

## SQLite snapshot: copy-then-drop

The snapshot is built by copying `graph.sqlite` verbatim and then dropping implementation tables. This preserves all indexes, views, and constraints without having to re-create them. Two classes of tables are dropped:

- Every table whose name matches `LIKE 'candidate_%'` — these are the staging tables used by stage 7; they are enumerated dynamically at export time so any future `candidate_*` table is stripped automatically (fail-loud if the schema grows a new candidate table without this code being updated).
- `llm_cache` — an extraction implementation detail (content-addressed LLM response cache) that is not part of the knowledge-graph contract.

After the drops, `VACUUM` is called to reclaim space.

## manifest.json contents

```json
{
  "version": "<caller-supplied label>",
  "schema_version": 2,
  "generated_at": "<ISO 8601 UTC>",
  "counts": {
    "persons": N,
    "person_variants": N,
    ...
  },
  "source_corpus_editions": {
    "dongzhoulieguozhi": "<edition string>"
  }
}
```

`schema_version` is the integer constant `SCHEMA_VERSION = 2` exported by this module. Consumers should gate on this value if the schema ever changes incompatibly.

`source_corpus_editions` is pulled from `corpus.sqlite.documents.MAX(source_edition) GROUP BY corpus`. If `corpus.sqlite` is absent (e.g. in tests that only exercise the canonical side), this field is an empty object.

## candidate_* prefix stripping: fail-loud safety

Tables are dropped by name-prefix enumeration (`name LIKE 'candidate_%'`), not from a hardcoded allowlist. If a future phase adds a new `candidate_events_v2` table and forgets to update this code, the export will silently strip it — which is the correct behaviour for the export bundle. There is no denormalized JSON per entity; all data is relational.

## _count_rows: dynamic enumeration

`_count_rows` enumerates tables via `sqlite_master` (dynamic) rather than a hardcoded `_CANONICAL_TABLES` list. Because `_snapshot_canonical_only` already strips `candidate_*` and `llm_cache`, the dynamic enumeration produces exactly the canonical table set. Any new canonical table added to the schema is automatically included in manifest counts without updating `_count_rows`.

## Schema version history

### v1 (initial)

v1 is the initial schema. Snapshot artifact named `changjuan.sqlite`. No denormalized JSON files are written alongside the SQLite snapshot. If a downstream consumer requires flat JSON it should query the snapshot directly.

### v2 (current)

v2 renames the snapshot artifact to `graph.sqlite`. Subsequent tasks in the export-bundle-v1 plan will add enrichment tables (`citations`, `deed_importance`) and `pinyin` columns; backward-compatible additions will not require a further `schema_version` bump.

## What would invalidate this article

- Schema version bumped beyond v2 (incompatible structural change to the canonical tables).
- A new category of "internal-only" tables that are neither `candidate_*` nor `llm_cache` but should still be excluded from exports.
- Addition of per-entity JSON export files.
