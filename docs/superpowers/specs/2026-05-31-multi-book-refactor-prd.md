# PRD — Multi-book refactor (changjuan as a multi-book ETL repo)

**Status:** Implemented 2026-06-01 (Tier 1 + Tier 2 core; per-stage --book-id threading deferred to book #2)
**Date:** 2026-05-31
**Repo:** `changjuan` (Python ETL + export)
**Approach:** B — stable internal `book_id` decoupled from a human-facing `slug`

---

## 1. Summary

`changjuan` currently extracts and hosts exactly one book (东周列国志). The
reader (`changjuan-reader`) is designed to host multiple books, so `changjuan`
should too. This refactor makes `book_id` a first-class axis: per-book working
files and per-book export bundles, named by a human `slug` (e.g.
`dongzhoulieguozhi-export-2026-06-v2`) while keeping stable short ids internally.

**Approach B (chosen):** keep `book_id = dzl` as the stable internal identifier
(it is already baked into chunk ids `chk:dzl:…` and the manifest), and add a
`slug` for human-facing folder/bundle names. **No entity-id or chunk-id
migration.** This is the low-risk path; the alternative (A — rename `dzl` →
`dongzhoulieguozhi` everywhere) was rejected because it forces re-prefixing every
chunk id + the export `citations` table for cosmetic gain.

## 2. Current state (what exists today)

**Already book-aware**
- `data/books/<book_id>/book-meta.json` (book_id, title, author, edition, capabilities).
- `changjuan export --book-id` (default `dzl`) loads book-meta → writes `book_id` into `manifest.json`.
- Corpus chunk ids carry the book prefix: `chk:dzl:100:0`.

**Single-book hardcoded (to fix)**
- Export dir: `f"changjuan-export-{version}"` (ignores book).
- Flat working files: `data/changjuan.sqlite`, `data/corpus.sqlite`, `data/{extractions,readable,logs,qa,reigns}/`.
- `data/changjuan.sqlite` hardcoded in ~10 places (`pipeline/cli.py` ×8, `pipeline/db.py`, `pipeline/smoke_checks.py`), plus `Config.canonical_db`/`corpus_db`.
- Canonical entity ids are **not** book-scoped (`per:专毅`, `evt:上书`) — left as-is (see §6).

## 3. Goals / Non-goals

**Goals**
- Per-book working files and exports under `data/books/<book_id>/`.
- Every pipeline/CLI command takes `--book-id` (default `dzl`); no command assumes a single book.
- Export bundle dir = `<slug>-export-<version>` (slug from book-meta).
- Adding a second book never touches another book's data.
- The existing `dzl` data migrates in place with **no id changes** and a byte-identical re-export (modulo the new dir name).

**Non-goals**
- Re-prefixing entity/chunk ids (approach A).
- A shared cross-book database or `book_id` discriminator columns. One book = one DB = one export bundle.
- Cross-book entity linking / dedup (books are independent; a figure appearing in two books is two records by design).
- Reader-side changes beyond confirming it keys on `manifest.book_id` (see §7).

## 4. Design (approach B)

### 4.1 Book identity
`book-meta.json` gains a `slug`:
```json
{ "book_id": "dzl", "slug": "dongzhoulieguozhi", "title": "东周列国志", ... }
```
- `book_id` (short, stable) → internal: chunk-id prefix, manifest `book_id`, folder key.
- `slug` (human) → folder/bundle display names only. Defaults to `book_id` if absent.

### 4.2 Target storage layout
```
data/books/<book_id>/
  book-meta.json        # tracked
  corpus.sqlite         # gitignored
  canonical.sqlite      # gitignored  (renamed from data/changjuan.sqlite — "changjuan" is the tool, not the book)
  extractions/          # gitignored
  readable/             # gitignored
  logs/  qa/            # gitignored
  reigns/               # tracked (curated; reign tables are book/era-specific)
  exports/<slug>-export-<version>/   # gitignored
```
`.bak` snapshots: `data/books/<book_id>/*.bak-*` (gitignored, per existing rule).

### 4.3 Config (`pipeline/config.py`)
Path accessors take `book_id`:
```python
def book_dir(self, book_id: str) -> Path:      return self.data_dir / "books" / book_id
def canonical_db(self, book_id: str) -> Path:  return self.book_dir(book_id) / "canonical.sqlite"
def corpus_db(self, book_id: str) -> Path:     return self.book_dir(book_id) / "corpus.sqlite"
def readable_dir(self, book_id: str) -> Path:  return self.book_dir(book_id) / "readable"
def exports_dir(self, book_id: str) -> Path:   return self.book_dir(book_id) / "exports"
# extractions_dir, logs_dir, qa_dir, reigns_dir likewise
```
(Keep a deprecation-free transition: every caller must pass `book_id`.)

### 4.4 CLI (`pipeline/cli.py`)
- Add `book_id: str = typer.Option("dzl", "--book-id")` to **every** stage command (ingest, chunk, extract, extract-load, link, load, export, the date-triage commands, smoke). Currently 8 commands hardcode `open_canonical_db(repo_root/"data"/"changjuan.sqlite")` — replace with `cfg.canonical_db(book_id)`.
- `export`: `out_dir = cfg.exports_dir(book_id) / f"{slug}-export-{version}"` where `slug = meta.get("slug", book_id)`.

### 4.5 Export (`pipeline/stage9_export.py`)
- `export_bundle` already takes `book_meta`; pass `slug` through for the dir name (or have the CLI own the dir name and pass `out_dir`, which it already does). Manifest keeps `book_id`; optionally add `slug`.
- `prominence_overrides` path → `cfg.book_dir(book_id) / "prominence_overrides.yaml"`.

### 4.6 .gitignore
Replace flat ignores with per-book globs; keep curated files tracked:
```
data/books/*/corpus.sqlite
data/books/*/canonical.sqlite
data/books/*/canonical.sqlite.*-bak
data/books/*/exports/
data/books/*/extractions/
data/books/*/readable/
data/books/*/logs/
data/books/*/qa/
# tracked: data/books/*/book-meta.json, data/books/*/reigns/**, data/books/*/prominence_overrides.yaml
```

## 5. Migration (one-time, for existing `dzl`)
1. `mkdir -p data/books/dzl`; `git mv`/move curated files (`reigns/`, `prominence_overrides.yaml`) under it; move gitignored DBs/dirs with plain `mv`.
2. Rename `data/changjuan.sqlite` → `data/books/dzl/canonical.sqlite` (checkpoint WAL first; see WAL-safety note in `concepts/pipeline/architecture.md` — never `rm` a live `-wal`).
3. Add `"slug": "dongzhoulieguozhi"` to `data/books/dzl/book-meta.json`.
4. Update `.gitignore` (§4.6).
5. Re-run `changjuan export 2026-06-v2 --book-id dzl` → produces `data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v2/`.
6. Verify the new bundle's `graph.sqlite` is row-for-row identical to the pre-refactor one (same counts, same `schema_version=3`).

## 6. Entity-id decision (why no migration)
Per-book DBs give file-level isolation, and the reader loads **one `graph.sqlite`
per book**, so unprefixed ids (`per:晋文公`) cannot collide across books. Keeping
ids unprefixed avoids touching `persons`/`events`/`person_relations`/
`entity_citations`/`deed_importance`/`prominence` and the reader's deep-link
routes. Chunk ids stay `chk:dzl:…` (already book-scoped; untouched).

## 7. Reader compatibility (verify, don't change)
- The reader must identify a book by `manifest.book_id` (`dzl`), **not** the bundle directory name — confirm in `changjuan-reader` before renaming bundles it vendors. If it currently keys on the dir name, fix that first.
- Bundle dir name is cosmetic to the reader; the manifest is the contract.

## 8. Acceptance criteria
- `changjuan export 2026-06-v2 --book-id dzl` writes `data/books/dzl/exports/dongzhoulieguozhi-export-2026-06-v2/`; manifest `book_id == "dzl"`, `schema_version == 3`.
- The bundle's `graph.sqlite` matches the pre-refactor v2 bundle on all table counts.
- No command reads/writes a flat `data/changjuan.sqlite` or `data/corpus.sqlite` anymore (grep clean).
- A second book can be added by creating `data/books/<id>/book-meta.json` + corpora symlink and running the pipeline with `--book-id <id>`, with zero edits to `dzl` data.
- All tests pass (update fixtures/paths that hardcode `data/changjuan.sqlite`); drift check green (touches `pipeline/cli.py`→cli.md, `config.py`→configuration.md, stage9→export-contract/architecture, schemas unaffected).

## 9. Risks / notes
- Cross-cutting: ~10 hardcoded paths + Config + tests + `.gitignore`. Do it as one focused change, not piecemeal.
- WAL safety during the DB move (checkpoint TRUNCATE, then move; never delete a live `-wal`).
- `reigns/` is currently shared at `data/reigns/`; confirm whether it's truly book-specific (it is for date resolution) before moving — or keep a shared `data/reigns/` if a future book reuses the same calendar.
- Ship order: Tier-1 bundle-name change (`<slug>-export-<v>`) can land first and independently; Tier-2 storage move follows.

## 10. Touch points
`pipeline/config.py`, `pipeline/cli.py` (all stage commands), `pipeline/db.py`,
`pipeline/smoke_checks.py`, `pipeline/stage9_export.py`, `data/books/dzl/book-meta.json`,
`.gitignore`, tests under `tests/**` that hardcode `data/changjuan.sqlite`,
knowledge: `concepts/runtime/configuration.md`, `concepts/runtime/cli.md`,
`concepts/pipeline/export-contract.md`, `concepts/pipeline/architecture.md`,
`knowledge/log.md`.
