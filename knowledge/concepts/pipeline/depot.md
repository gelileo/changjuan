---
title: Depot — catalog & single-file bundles
type: concept
area: pipeline
status: thin
load_bearing: true
affects:
  - pipeline/publish_depot.py
---

## What this is

The depot is a public GitHub repo (`gelileo/changjuan-depot`) that holds a
`catalog.json` and single-file SQLite book bundles. It is the distribution half
of sub-project B1. The reader (B2) fetches the catalog and downloads individual
bundles from `raw.githubusercontent.com` without any server infrastructure.

## Catalog contract

`catalog.json` at the depot root:

```json
{
  "catalog_schema": 1,
  "generated_at": "2026-06-08T00:00:00Z",
  "source": {
    "name": "changjuan depot",
    "baseUrl": "https://raw.githubusercontent.com/gelileo/changjuan-depot/main/"
  },
  "books": [
    {
      "book_id": "dzl",
      "slug": "dongzhoulieguozhi",
      "title": "东周列国志",
      "author": "冯梦龙 / 蔡元放",
      "edition": "明刊本",
      "language": "zh-CN",
      "cover": null,
      "capabilities": ["cast", "timeline", "states"],
      "schema_version": 6,
      "counts": { "persons": 0 },
      "version": "2026-06-v8",
      "bundle": {
        "path": "books/dzl/dzl-2026-06-v8.sqlite",
        "bytes": 16500000,
        "sha256": "<64-hex>"
      }
    }
  ]
}
```

Key fields:
- `catalog_schema` — always `1` (schema version for the catalog envelope itself; separate from the book's `schema_version`).
- `source.baseUrl` — prefix the reader appends to `bundle.path` to form a download URL.
- Each `books[]` entry is the book's `manifest.json` fields plus `language` (defaults to `"zh-CN"` if absent from the manifest) plus a `bundle` descriptor.
- `bundle.path` — relative path within the depot repo: `books/<book_id>/<book_id>-<version>.sqlite`.
- `bundle.bytes` / `bundle.sha256` — computed at publish time from the on-disk file; the reader can use these for integrity verification.
- `prices` (optional) — an object mapping currency codes to amounts (e.g. `{"CNY": 18, "USD": 2.99}`), passed through from the manifest only when present. Free books omit this key entirely; the reader treats an absent `prices` as free.

The catalog is written by `upsert_catalog` (pure function): inserts or replaces the entry for a given `book_id`, then sorts `books[]` by `book_id`. Re-publishing a version overwrites the entry (no duplicates).

## Single-file bundle

A bundle is `graph.sqlite` from the export, copied verbatim. Because `export_enrich.build_chapter_texts` folds the full chapter prose into a `chapter_texts(chapter INTEGER PRIMARY KEY, markdown TEXT)` table, the downloaded file is self-contained — no separate `texts/` directory needed. See [[export-contract]] for the full table inventory.

## `publish_book` orchestrator

`pipeline/publish_depot.py::publish_book(export_dir, depot_dir)`:

1. Reads `manifest.json` from `export_dir` to get `book_id` and `version`.
2. Copies `export_dir/graph.sqlite` → `depot_dir/books/<book_id>/<book_id>-<version>.sqlite` (creates parent dirs).
3. Computes `bytes` and `sha256` of the destination file.
4. Builds a catalog entry via `build_entry(manifest, bundle_path, bytes_, sha256)`.
5. Reads the existing `catalog.json` (empty dict if absent), calls `upsert_catalog`, and writes the result back.
6. Returns the updated catalog dict.

Idempotent per `(book_id, version)`: re-publishing overwrites the bundle file and replaces the catalog entry, leaving no duplicate. Does NOT git-commit or git-push — the operator runs those manually (or via CI).

## `changjuan publish-depot` command

```
changjuan publish-depot --depot <path> --version <v> [--book-id dzl] [--repo-root PATH]
```

Resolves the export dir as `data/books/<book_id>/exports/<slug>-export-<version>/` using `Config` (the same path the `export` command writes to). Exits 1 with a clear message if `manifest.json` is absent. On success echoes: `published <book_id>@<version> → <depot>; catalog has N book(s)`.

See [[cli]] for full option documentation.

## Hosting model

The depot repo is committed binary files (git LFS is not used — the few-books case makes raw `.sqlite` files in history acceptable). The operator publishes with:

```bash
git -C <depot> add catalog.json books/
git -C <depot> commit -m "publish: <book_id> <version>"
# then push / PR against gelileo/changjuan-depot
```

The reader (B2, out of scope for B1) fetches the catalog at cold-start, lists available books, and downloads the bundle on demand.

## What would invalidate this article

- Changing `bundle.path` naming convention (currently `books/<id>/<id>-<version>.sqlite`).
- Changing `catalog_schema` version or adding required top-level fields.
- Adding LFS or switching from `raw.githubusercontent.com` to another CDN.
- Reader-side consumption details (B2 — not yet implemented).
