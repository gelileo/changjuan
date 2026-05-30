# Export Bundle v1 Prerequisites — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the stage-9 export so the frozen bundle is everything the 长卷 Reader app needs: a lean `graph.sqlite` carrying denormalized citation passages, build-time pinyin, and build-time deed-importance; a separate `texts/` payload; and a manifest with book identity + capabilities.

**Architecture:** The export already copies the canonical DB and strips candidate tables. We extend it with **post-snapshot enrichment passes** that mutate the copied `graph.sqlite` (add a `citations` table from `corpus.sqlite`, add `pinyin` columns, add a `deed_importance` table), rename the artifact to `graph.sqlite`, emit a `texts/` payload from `data/readable/`, and enrich `manifest.json` from a per-book metadata file. Schema version bumps to 2.

**Tech Stack:** Python ≥3.12, Typer CLI, SQLite (stdlib `sqlite3`), `pypinyin` (new dep), pytest (`uv run pytest`), structlog.

---

## Conventions for every task in this plan

1. **TDD:** failing test → run-and-see-it-fail → minimal implementation → run-and-see-it-pass → commit.
2. **Run tests with `uv run pytest`** from the repo root `/Users/kunlu/Projects/gelileo/unroll/changjuan`.
3. **Drift-check hook (load-bearing):** `pipeline/stage9_export.py` is mapped to `knowledge/concepts/pipeline/export-contract.md` in `CLAUDE.md`'s article-mapping table, and a pre-commit hook enforces it. **Every commit that touches `stage9_export.py` MUST also stage an edit to `export-contract.md` and append a line to `knowledge/log.md`,** or the commit is rejected. Each task below includes that doc step explicitly.
4. **Frequent commits:** one commit per task (code + test + docs together).
5. **Never** use `--no-verify`.

## File Structure (created / modified across the plan)

- **Modify** `pipeline/stage9_export.py` — bundle builder; gains enrichment passes + new artifact layout. (~currently 96 lines.)
- **Create** `pipeline/export_enrich.py` — pure, testable enrichment helpers (citation text, pinyin, deed importance) kept out of the orchestration file so each has one responsibility and is unit-testable without the full bundle.
- **Modify** `pipeline/cli.py:93-102` — `export` command gains `--book-id`.
- **Modify** `pipeline/config.py:22-36` — add `books_dir` and `readable_dir` properties.
- **Create** `data/books/dzl/book-meta.json` — 东周列国志 identity + capabilities.
- **Modify** `pyproject.toml:6-13` — add `pypinyin`.
- **Modify** `tests/unit/test_stage9_export.py` — update existing assertions + add bundle-layout tests.
- **Create** `tests/unit/test_export_enrich.py` — unit tests for the enrichment helpers.
- **Modify** `knowledge/concepts/pipeline/export-contract.md` + `knowledge/log.md` — kept in sync each task.

---

## Task 1: Bump bundle to v2 layout (`graph.sqlite`, `schema_version: 2`)

Rename the snapshot artifact from `changjuan.sqlite` to `graph.sqlite` and bump the schema version. This is the smallest standalone change and updates the one existing test that asserts the old filename.

**Files:**

