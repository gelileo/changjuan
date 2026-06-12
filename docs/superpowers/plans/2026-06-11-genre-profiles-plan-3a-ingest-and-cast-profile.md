# Genre Profiles — Plan 3a: Ingest Generalization + Cast Profile

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Generalize stage-1 ingest from the hardwired dzl path to a book-meta-driven book-registry, declare the `cast` genre profile, and ingest+chunk the staged 红楼梦 (`hlm`) corpus — without changing dzl's behavior.

**Architecture:** Ingest reads its source from `book-meta.json` fields (`corpus`, `corpus_dir`, `corpus_json`), stamps `documents.corpus` + `<book_id>:<n>` ids. The `documents.corpus` enum `CHECK` is dropped (corpus is a free label, validated by book-meta — consistent with the relation-kind CHECK removal in Plan 1). The `cast` profile is a new `PROFILES` entry (capabilities `[persons,relations,events,groups,themes]`, `default_group_type="clan"`, domestic relation vocab). No extraction yet — that's Plan 3c.

**Tech Stack:** Python 3, SQLite, Typer CLI, pytest. Spec: `docs/superpowers/specs/2026-06-10-capability-genre-profiles-design.md`. Corpus staged per `knowledge/concepts/corpora/honglou.md` (`corpus_dir = hlm`, `corpus_json = 红楼梦.json`, 120 chapters).

**Branch:** `feat/hlm-cast` (already created; the corpus staging is committed there at `2b97d10`).

---

## File Structure
- **Modify** `pipeline/profile.py` — add the `cast` entry to `PROFILES`.
- **Modify** `pipeline/schemas/corpus_schema.sql` — drop the `documents.corpus` enum CHECK.
- **Modify** `pipeline/stage1_ingest.py` — replace `ingest_dongzhoulieguozhi(conn, cfg)` with `ingest_book(conn, cfg, book_meta)`.
- **Modify** `pipeline/cli.py` — `ingest` + `chunk` commands take `--book-id`; `ingest` reads book-meta and calls `ingest_book`; update the import.
- **Modify** `data/books/dzl/book-meta.json` — add `corpus`/`corpus_dir`/`corpus_json`.
- **Create** `data/books/hlm/book-meta.json`.
- **Tests:** `tests/test_profile.py` (extend), `tests/test_corpus_schema.py` (create), `tests/test_ingest_book.py` (create), `tests/integration/test_hlm_ingest.py` (create).
- **Knowledge:** update `concepts/pipeline/architecture.md` (ingest is book-driven), `concepts/pipeline/profiles.md` (cast profile), `concepts/corpora/honglou.md` (now ingestable), `concepts/runtime/cli.md` (ingest/chunk `--book-id`); `knowledge/log.md`.

---

## Task 1: Add the `cast` profile

**Files:** Modify `pipeline/profile.py`; Test `tests/test_profile.py`.

- [ ] **Step 1: Write the failing test (append to `tests/test_profile.py`)**

```python
from pipeline.profile import default_group_type


def test_cast_profile_capabilities():
    assert PROFILES["cast"]["capabilities"] == [
        "persons", "relations", "events", "groups", "themes",
    ]


def test_cast_default_group_type_is_clan():
    assert default_group_type("cast") == "clan"


def test_cast_person_relation_vocab_is_domestic():
    kinds = relation_kinds_for("cast", "person")
    assert {"spouse", "master", "servant", "romantic", "concubine"} <= kinds
    assert "ruler" not in kinds and "killed_by" not in kinds


def test_cast_derives_reader_caps_without_timeline():
    # cast has no chronology -> no timeline tab
    assert derive_reader_capabilities(list(PROFILES["cast"]["capabilities"])) == [
        "cast", "groups", "themes",
    ]
```

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_profile.py -v` (KeyError: 'cast').

- [ ] **Step 3: Add the cast entry in `pipeline/profile.py`** — after `_HISTORY_EVENT_KINDS`:

```python
_CAST_PERSON_KINDS = {
    "parent", "child", "spouse", "sibling", "grandparent", "grandchild",
    "uncle_aunt", "cousin", "in_law", "concubine", "master", "servant",
    "mentor", "friend", "romantic", "adopted", "clan_member",
}
_CAST_EVENT_KINDS = {"causes", "precedes", "related"}
```

and add to `PROFILES` (replacing the `# "cast" profile lands in Plan 3` comment):

