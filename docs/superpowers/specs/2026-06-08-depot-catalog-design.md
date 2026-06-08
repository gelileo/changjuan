# 书库 — Depot Catalog & Factory Publish (B1) (design)

**Date:** 2026-06-08
**Status:** designed (not yet implemented)
**Scope:** changjuan (factory) + a new sibling `changjuan-depot` repo. Sub-project
**B1** of the book-distribution ecosystem: produce a static **catalog** + hosted
single-file **bundles** so the reader (sub-project B2) can later fetch, download,
and render books it does not ship. B1 does NOT touch the reader.

---

## 1. Goal & context

Sub-project A made the reader a multi-book host with a `BundledBook` registry seam
("the depot will implement a second way behind this interface"). B1 builds the
production + distribution half so a book the reader did not bundle can be served
over plain HTTP.

The model follows the proven `chinese-lesson-depot` precedent: a public git repo
holding a `catalog.json` + content files, served via `raw.githubusercontent.com`,
the consumer resolving `baseUrl + relativePath`.

**Two decisions fixed during brainstorming:**
- **Hosting:** a public GitHub repo with committed files (free, zero infra; ~15 MB
  binaries bloat git history over versions — accepted for a few books).
- **Packaging:** a book is **one `.sqlite` file** — the chapter prose is folded
  into `graph.sqlite` as a `chapter_texts` table, so distribution is a single
  download (no 108-file fan-out, no archive/unzip dependency).

## 2. Code reality (grounding)

Verified against the factory:
- `pipeline/stage9_export.py::export_bundle(...)` writes `manifest.json` (carrying
  `SCHEMA_VERSION`), snapshots the canonical tables into `graph.sqlite`, then copies
  `readable_dir/ch[0-9]*.md` → `out_dir/texts/`.
- `pipeline/export_enrich.py` holds the in-place snapshot mutators
  (`build_citations_table`, `add_pinyin_columns`, `build_deed_importance`,
  `add_prominence`, `add_event_prominence`, `add_narrative_seq`,
  `add_state_prominence`) — each opens `graph.sqlite` and adds a table/column. The
  new `chapter_texts` builder follows this exact pattern.
- `pipeline/cli.py` is the subcommand host (argparse `add_parser` + `*_cmd`
  handlers); `publish-depot` is added here.
- Export bundles live at `data/books/<book_id>/exports/<slug>-export-<version>/`
  = `graph.sqlite` + `manifest.json` + `texts/`. Current `SCHEMA_VERSION` = 5.