- Modify: `pipeline/stage9_export.py` (the `SCHEMA_VERSION` constant near top; the snapshot filename in `export_bundle`)
- Modify: `tests/unit/test_stage9_export.py` (assertions referencing `changjuan.sqlite` / `schema_version`)
- Modify: `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Update the existing test to expect the new layout**

In `tests/unit/test_stage9_export.py`, change the existing `test_export_creates_manifest_and_sqlite` assertions:

```python
    export_bundle(src, out, version="test-v1")
    assert (out / "manifest.json").is_file()
    assert (out / "graph.sqlite").is_file()
    assert not (out / "changjuan.sqlite").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["version"] == "test-v1"
    assert manifest["schema_version"] == 2
    assert manifest["counts"]["persons"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_stage9_export.py::test_export_creates_manifest_and_sqlite -v`
Expected: FAIL — bundle still writes `changjuan.sqlite`; `schema_version` is `1`.

- [ ] **Step 3: Make the change**

In `pipeline/stage9_export.py`: set `SCHEMA_VERSION = 2`, and change the snapshot path from `out_dir / "changjuan.sqlite"` to `out_dir / "graph.sqlite"` (the `_snapshot_canonical_only` call target).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_stage9_export.py -v`
Expected: PASS.

- [ ] **Step 5: Update the contract doc + log (required by the drift hook)**

In `knowledge/concepts/pipeline/export-contract.md`: change the bundle-layout line from `changjuan.sqlite` to `graph.sqlite`, and bump the documented `schema_version` to `2`, adding a sentence: "v2 renames the snapshot to `graph.sqlite` and adds enrichment tables (`citations`, `deed_importance`) and `pinyin` columns; see tasks below."

Append to `knowledge/log.md`:

```markdown
- 2026-05-30 — export-contract: bundle artifact renamed `changjuan.sqlite`→`graph.sqlite`, schema_version→2 (reader-app prereq). Touched: concepts/pipeline/export-contract.md.
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/stage9_export.py tests/unit/test_stage9_export.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): v2 bundle layout — rename to graph.sqlite, schema_version=2"
```

---

## Task 2: Denormalize citation passages into `graph.sqlite`

For every distinct `entity_citations.citation_id` (a chunk id like `chk:dzl:1:0`), look up its passage text from `corpus.sqlite`'s `chunks` table and write a `citations(citation_id, document_id, paragraph_start, paragraph_end, text)` table into `graph.sqlite`. This is the critical-path change: without it the app cannot render any citation.

**Files:**

- Create: `pipeline/export_enrich.py`
- Create: `tests/unit/test_export_enrich.py`
- Modify: `pipeline/stage9_export.py` (call the new pass; thread `corpus_db`)
- Modify: `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing test for the citation pass**

Create `tests/unit/test_export_enrich.py`:

```python
import sqlite3
from pathlib import Path

from pipeline.export_enrich import build_citations_table


def _mk_graph(path: Path) -> None:
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT);"
        )
        c.executemany(
            "INSERT INTO entity_citations VALUES (?,?,?);",
            [
                ("person", "per:a", "chk:dzl:1:0"),
                ("person", "per:a", "chk:dzl:1:0"),  # duplicate id
                ("event", "evt:x", "chk:dzl:2:5"),
            ],
        )


def _mk_corpus(path: Path) -> None:
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )
        c.executemany(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?);",
            [
                ("chk:dzl:1:0", "dzl:1", 0, 0, "周幽王嬖褒姒。", "h1"),
                ("chk:dzl:2:5", "dzl:2", 5, 6, "郑伯克段于鄢。", "h2"),
                ("chk:dzl:9:9", "dzl:9", 9, 9, "uncited chunk", "h3"),
            ],
        )