```python
    "cast": {
        "capabilities": ["persons", "relations", "events", "groups", "themes"],
        "person_relation_kinds": _CAST_PERSON_KINDS,
        "event_relation_kinds": _CAST_EVENT_KINDS,
        "default_group_type": "clan",
    },
```

- [ ] **Step 4: Run, verify PASS** — `uv run pytest tests/test_profile.py -v`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/profile.py tests/test_profile.py
git commit -m "feat(profile): add cast genre profile (domestic relation vocab, group_type=clan)"
```

---

## Task 2: Drop the `documents.corpus` enum CHECK

**Files:** Modify `pipeline/schemas/corpus_schema.sql`; Test `tests/test_corpus_schema.py`.

- [ ] **Step 1: Write the failing test `tests/test_corpus_schema.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA = Path("pipeline/schemas/corpus_schema.sql").read_text(encoding="utf-8")


def test_corpus_label_is_free_no_enum_check():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    # A corpus label outside the old enum must now insert fine.
    c.execute(
        "INSERT INTO documents (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition) "
        "VALUES ('hlm:1','honglou','红楼梦',1,'第一回','...','hlm/json')"
    )
    assert c.execute("SELECT corpus FROM documents WHERE id='hlm:1'").fetchone()[0] == "honglou"
```

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_corpus_schema.py -v` (IntegrityError: CHECK constraint failed).

- [ ] **Step 3: Edit `pipeline/schemas/corpus_schema.sql`** — change the `documents.corpus` column line from:
`corpus          TEXT NOT NULL CHECK (corpus IN ('dongzhoulieguozhi', 'zuozhuan', 'shiji')),`
to:
`corpus          TEXT NOT NULL,`
Leave the `UNIQUE (corpus, chapter_num)` constraint and all other columns intact.

- [ ] **Step 4: Run, verify PASS** — `uv run pytest tests/test_corpus_schema.py -v`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/schemas/corpus_schema.sql tests/test_corpus_schema.py
git commit -m "refactor(schema): drop documents.corpus enum CHECK (corpus is a free label)"
```

---

## Task 3: Generalize `ingest_dongzhoulieguozhi` → `ingest_book`

**Files:** Modify `pipeline/stage1_ingest.py`; Test `tests/test_ingest_book.py`.

- [ ] **Step 1: Write the failing test `tests/test_ingest_book.py`**

```python
import json
import sqlite3
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema
from pipeline.stage1_ingest import ingest_book

SCHEMA = Path("pipeline/schemas/corpus_schema.sql").read_text(encoding="utf-8")


