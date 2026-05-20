---
title: Export contract
type: concept
area: pipeline
updated: 2026-05-20
status: thin
load_bearing: true
affects:
  - pipeline/stage9_export.py
---

## What this is

Stage 9 (`pipeline/stage9_export.py`) produces a versioned export bundle in `data/exports/changjuan-export-<version>/` with two artefacts:

1. **`changjuan.sqlite`** — a read-only SQLite snapshot of all canonical tables.
2. **`manifest.json`** — metadata describing the bundle contents.

## SQLite snapshot: copy-then-drop

The snapshot is built by copying `changjuan.sqlite` verbatim and then dropping implementation tables. This preserves all indexes, views, and constraints without having to re-create them. Two classes of tables are dropped:

- Every table whose name matches `LIKE 'candidate_%'` — these are the staging tables used by stage 7; they are enumerated dynamically at export time so any future `candidate_*` table is stripped automatically (fail-loud if the schema grows a new candidate table without this code being updated).
- `llm_cache` — an extraction implementation detail (content-addressed LLM response cache) that is not part of the knowledge-graph contract.

After the drops, `VACUUM` is called to reclaim space.

## manifest.json contents

```json
{
  "version": "<caller-supplied label>",
  "schema_version": 1,
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

`schema_version` is the integer constant `SCHEMA_VERSION = 1` exported by this module. Consumers should gate on this value if the schema ever changes incompatibly.

`source_corpus_editions` is pulled from `corpus.sqlite.documents.MAX(source_edition) GROUP BY corpus`. If `corpus.sqlite` is absent (e.g. in tests that only exercise the canonical side), this field is an empty object.

## candidate_* prefix stripping: fail-loud safety

Tables are dropped by name-prefix enumeration (`name LIKE 'candidate_%'`), not from a hardcoded allowlist. If a future phase adds a new `candidate_events_v2` table and forgets to update this code, the export will silently strip it — which is the correct behaviour for the export bundle. There is no denormalized JSON per entity in v1; all data is relational.

## Schema version (v1)

v1 is the initial schema. No denormalized JSON files are written alongside the SQLite snapshot. If a downstream consumer requires flat JSON it should query the snapshot directly.

## What would invalidate this article

- Schema version bumped to v2 (incompatible structural change to the canonical tables).
- A new category of "internal-only" tables that are neither `candidate_*` nor `llm_cache` but should still be excluded from exports.
- Addition of per-entity JSON export files.