## 3. The catalog contract (the seam between B1 and B2)

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
      "counts": { "...": 0 },
      "version": "2026-06-v8",
      "bundle": {
        "path": "books/dzl/dzl-2026-06-v8.sqlite",
        "bytes": 16500000,
        "sha256": "<hex>"
      }
    }
  ]
}
```

Contract rules:
- Each `books[]` entry **is the book's `manifest.json`** (all of its fields) **plus**
  a `bundle` object. B2 therefore needs no separate manifest fetch — the catalog
  entry is sufficient to register the book and the `.sqlite` is the only payload.
- `bundle.path` is **relative to `source.baseUrl`**; the reader downloads
  `baseUrl + path`. The bundle is a single self-contained `.sqlite` (canonical
  tables + the enrichment tables + `chapter_texts`).
- One entry per `book_id` = its **latest** version (no version history in v1).
- `bytes` supports download-progress UI; `sha256` supports integrity/dedupe — B2
  decides whether to enforce it (the field ships regardless).
- `catalog_schema` versions the catalog format itself, independent of any book's
  `schema_version`.

## 4. Factory change A — `chapter_texts` in the export

Add `build_chapter_texts(graph_db: Path, readable_dir: Path) -> None` to
`pipeline/export_enrich.py`:
- Creates `chapter_texts(chapter INTEGER PRIMARY KEY, markdown TEXT)` (idempotent —
  `CREATE TABLE IF NOT EXISTS`, then clear+repopulate).
- Iterates `readable_dir.glob("ch[0-9]*.md")` (same glob the texts/ copy uses),
  parses the chapter number from the filename (`chNN.md` → `NN`), inserts
  `(chapter, file_text)` in one `executemany` pass.
- Tolerates an absent/empty `readable_dir` (no rows) — mirrors the `texts/` guard.

Wire it into `export_bundle` after the canonical snapshot (alongside the other
`export_enrich` calls), passing the same `readable_dir`. The export continues to
write `texts/` unchanged — the table is **purely additive**; the bundled reader is
unaffected, only downloaded books (B2) read it.

Bump `SCHEMA_VERSION` 5 → 6 so the manifest/catalog advertise the new table.

## 5. Factory change B — `changjuan publish-depot`

New module `pipeline/publish_depot.py` + a `publish-depot` subcommand in
`pipeline/cli.py`.

**Inputs:** an export bundle to publish (resolved from `--book <book_id>`
+ `--version <v>`, or `--export-dir <path>`) and `--depot <path>` (the local
`changjuan-depot` working tree).

**Behavior (pure-ish, filesystem side effects only):**
1. Resolve the export dir; read its `manifest.json` and `graph.sqlite`.
2. Copy `graph.sqlite` → `<depot>/books/<book_id>/<book_id>-<version>.sqlite`
   (creating dirs). Compute `bytes` (file size) and `sha256` (streamed).
3. Build the catalog entry = manifest fields + `bundle {path, bytes, sha256}`.
4. Load `<depot>/catalog.json` if present (else seed `{catalog_schema, source, books: []}`),
   **replace** the entry whose `book_id` matches (or append), sort `books` by
   `book_id`, stamp `generated_at`, write it back (UTF-8, indent 2, `ensure_ascii: False`).

Factor the catalog mutation as a **pure function**
`upsert_catalog(catalog: dict, entry: dict, generated_at: str) -> dict` so it is
unit-testable without the filesystem. The command does **not** git-commit or push —
that is a documented manual step.

## 6. The depot repo (`changjuan-depot`)

A new sibling repo:

```
changjuan-depot/
├── catalog.json
├── books/
│   └── dzl/
│       └── dzl-2026-06-v8.sqlite
└── README.md          # documents the contract + baseUrl + how it's published
```

Hosted as a **public GitHub repo**, content served via
`https://raw.githubusercontent.com/gelileo/changjuan-depot/main/`. B1 scaffolds the
repo locally and publishes dzl at v6 (a fresh export carrying `chapter_texts`).
Creating the remote (`gh repo create`) and the first push are **manual steps the
spec/README document** — not automated here.

## 7. Living documentation (changjuan same-task rule)

Updated in the same commits as the code they describe:
- `knowledge/concepts/pipeline/export-contract.md` — the `chapter_texts` table +
  `SCHEMA_VERSION` 6.
- `knowledge/concepts/pipeline/depot.md` (new) — the catalog contract, single-file
  bundle, and the `publish-depot` command; add its row to the article-mapping table.
- `knowledge/concepts/runtime/cli.md` — the `publish-depot` subcommand.
- `knowledge/log.md` — a compile entry listing the touched articles.

## 8. Testing

- `build_chapter_texts`: against a tiny fixture `readable/` dir (e.g. `ch01.md`,
  `ch02.md`), assert the table exists, has one row per chapter with the correct
  chapter number, and the markdown round-trips byte-for-byte; assert idempotent
  re-run.
- `upsert_catalog` (pure): inserting a new book appends; re-publishing the same
  `book_id` **replaces** its entry (no duplicate); `books` stays sorted;
  `generated_at` is set from the passed value.
- `publish_depot` end-to-end (tmp dirs): given a fixture export, the single-file
  bundle is copied to the right path, `bytes`/`sha256` match the file, and
  `catalog.json` is written/updated correctly.
- The existing pytest suite stays green.

## 9. Out of scope

- **B2** entirely: the reader fetching the catalog, the download manager + states,
  persisting bundles on-device, the DB-backed chapter-text loader for downloaded
  books, and generalizing the registry/openers to serve them.
- Cover-art generation (catalog carries `cover: null`).
- Catalog **version history** (latest-only per book).
- `sha256` **verification enforcement** (field is published; enforcing is B2's call).
- Automated git commit/push of the depot or remote repo creation.
- Re-vendoring the reader's bundled dzl to v6 (independent; the bundled path keeps
  using its Metro `texts/` assets until separately refreshed).