def test_build_citations_table_denormalizes_cited_chunks(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    _mk_graph(graph)
    _mk_corpus(corpus)

    build_citations_table(graph, corpus)

    with sqlite3.connect(graph) as c:
        rows = dict(
            (cid, txt)
            for cid, txt in c.execute("SELECT citation_id, text FROM citations;")
        )
    # one row per *distinct* cited chunk; uncited chunk excluded
    assert rows == {
        "chk:dzl:1:0": "周幽王嬖褒姒。",
        "chk:dzl:2:5": "郑伯克段于鄢。",
    }


def test_build_citations_table_raises_when_chunk_missing(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    _mk_graph(graph)
    with sqlite3.connect(corpus) as c:
        c.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )  # empty — cited chunks absent
    import pytest

    with pytest.raises(ValueError, match="2 cited chunk"):
        build_citations_table(graph, corpus)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_export_enrich.py -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.export_enrich`.

- [ ] **Step 3: Implement `build_citations_table`**

Create `pipeline/export_enrich.py`:

```python
"""Post-snapshot enrichment passes for the export bundle (stage 9).

Each function mutates the already-copied graph.sqlite in place. Kept separate
from stage9_export.py orchestration so each pass has one responsibility and is
unit-testable without building a full bundle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def build_citations_table(graph_db: Path, corpus_db: Path) -> None:
    """Create `citations` in graph_db, denormalizing each distinct cited chunk's
    passage text from corpus_db's `chunks` table.

    Raises ValueError if any cited chunk id is absent from the corpus (fail loud:
    the reader's one-tap-to-source feature must not silently lose passages).
    """
    with sqlite3.connect(graph_db) as g:
        cited = [r[0] for r in g.execute(
            "SELECT DISTINCT citation_id FROM entity_citations;"
        )]
        g.execute("DROP TABLE IF EXISTS citations;")
        g.execute(
            "CREATE TABLE citations ("
            " citation_id TEXT PRIMARY KEY,"
            " document_id TEXT,"
            " paragraph_start INTEGER,"
            " paragraph_end INTEGER,"
            " text TEXT NOT NULL);"
        )
        if not cited:
            return
        with sqlite3.connect(corpus_db) as cor:
            placeholders = ",".join("?" * len(cited))
            found = {
                cid: (cid, doc, ps, pe, txt)
                for cid, doc, ps, pe, txt in cor.execute(
                    "SELECT id, document_id, paragraph_start, paragraph_end, text "
                    f"FROM chunks WHERE id IN ({placeholders});",
                    cited,
                )
            }
        missing = [c for c in cited if c not in found]
        if missing:
            raise ValueError(
                f"{len(missing)} cited chunk(s) absent from corpus "
                f"(e.g. {missing[:3]}); cannot denormalize citation text."
            )
        g.executemany(
            "INSERT INTO citations VALUES (?,?,?,?,?);",
            [found[c] for c in cited],
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_export_enrich.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Wire the pass into `export_bundle` and thread `corpus_db`**

In `pipeline/stage9_export.py`:
- Add import: `from pipeline.export_enrich import build_citations_table`.
- Extend the signature to accept the corpus path: `def export_bundle(src_db: Path, out_dir: Path, *, version: str, corpus_db: Path) -> Path:`.
- After `_snapshot_canonical_only(src_db, snap_path)` and before the manifest is written, call: `build_citations_table(snap_path, corpus_db)`.
- Update the existing `_source_editions(src_db)` call site if it derived the corpus path internally; pass `corpus_db` consistently.

In `pipeline/cli.py:93-102`, update the call: `export_bundle(cfg.canonical_db, out_dir, version=version, corpus_db=cfg.corpus_db)`.

In `tests/unit/test_stage9_export.py`, the existing test now needs a corpus DB. Update `test_export_creates_manifest_and_sqlite` to create an empty-but-valid corpus and pass it:

```python
    corpus = tmp_path / "corpus.sqlite"
    with connect(corpus) as cc:
        cc.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )
    export_bundle(src, out, version="test-v1", corpus_db=corpus)
```

(The seeded `per:a` has no entity_citations row, so the citations table is created empty and no chunk lookup fails.)

- [ ] **Step 6: Run the full export test file**

Run: `uv run pytest tests/unit/test_stage9_export.py tests/unit/test_export_enrich.py -v`
Expected: PASS.

- [ ] **Step 7: Update the contract doc + log**

In `export-contract.md`, add to the bundle/schema description: "`graph.sqlite` includes a `citations(citation_id, document_id, paragraph_start, paragraph_end, text)` table denormalized from `corpus.sqlite`'s `chunks` for every distinct cited chunk. The export **fails loud** if a cited chunk is missing from the corpus. Requires `corpus.sqlite` present at export time."

Append to `knowledge/log.md`:

```markdown
- 2026-05-30 — export-contract: graph.sqlite now carries denormalized `citations` text (joined from corpus.chunks); fail-loud on missing chunk. Touched: concepts/pipeline/export-contract.md.
```

- [ ] **Step 8: Commit**

```bash
git add pipeline/export_enrich.py pipeline/stage9_export.py pipeline/cli.py tests/unit/test_export_enrich.py tests/unit/test_stage9_export.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): denormalize citation passages from corpus into graph.sqlite"
```

---

## Task 3: Manifest book identity + capabilities

Add per-book metadata (title, author, edition, cover, capabilities) to `manifest.json`, sourced from a `book-meta.json` file so it is authored, not guessed.

**Files:**

- Create: `data/books/dzl/book-meta.json`
- Modify: `pipeline/config.py:22-36` (add `books_dir`)
- Modify: `pipeline/stage9_export.py` (accept `book_meta: dict`, merge into manifest)
- Modify: `pipeline/cli.py` (add `--book-id`, load the meta file)
- Modify: `tests/unit/test_stage9_export.py`
- Modify: `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_stage9_export.py`:

```python
def test_manifest_includes_book_identity_and_capabilities(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    out = tmp_path / "exports" / "b"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    with connect(corpus) as cc:
        cc.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )
    meta = {
        "book_id": "dzl",
        "title": "东周列国志",
        "author": "冯梦龙 / 蔡元放",
        "edition": "明刊本",
        "cover": None,
        "capabilities": ["cast", "timeline", "states"],
    }
    export_bundle(src, out, version="b", corpus_db=corpus, book_meta=meta)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["title"] == "东周列国志"
    assert manifest["author"] == "冯梦龙 / 蔡元放"
    assert manifest["capabilities"] == ["cast", "timeline", "states"]
    assert manifest["book_id"] == "dzl"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_stage9_export.py::test_manifest_includes_book_identity_and_capabilities -v`
Expected: FAIL — `export_bundle() got an unexpected keyword argument 'book_meta'`.

- [ ] **Step 3: Implement**

In `pipeline/stage9_export.py`, extend the signature to `def export_bundle(src_db, out_dir, *, version, corpus_db, book_meta) -> Path:` and merge selected keys into the manifest dict before writing:

```python
    manifest: dict[str, object] = {
        "version": version,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "book_id": book_meta["book_id"],
        "title": book_meta["title"],
        "author": book_meta.get("author"),
        "edition": book_meta.get("edition"),
        "cover": book_meta.get("cover"),
        "capabilities": book_meta["capabilities"],
        "counts": counts,
        "source_corpus_editions": _source_editions(corpus_db),
    }
```

Create `data/books/dzl/book-meta.json`:

```json
{
  "book_id": "dzl",
  "title": "东周列国志",
  "author": "冯梦龙 / 蔡元放",
  "edition": "明刊本",
  "cover": null,
  "capabilities": ["cast", "timeline", "states"]
}
```

In `pipeline/config.py`, add after `exports_dir`:

```python
    @property
    def books_dir(self) -> Path:
        return self.data_dir / "books"
```

In `pipeline/cli.py`, update the `export` command:

```python
@app.command()
def export(
    version: str = typer.Argument(..., help="Export bundle version label."),
    book_id: str = typer.Option("dzl", help="Book id under data/books/."),
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 9: freeze a versioned export bundle."""
    cfg = _cfg(repo_root)
    meta = json.loads((cfg.books_dir / book_id / "book-meta.json").read_text("utf-8"))
    out_dir = cfg.exports_dir / f"changjuan-export-{version}"
    export_bundle(cfg.canonical_db, out_dir, version=version,
                  corpus_db=cfg.corpus_db, book_meta=meta)
    typer.echo(f"export bundle written to {out_dir}")
```

(Add `import json` to `cli.py` if not already present.)

Update the two existing tests from Task 1/2 that call `export_bundle(...)` to pass `book_meta=meta` with a minimal dict (reuse the `meta` literal above).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_stage9_export.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Update the contract doc + log**

In `export-contract.md`, extend the manifest-schema block with the new keys (`book_id`, `title`, `author`, `edition`, `cover`, `capabilities`) and note they are sourced from `data/books/<book_id>/book-meta.json`. Append a `knowledge/log.md` line.

- [ ] **Step 6: Commit**

```bash
git add data/books/dzl/book-meta.json pipeline/config.py pipeline/stage9_export.py pipeline/cli.py tests/unit/test_stage9_export.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): manifest book identity + capabilities from book-meta.json"
```

---

## Task 4: Build-time pinyin columns

Add a toneless, lowercased pinyin rendering for each person canonical name and each variant, so the app's in-memory search can match romanized input.

**Files:**

- Modify: `pyproject.toml:6-13` (add `pypinyin`)
- Modify: `pipeline/export_enrich.py` (add `add_pinyin_columns` + pure `to_pinyin`)
- Modify: `tests/unit/test_export_enrich.py`
- Modify: `pipeline/stage9_export.py` (call the pass)
- Modify: `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` dependencies array, add `"pypinyin>=0.51"`. Then run: `uv sync` (Expected: resolves and installs pypinyin).

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/test_export_enrich.py`:

```python
from pipeline.export_enrich import to_pinyin, add_pinyin_columns


def test_to_pinyin_toneless_joined_lowercase() -> None:
    assert to_pinyin("管仲") == "guanzhong"
    assert to_pinyin("赵盾") == "zhaodun"
    assert to_pinyin("") == ""


def test_add_pinyin_columns_populates_persons_and_variants(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE persons (id TEXT PRIMARY KEY, canonical_name TEXT);")
        c.execute(
            "CREATE TABLE person_variants (id INTEGER PRIMARY KEY, "
            "person_id TEXT, variant TEXT, kind TEXT);"
        )
        c.execute("INSERT INTO persons VALUES ('per:gz', '管仲');")
        c.execute(
            "INSERT INTO person_variants (person_id, variant, kind) "
            "VALUES ('per:gz', '夷吾', '本名');"
        )
    add_pinyin_columns(graph)
    with sqlite3.connect(graph) as c:
        p = c.execute("SELECT pinyin FROM persons WHERE id='per:gz';").fetchone()[0]
        v = c.execute(
            "SELECT pinyin FROM person_variants WHERE variant='夷吾';"
        ).fetchone()[0]
    assert p == "guanzhong"
    assert v == "yiwu"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_export_enrich.py -k pinyin -v`
Expected: FAIL — `ImportError: cannot import name 'to_pinyin'`.

- [ ] **Step 4: Implement**

Add to `pipeline/export_enrich.py`:

```python
from pypinyin import Style, lazy_pinyin


def to_pinyin(text: str) -> str:
    """Toneless, joined, lowercased pinyin. Non-Han chars pass through.

    NOTE: polyphonic name characters (e.g. 重 in 重耳) may romanize to their
    most-common reading rather than the name reading; pinyin-quality tuning is
    tracked as an open question in the reader spec, not solved here.
    """
    if not text:
        return ""
    return "".join(lazy_pinyin(text, style=Style.NORMAL)).lower()


def add_pinyin_columns(graph_db: Path) -> None:
    """Add and populate a `pinyin` column on persons.canonical_name and
    person_variants.variant."""
    with sqlite3.connect(graph_db) as g:
        for table, name_col in (("persons", "canonical_name"),
                                ("person_variants", "variant")):
            cols = [r[1] for r in g.execute(f"PRAGMA table_info({table});")]
            if "pinyin" not in cols:
                g.execute(f"ALTER TABLE {table} ADD COLUMN pinyin TEXT;")
            rows = g.execute(f"SELECT rowid, {name_col} FROM {table};").fetchall()
            g.executemany(
                f"UPDATE {table} SET pinyin = ? WHERE rowid = ?;",
                [(to_pinyin(n or ""), rid) for rid, n in rows],
            )
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/test_export_enrich.py -k pinyin -v`
Expected: PASS.

(If `to_pinyin("管仲")` returns something other than `"guanzhong"` on the installed pypinyin version, correct the test's expected value to the library's actual output — the library is the source of truth — and note the polyphone caveat. `管仲`/`赵盾`/`夷吾` were chosen as non-polyphonic to avoid this.)

- [ ] **Step 6: Wire into `export_bundle`**

In `pipeline/stage9_export.py`: import `add_pinyin_columns`, and call `add_pinyin_columns(snap_path)` after `build_citations_table(...)`.

- [ ] **Step 7: Run the full export suite**

Run: `uv run pytest tests/unit/test_stage9_export.py tests/unit/test_export_enrich.py -v`
Expected: PASS.

- [ ] **Step 8: Update the contract doc + log**

In `export-contract.md`: note `persons.pinyin` and `person_variants.pinyin` (toneless joined lowercase, built with `pypinyin`) are added in v2 for client-side search. Append a `knowledge/log.md` line.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml pipeline/export_enrich.py pipeline/stage9_export.py tests/unit/test_export_enrich.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): build-time pinyin columns on persons + variants"
```

---

## Task 5: Build-time deed importance

Compute a per-participation importance score (blending a global component with a within-person salience component) and store it in a `deed_importance(event_id, person_id, score)` table so the client ranks deeds cheaply.

**Files:**

- Modify: `pipeline/export_enrich.py` (pure `deed_importance` + DB pass `build_deed_importance`)
- Modify: `tests/unit/test_export_enrich.py`
- Modify: `pipeline/stage9_export.py` (call the pass)
- Modify: `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing test for the pure function**