def _make_corpus(corpora_dir: Path, corpus_dir: str, fname: str) -> None:
    d = corpora_dir / corpus_dir / "json"
    d.mkdir(parents=True)
    (d / fname).write_text(
        json.dumps(
            {"title": "T", "chapters": [
                {"title": "C1", "content": "p1"},
                {"title": "C2", "content": "p2"},
            ]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_ingest_book_uses_book_meta_source_and_book_id_prefix(tmp_path):
    # Lay out a fake repo: corpora/myc/json/x.json, run as book_id 'bk'
    (tmp_path / "data" / "books" / "bk").mkdir(parents=True)
    _make_corpus(tmp_path / "corpora", "myc", "x.json")
    cfg = Config(repo_root=tmp_path, book_id="bk")
    meta = {"book_id": "bk", "title": "MyBook",
            "corpus": "mycorpus", "corpus_dir": "myc", "corpus_json": "x.json"}
    conn = sqlite3.connect(cfg.corpus_db)
    apply_schema(conn, SCHEMA)
    n = ingest_book(conn, cfg, meta)
    assert n == 2
    rows = conn.execute("SELECT id, corpus, title, chapter_num, chapter_title FROM documents ORDER BY chapter_num").fetchall()
    assert rows[0] == ("bk:1", "mycorpus", "MyBook", 1, "C1")
    assert rows[1][0] == "bk:2"


def test_ingest_book_is_idempotent(tmp_path):
    (tmp_path / "data" / "books" / "bk").mkdir(parents=True)
    _make_corpus(tmp_path / "corpora", "myc", "x.json")
    cfg = Config(repo_root=tmp_path, book_id="bk")
    meta = {"book_id": "bk", "corpus": "mycorpus", "corpus_dir": "myc", "corpus_json": "x.json"}
    conn = sqlite3.connect(cfg.corpus_db)
    apply_schema(conn, SCHEMA)
    ingest_book(conn, cfg, meta)
    assert ingest_book(conn, cfg, meta) == 0  # re-ingest no-op
```

> `Config.corpus_db` resolves to `tmp_path/data/books/bk/corpus.sqlite`; the `data/books/bk` dir is created above so the connect succeeds.

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_ingest_book.py -v` (ImportError: ingest_book).

- [ ] **Step 3: Replace the function in `pipeline/stage1_ingest.py`** — replace `ingest_dongzhoulieguozhi` with:

```python
def ingest_book(conn: sqlite3.Connection, cfg: Config, book_meta: Mapping[str, object]) -> int:
    """Ingest a book's chaptered JSON into corpus.sqlite. Returns the number of inserts.

    Source + labels come from book_meta: `corpus_dir`/`corpus_json` locate the JSON
    under corpora/, `corpus` is the stamped documents.corpus label. Document ids are
    `<book_id>:<chapter_num>`. Idempotent (ON CONFLICT DO NOTHING on (corpus, chapter_num)).
    """
    corpus = str(book_meta["corpus"])
    src = cfg.corpora_dir / str(book_meta["corpus_dir"]) / "json" / str(book_meta["corpus_json"])
    data = json.loads(src.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    title = str(book_meta.get("title") or data.get("title") or corpus)
    rows = [
        {
            "id": f"{cfg.book_id}:{i + 1}",
            "corpus": corpus,
            "title": title,
            "chapter_num": i + 1,
            "chapter_title": ch["title"],
            "raw_text": ch["content"],
            "source_edition": f"{book_meta['corpus_dir']}/json",
        }
        for i, ch in enumerate(chapters)
    ]
    inserted = 0
    cur = conn.cursor()
    for row in rows:
        cur.execute(
            """
            INSERT INTO documents
                (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition)
            VALUES
                (:id, :corpus, :title, :chapter_num, :chapter_title, :raw_text, :source_edition)
            ON CONFLICT (corpus, chapter_num) DO NOTHING;
            """,
            row,
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted
```

Add `from collections.abc import Mapping` to the imports (alongside the existing `from pipeline.config import Config`). Remove the old `ingest_dongzhoulieguozhi` function entirely.

- [ ] **Step 4: Run, verify PASS** — `uv run pytest tests/test_ingest_book.py -v`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/stage1_ingest.py tests/test_ingest_book.py
git commit -m "feat(ingest): generalize to ingest_book(conn, cfg, book_meta) (book-registry)"
```

---

## Task 4: CLI `ingest` + `chunk` take `--book-id`

**Files:** Modify `pipeline/cli.py`.

- [ ] **Step 1: Edit `pipeline/cli.py`**
- Change the import `from pipeline.stage1_ingest import ingest_dongzhoulieguozhi` → `from pipeline.stage1_ingest import ingest_book`.
- Replace the `ingest` command body:

```python
@app.command()
def ingest(
    book_id: str = typer.Option("dzl", help="Book id under data/books/."),
    repo_root: Path | None = typer.Option(None, help="Override the repo root."),
) -> None:
    """Stage 1: read a book's source corpus into corpus.sqlite."""
    cfg = _cfg(repo_root, book_id)
    meta_path = cfg.books_dir / book_id / "book-meta.json"
    if not meta_path.exists():
        typer.echo(f"book-meta.json not found for book '{book_id}': {meta_path}", err=True)
        raise typer.Exit(code=1)
    meta = _json.loads(meta_path.read_text("utf-8"))
    src = cfg.corpora_dir / meta["corpus_dir"] / "json" / meta["corpus_json"]
    if not src.exists():
        typer.echo(f"corpus source not found: {src}", err=True)
        raise typer.Exit(code=1)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = ingest_book(conn, cfg, meta)
    typer.echo(f"ingested {n} chapters into {cfg.corpus_db}")
```

- Add `--book-id` to `chunk`:

```python
@app.command()
def chunk(
    book_id: str = typer.Option("dzl", help="Book id under data/books/."),
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 2: split documents into overlapping paragraph-aware chunks."""
    cfg = _cfg(repo_root, book_id)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = chunk_documents(conn, cfg)
    typer.echo(f"wrote {n} chunks into {cfg.corpus_db}")
```

- [ ] **Step 2: Verify CLI imports** — `uv run python -c "from pipeline.cli import app; print('ok')"` → `ok`.

- [ ] **Step 3: Commit**

```bash
git add pipeline/cli.py
git commit -m "feat(cli): ingest/chunk take --book-id; ingest reads corpus source from book-meta"
```

---

## Task 5: book-meta corpus fields (dzl + hlm) + dzl regression

**Files:** Modify `data/books/dzl/book-meta.json`; Create `data/books/hlm/book-meta.json`; Test `tests/integration/test_hlm_ingest.py` (dzl-regression part here, hlm part in Task 6).

- [ ] **Step 1: Add corpus fields to `data/books/dzl/book-meta.json`** (keep all existing fields; add):
```json
"corpus": "dongzhoulieguozhi",
"corpus_dir": "dongzhoulieguozhi",
"corpus_json": "东周列国志.json"
```

- [ ] **Step 2: Create `data/books/hlm/book-meta.json`**
```json
{
  "book_id": "hlm",
  "slug": "hongloumeng",
  "title": "红楼梦",
  "author": "曹雪芹 高鹗",
  "profile": "cast",
  "capabilities": ["persons", "relations", "events", "groups", "themes"],
  "corpus": "honglou",
  "corpus_dir": "hlm",
  "corpus_json": "红楼梦.json"
}
```

- [ ] **Step 3: Write the dzl-regression test `tests/integration/test_hlm_ingest.py`**
```python
import json
import sqlite3
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.integration
def test_dzl_ingest_unchanged():
    """dzl ingest still produces dzl:<n> ids + corpus 'dongzhoulieguozhi' from its book-meta."""
    meta = json.loads((ROOT / "data/books/dzl/book-meta.json").read_text("utf-8"))
    assert meta["corpus"] == "dongzhoulieguozhi"
    src = ROOT / "corpora" / meta["corpus_dir"] / "json" / meta["corpus_json"]
    if not src.exists():
        pytest.skip("dzl corpus source not present")
    from pipeline.config import Config
    from pipeline.db import apply_schema
    from pipeline.stage1_ingest import ingest_book
    SCHEMA = (ROOT / "pipeline/schemas/corpus_schema.sql").read_text("utf-8")
    conn = sqlite3.connect(":memory:")
    apply_schema(conn, SCHEMA)
    cfg = Config(repo_root=ROOT, book_id="dzl")
    n = ingest_book(conn, cfg, meta)
    assert n == 108
    first = conn.execute("SELECT id, corpus FROM documents ORDER BY chapter_num LIMIT 1").fetchone()
    assert first == ("dzl:1", "dongzhoulieguozhi")
```

- [ ] **Step 4: Run** — `uv run pytest tests/integration/test_hlm_ingest.py::test_dzl_ingest_unchanged -v -m integration`. Expected PASS (or SKIP if corpus absent).

- [ ] **Step 5: Commit**

```bash
git add data/books/dzl/book-meta.json data/books/hlm/book-meta.json tests/integration/test_hlm_ingest.py
git commit -m "feat(books): corpus source fields in dzl+hlm book-meta; dzl ingest regression test"
```

---

## Task 6: Ingest + chunk hlm (the deliverable) + knowledge

**Files:** Test `tests/integration/test_hlm_ingest.py` (extend); knowledge articles.

- [ ] **Step 1: Add the hlm ingest integration test (append to `tests/integration/test_hlm_ingest.py`)**
```python
@pytest.mark.integration
def test_hlm_ingest_120_chapters():
    meta = json.loads((ROOT / "data/books/hlm/book-meta.json").read_text("utf-8"))
    src = ROOT / "corpora" / meta["corpus_dir"] / "json" / meta["corpus_json"]
    if not src.exists():
        pytest.skip("hlm corpus source not present (corpora/hlm staged?)")
    from pipeline.config import Config
    from pipeline.db import apply_schema
    from pipeline.stage1_ingest import ingest_book
    SCHEMA = (ROOT / "pipeline/schemas/corpus_schema.sql").read_text("utf-8")
    conn = sqlite3.connect(":memory:")
    apply_schema(conn, SCHEMA)
    cfg = Config(repo_root=ROOT, book_id="hlm")
    n = ingest_book(conn, cfg, meta)
    assert n == 120
    row = conn.execute("SELECT id, corpus, chapter_title FROM documents ORDER BY chapter_num LIMIT 1").fetchone()
    assert row[0] == "hlm:1" and row[1] == "honglou" and "第一回" in row[2]
```

- [ ] **Step 2: Run it** — `uv run pytest tests/integration/test_hlm_ingest.py -v -m integration` (both pass).

- [ ] **Step 3: Produce the real hlm corpus.sqlite (manual, the deliverable)**
```bash
uv run changjuan ingest --book-id hlm
uv run changjuan chunk --book-id hlm
sqlite3 data/books/hlm/corpus.sqlite "SELECT COUNT(*) FROM documents; SELECT COUNT(*) FROM chunks;"
```
Expected: 120 documents; chunks > 120. (`data/books/hlm/` is gitignored working state.)

- [ ] **Step 4: Run the full suite** — `uv run pytest -q` (green; integration deselected by default).

- [ ] **Step 5: Knowledge updates (same-task rule)**
- `concepts/pipeline/architecture.md` — stage-1 ingest is now book-meta-driven (`ingest_book`, `--book-id`), not dzl-hardwired; `documents.corpus` is a free label.
- `concepts/pipeline/profiles.md` — add the `cast` profile (capabilities, `default_group_type=clan`, domestic relation vocab).
- `concepts/corpora/honglou.md` — change status to "ingestable; `changjuan ingest --book-id hlm` reads `corpus_dir`/`corpus_json` from book-meta."
- `concepts/runtime/cli.md` — `ingest`/`chunk` take `--book-id`.
- Append `knowledge/log.md`.

- [ ] **Step 6: Commit**

```bash
git add knowledge/
git commit -m "docs(knowledge): book-driven ingest + cast profile + hlm ingestable"
```

---

## Self-Review
1. **Spec coverage:** ingest generalization (Tasks 3–4) ✓; cast profile (Task 1) ✓; hlm ingestable (Tasks 5–6) ✓. Themes capability + cast prompt-pack + extraction slice are **Plan 3b/3c** (out of scope here, by design).
2. **Placeholders:** none — every code step shows code; tests/commands explicit.
3. **Symbol consistency:** `ingest_book(conn, cfg, book_meta)`, book-meta keys `corpus`/`corpus_dir`/`corpus_json`, id prefix `<book_id>:`, profile `cast` with `default_group_type="clan"` — used identically across tasks.