Add to `tests/unit/test_export_enrich.py`:

```python
from pipeline.export_enrich import deed_importance


def test_deed_importance_high_weight_beats_low_for_same_person() -> None:
    # dense person: a battle outranks a sickbed visit
    battle = deed_importance(event_type="战", participants=6, citations=2,
                             person_type_fraction=0.1)
    visit = deed_importance(event_type="探病", participants=2, citations=1,
                            person_type_fraction=0.1)
    assert battle > visit


def test_deed_importance_rarity_boosts_sole_defining_act() -> None:
    # same low-weight event type; the person for whom it is their ONLY deed of
    # that type (fraction=1.0 -> rare relative to a rich record) is boosted vs.
    # a person for whom that type is common (fraction=0.5).
    sole = deed_importance(event_type="谏", participants=2, citations=1,
                           person_type_fraction=1.0 / 8)
    common = deed_importance(event_type="谏", participants=2, citations=1,
                             person_type_fraction=4.0 / 8)
    assert sole > common
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_export_enrich.py -k deed_importance -v`
Expected: FAIL — `cannot import name 'deed_importance'`.

- [ ] **Step 3: Implement the pure function**

Add to `pipeline/export_enrich.py`:

```python
import math

# Curated high-salience event types; everything else gets DEFAULT_WEIGHT.
# Tunable — see reader spec open questions. Matched against events.type exactly.
TYPE_WEIGHTS: dict[str, float] = {
    "战": 3.0, "会盟": 3.0, "盟": 2.5, "弑": 3.0, "灭": 3.0,
    "即位": 2.5, "立": 2.0, "出奔": 2.5, "奔": 2.5,
    "伐": 2.0, "围": 2.0, "薨": 2.0, "卒": 2.0, "处死": 2.0, "杀": 2.0,
}
DEFAULT_WEIGHT = 1.0
SALIENCE_WEIGHT = 1.5  # how strongly within-person rarity boosts a deed


def deed_importance(*, event_type: str, participants: int, citations: int,
                    person_type_fraction: float) -> float:
    """Blended importance of one participation.

    global component: type weight scaled by how many people were involved and
    how often it is attested. within-person salience: deeds whose type is rare
    in *this person's* record (small fraction) are boosted, so a minor figure's
    single defining act is not buried by global weighting.
    """
    weight = TYPE_WEIGHTS.get(event_type, DEFAULT_WEIGHT)
    global_component = weight * (1 + math.log1p(participants)) * (1 + math.log1p(citations))
    rarity = 1.0 / person_type_fraction if person_type_fraction > 0 else 1.0
    salience = 1 + SALIENCE_WEIGHT * math.log1p(rarity - 1)
    return global_component * salience
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_export_enrich.py -k deed_importance -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for the DB pass**

Add to `tests/unit/test_export_enrich.py`:

```python
from pipeline.export_enrich import build_deed_importance


def test_build_deed_importance_writes_a_row_per_participation(tmp_path: Path) -> None:
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as c:
        c.execute("CREATE TABLE events (id TEXT PRIMARY KEY, type TEXT);")
        c.execute(
            "CREATE TABLE event_participants (event_id TEXT, person_id TEXT, "
            "role TEXT, role_detail TEXT, citation_id TEXT, confidence REAL, "
            "provenance TEXT);"
        )
        c.execute("CREATE TABLE entity_citations (entity_kind TEXT, entity_id TEXT, citation_id TEXT);")
        c.execute("INSERT INTO events VALUES ('evt:war', '战'), ('evt:visit', '探病');")
        c.executemany(
            "INSERT INTO event_participants (event_id, person_id, role, confidence, provenance)"
            " VALUES (?,?,?,1.0,'auto');",
            [("evt:war", "per:a", "主将"), ("evt:visit", "per:a", "主行")],
        )
    build_deed_importance(graph)
    with sqlite3.connect(graph) as c:
        scores = dict(c.execute(
            "SELECT event_id, score FROM deed_importance WHERE person_id='per:a';"
        ))
    assert set(scores) == {"evt:war", "evt:visit"}
    assert scores["evt:war"] > scores["evt:visit"]
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_export_enrich.py -k build_deed_importance -v`
Expected: FAIL — `cannot import name 'build_deed_importance'`.

- [ ] **Step 7: Implement the DB pass**

Add to `pipeline/export_enrich.py`:

```python
def build_deed_importance(graph_db: Path) -> None:
    """Create `deed_importance(event_id, person_id, score)` over every
    participation, using deed_importance()."""
    with sqlite3.connect(graph_db) as g:
        parts = g.execute(
            "SELECT ep.event_id, ep.person_id, e.type "
            "FROM event_participants ep JOIN events e ON e.id = ep.event_id;"
        ).fetchall()
        # participant count per event
        pcount: dict[str, int] = {}
        for eid, _pid, _t in parts:
            pcount[eid] = pcount.get(eid, 0) + 1
        # citation count per event (via entity_citations on the event)
        ccount = dict(g.execute(
            "SELECT entity_id, COUNT(*) FROM entity_citations "
            "WHERE entity_kind='event' GROUP BY entity_id;"
        ))
        # per-person deed total and per-(person,type) counts
        ptype: dict[tuple[str, str], int] = {}
        ptotal: dict[str, int] = {}
        for _eid, pid, t in parts:
            ptotal[pid] = ptotal.get(pid, 0) + 1
            ptype[(pid, t)] = ptype.get((pid, t), 0) + 1

        g.execute("DROP TABLE IF EXISTS deed_importance;")
        g.execute(
            "CREATE TABLE deed_importance ("
            " event_id TEXT, person_id TEXT, score REAL,"
            " PRIMARY KEY (event_id, person_id));"
        )
        rows = []
        for eid, pid, t in parts:
            frac = ptype[(pid, t)] / ptotal[pid]
            score = deed_importance(
                event_type=t,
                participants=pcount.get(eid, 1),
                citations=ccount.get(eid, 0),
                person_type_fraction=frac,
            )
            rows.append((eid, pid, score))
        g.executemany("INSERT OR REPLACE INTO deed_importance VALUES (?,?,?);", rows)
```

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/unit/test_export_enrich.py -k "deed_importance or build_deed" -v`
Expected: PASS.

- [ ] **Step 9: Wire into `export_bundle`**

In `pipeline/stage9_export.py`: import `build_deed_importance`; call `build_deed_importance(snap_path)` after `add_pinyin_columns(...)`.

- [ ] **Step 10: Run the full export suite**

Run: `uv run pytest tests/unit/test_stage9_export.py tests/unit/test_export_enrich.py -v`
Expected: PASS.

- [ ] **Step 11: Update the contract doc + log**

In `export-contract.md`: document the `deed_importance(event_id, person_id, score)` table and that the weighting constants live in `pipeline/export_enrich.py` and are tunable. Append a `knowledge/log.md` line.

- [ ] **Step 12: Commit**

```bash
git add pipeline/export_enrich.py pipeline/stage9_export.py tests/unit/test_export_enrich.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): build-time deed_importance (global x within-person salience)"
```

---

## Task 6: Emit the `texts/` payload

Copy the readable chapter prose into a `texts/` directory in the bundle, so the phase-2 Reader has its payload while v1's web bundle ships only `graph.sqlite`.

**Files:**

- Modify: `pipeline/config.py` (add `readable_dir`)
- Modify: `pipeline/stage9_export.py` (copy readable md into `out_dir/texts/`)
- Modify: `tests/unit/test_stage9_export.py`
- Modify: `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_stage9_export.py`:

```python
def test_export_copies_readable_texts(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    corpus = tmp_path / "corpus.sqlite"
    readable = tmp_path / "readable"
    readable.mkdir()
    (readable / "ch01.md").write_text("第一回 正文", encoding="utf-8")
    (readable / "ch02.md").write_text("第二回 正文", encoding="utf-8")
    out = tmp_path / "exports" / "t"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    with connect(corpus) as cc:
        cc.execute(
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, "
            "paragraph_start INTEGER, paragraph_end INTEGER, text TEXT, hash TEXT);"
        )
    meta = {"book_id": "dzl", "title": "东周列国志",
            "capabilities": ["cast", "timeline", "states"]}
    export_bundle(src, out, version="t", corpus_db=corpus, book_meta=meta,
                  readable_dir=readable)
    assert (out / "texts" / "ch01.md").read_text(encoding="utf-8") == "第一回 正文"
    assert (out / "texts" / "ch02.md").is_file()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_stage9_export.py::test_export_copies_readable_texts -v`
Expected: FAIL — `unexpected keyword argument 'readable_dir'`.

- [ ] **Step 3: Implement**

In `pipeline/config.py`, add:

```python
    @property
    def readable_dir(self) -> Path:
        return self.data_dir / "readable"
```

In `pipeline/stage9_export.py`, extend the signature with `readable_dir: Path` and, after the manifest write, copy the texts:

```python
    texts_out = out_dir / "texts"
    texts_out.mkdir(parents=True, exist_ok=True)
    if readable_dir.is_dir():
        for md in sorted(readable_dir.glob("ch*.md")):
            shutil.copyfile(md, texts_out / md.name)
```

In `pipeline/cli.py`, pass `readable_dir=cfg.readable_dir` in the `export_bundle(...)` call. Update the other existing tests' `export_bundle(...)` calls to pass `readable_dir=tmp_path / "readable"` (create the dir, may be empty — the `is_dir()` guard handles empties).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_stage9_export.py -v`
Expected: PASS.

- [ ] **Step 5: Update the contract doc + log**

In `export-contract.md`: document the bundle now contains `texts/chNN.md` (full reading prose, phase-2 payload; **not** consumed by the v1 web target which bundles only `graph.sqlite`). Append a `knowledge/log.md` line.

- [ ] **Step 6: Commit**

```bash
git add pipeline/config.py pipeline/stage9_export.py pipeline/cli.py tests/unit/test_stage9_export.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): emit texts/ payload from readable chapters"
```

---

## Task 7: Integration — produce and sanity-check the real Ch.1–50 bundle

Run the whole suite, build the actual bundle from the live data, and eyeball it. No new code unless a defect surfaces.

**Files:** none (verification only), unless a fix is needed.

- [ ] **Step 1: Full test suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions across the repo).

- [ ] **Step 2: Build the real bundle**

Run: `uv run changjuan export 2026-05-v1`
Expected: prints `export bundle written to .../data/exports/changjuan-export-2026-05-v1`.

- [ ] **Step 3: Sanity-check the artifacts**

Run:

```bash
uv run python -c "
import json, sqlite3, pathlib
b = pathlib.Path('data/exports/changjuan-export-2026-05-v1')
m = json.loads((b/'manifest.json').read_text())
print('manifest keys:', sorted(m))
print('title/caps:', m['title'], m['capabilities'], 'schema_version', m['schema_version'])
g = sqlite3.connect(b/'graph.sqlite')
print('citations rows:', g.execute('SELECT COUNT(*) FROM citations').fetchone()[0])
print('persons with pinyin:', g.execute(\"SELECT COUNT(*) FROM persons WHERE pinyin IS NOT NULL AND pinyin<>''\").fetchone()[0])
print('deed_importance rows:', g.execute('SELECT COUNT(*) FROM deed_importance').fetchone()[0])
print('sample top deeds for 晋文公:')
for r in g.execute('''SELECT e.type, d.score FROM deed_importance d
  JOIN events e ON e.id=d.event_id WHERE d.person_id='per:晋文公'
  ORDER BY d.score DESC LIMIT 5'''):
    print('  ', r)
print('texts files:', len(list((b/'texts').glob('ch*.md'))))
"
```

Expected: manifest carries identity + capabilities + `schema_version` 2; `citations` non-empty; most persons have pinyin; `deed_importance` ≈ number of `event_participants`; 晋文公's top deeds are battles/covenants (战/会盟), not 探病; `texts/` has the readable chapters.

- [ ] **Step 4: Confirm the drift hook is satisfied across the plan**

Run: `git log --oneline -7` and confirm each export commit also touched `export-contract.md`. (If `scripts/drift-check` exists, run `uv run scripts/drift-check` or `./scripts/drift-check`.)

- [ ] **Step 5: (Only if Step 3 surfaced a defect)** fix, add a regression test in `tests/unit/test_export_enrich.py`, re-run `uv run pytest -q`, and commit.

---

## Self-Review (completed by plan author)

**Spec coverage** — the five §8 export prerequisites map to Tasks 2 (citation denormalization), 6 (graph/text split — graph rename Task 1 + texts Task 6), 3 (manifest identity + capabilities), 4 (pinyin), 5 (deed-importance). Bundle-layout/schema bump = Task 1. Integration against real data = Task 7. The reader-app itself is a **separate plan** (out of scope here, by the brainstorming scope split).

**Placeholders** — none; every code step shows complete code and every run step gives an exact command + expected output.

**Type/name consistency** — `export_bundle(src_db, out_dir, *, version, corpus_db, book_meta, readable_dir)` is introduced incrementally (Tasks 2/3/6) and every test/CLI call site is updated in the same task that adds each parameter. Enrichment functions (`build_citations_table`, `to_pinyin`, `add_pinyin_columns`, `deed_importance`, `build_deed_importance`) keep identical signatures between their defining task and their `stage9_export.py` call site.

**Known caveat carried forward** — pinyin polyphone handling (重耳→reading) is deliberately not solved; it is logged in the function docstring and the reader spec's open questions.
