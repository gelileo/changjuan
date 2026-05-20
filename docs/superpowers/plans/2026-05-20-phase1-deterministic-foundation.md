# changjuan Phase 1 — Deterministic Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the corpus ingest, canonical schema, deterministic stages (1, 2, 4, 7, 9), and end-to-end round-trip — so the whole tooling pipeline wires together with zero LLM cost, ready for stage 3 (extraction) in Phase 2.

**Architecture:** Sequential ETL with stage-local checkpointed outputs. Phase 1 builds the four deterministic stages (ingest, chunk, normalize, load, export) plus the canonical SQLite schema. No LLM stages yet; stage 3 / 5 / 6 land in subsequent phase plans. Living-docs same-task rule applies: every code change that alters behaviour or structure updates the matching `knowledge/concepts/*.md` article and appends to `knowledge/log.md` in the same commit.

**Tech Stack:** Python 3.12+, `uv` for env/dep management, SQLite (stdlib), pytest, typer (CLI), structlog (logging), ruff (lint), mypy (type-check), pre-commit. No LLM SDK in Phase 1.

---

## Definition of done (Phase 1)

- `corpus.sqlite` populated from 《东周列国志》 (108 chapters, paragraph-indexed, hashed chunks).
- `changjuan.sqlite` schema in place: all entity / relation / candidate / bookkeeping tables + `field_history` view, foreign keys enforced.
- Reign table (鲁公 + 周王) bundled as JSON; date parser handles all six `inference_kind` values.
- Stage 7 load demonstrates field-level merge semantics on synthetic candidate data: citation accumulation, variant union, scalar update, Conflict emission on disagreement, `curated`-never-overwritten rule.
- Stage 9 export produces a `manifest.json` + read-only SQLite snapshot with `candidate_*` tables prefix-excluded; a round-trip test loads the snapshot and verifies counts.
- CLI verbs: `changjuan ingest`, `changjuan chunk`, `changjuan load`, `changjuan export`, all driven by typer.
- `pre-commit install` complete; ruff + mypy + drift-check + validate-articles run on every commit.
- Knowledge articles `data-model/knowledge-graph.md` and `pipeline/architecture.md` carry `affects:` globs pointing at the files this phase produces.

## File structure (what Phase 1 creates or modifies)

```text
changjuan/
├── pyproject.toml                          # NEW (Task 1)
├── uv.lock                                  # NEW (generated)
├── ruff.toml                                # NEW (Task 2)
├── mypy.ini                                 # NEW (Task 2)
├── .pre-commit-config.yaml                  # MODIFY (Task 2) — extend with ruff/mypy
├── pipeline/
│   ├── __init__.py                         # NEW (Task 3)
│   ├── config.py                           # NEW (Task 3) — paths, model defaults
│   ├── db.py                               # NEW (Task 4) — sqlite helpers, migrations
│   ├── schemas/
│   │   ├── __init__.py                     # NEW (Task 4)
│   │   ├── corpus_schema.sql               # NEW (Task 5)
│   │   └── canonical_schema.sql            # NEW (Tasks 9–10)
│   ├── reign_table.json                    # NEW (Task 11)
│   ├── dates.py                            # NEW (Tasks 12–16)
│   ├── stage1_ingest.py                    # NEW (Tasks 6–7)
│   ├── stage2_chunk.py                     # NEW (Task 8)
│   ├── stage4_normalize.py                 # NEW (Task 16) — thin wrapper over dates.py
│   ├── stage7_load.py                      # NEW (Tasks 17–20)
│   ├── stage9_export.py                    # NEW (Tasks 21–24)
│   ├── llm_cache.py                        # NEW (Task 25) — empty shell for Phase 2
│   └── cli.py                              # NEW (Task 26)
├── tests/
│   ├── __init__.py                         # NEW (Task 1)
│   ├── conftest.py                         # NEW (Task 4) — shared fixtures, tmp dbs
│   ├── unit/
│   │   ├── test_db.py                      # NEW (Task 4)
│   │   ├── test_corpus_schema.py           # NEW (Task 5)
│   │   ├── test_stage1_ingest.py           # NEW (Tasks 6–7)
│   │   ├── test_stage2_chunk.py            # NEW (Task 8)
│   │   ├── test_canonical_schema.py        # NEW (Tasks 9–10)
│   │   ├── test_reign_table.py             # NEW (Task 11)
│   │   ├── test_dates.py                   # NEW (Tasks 12–15)
│   │   ├── test_stage4_normalize.py        # NEW (Task 16)
│   │   ├── test_stage7_load.py             # NEW (Tasks 17–20)
│   │   ├── test_stage9_export.py           # NEW (Tasks 21–24)
│   │   └── test_cli.py                     # NEW (Task 26)
│   └── integration/
│       ├── __init__.py
│       └── test_roundtrip.py               # NEW (Task 27)
└── knowledge/                              # MODIFY most tasks (same-task rule)
    └── log.md, index.md, concepts/...
```

---

## Task 1 — Python project bootstrap

**Files:**
- Create: `pyproject.toml`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`
- Test: `tests/unit/test_smoke.py` (deleted at end of task)

- [ ] **Step 1.1: Write a failing smoke test that imports `pipeline`**

Create `tests/unit/test_smoke.py`:

```python
def test_pipeline_module_importable():
    import pipeline  # noqa: F401
```

- [ ] **Step 1.2: Run the test, confirm it fails**

```
uv run pytest tests/unit/test_smoke.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline'`.

- [ ] **Step 1.3: Create `pyproject.toml`**

```toml
[project]
name = "changjuan"
version = "0.1.0"
description = "Knowledge-graph extraction of Eastern-Zhou history from 《东周列国志》"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.5",
    "mypy>=1.10",
    "pre-commit>=3.7",
]

[project.scripts]
changjuan = "pipeline.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["pipeline", "curation"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 1.4: Create empty package marker files**

```bash
mkdir -p pipeline curation pipeline/schemas tests/unit tests/integration
touch pipeline/__init__.py curation/__init__.py pipeline/schemas/__init__.py
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 1.5: Sync environment**

```
uv sync --extra dev
```

Expected: lockfile generated, dependencies installed.

- [ ] **Step 1.6: Run the smoke test, confirm it passes; delete it**

```
uv run pytest tests/unit/test_smoke.py -v
```

Expected: 1 passed. Then `rm tests/unit/test_smoke.py`.

- [ ] **Step 1.7: Commit**

```bash
git add pyproject.toml uv.lock pipeline curation tests
git commit -m "chore: scaffold Python project structure

no knowledge impact: pure scaffolding, no behaviour or model change yet."
```

---

## Task 2 — Lint, type-check, and pre-commit hooks

**Files:**
- Create: `ruff.toml`, `mypy.ini`
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 2.1: Add `ruff.toml`**

```toml
target-version = "py312"
line-length = 100

[lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
ignore = []

[lint.per-file-ignores]
"tests/**" = ["B011"]
```

- [ ] **Step 2.2: Add `mypy.ini`**

```ini
[mypy]
python_version = 3.12
strict = True
exclude = (?x)(^build/|^dist/|^data/)

[mypy-tests.*]
disallow_untyped_defs = False
```

- [ ] **Step 2.3: Extend `.pre-commit-config.yaml`**

Read the current `.pre-commit-config.yaml`. Append (or merge into the existing `repos:` list) hooks for ruff + mypy:

```yaml
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.5.0
  hooks:
    - id: ruff
      args: [--fix]
    - id: ruff-format
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.10.0
  hooks:
    - id: mypy
      additional_dependencies: [structlog, typer]
      args: [--config-file=mypy.ini]
      files: ^(pipeline|curation|tests)/
```

- [ ] **Step 2.4: Install pre-commit hooks**

```
uv run pre-commit install
uv run pre-commit run --all-files
```

Expected: hooks installed; first run may auto-format files — let it, then run again. Final run should be clean.

- [ ] **Step 2.5: Update knowledge — append to `knowledge/log.md`**

Append entry:

```markdown
## [2026-05-20] tooling: linting + type-checking + hooks

Added ruff (linter + formatter), mypy (strict type-checking), pre-commit hooks for ruff/mypy. No knowledge articles changed yet — this is pure tooling, no behaviour, model, or architecture.

`no knowledge impact: tooling only.`
```

- [ ] **Step 2.6: Commit**

```bash
git add ruff.toml mypy.ini .pre-commit-config.yaml knowledge/log.md
git commit -m "chore: enable ruff, mypy, and pre-commit hooks"
```

---

## Task 3 — `pipeline.config` and structlog setup

**Files:**
- Create: `pipeline/config.py`, `tests/unit/test_config.py`

- [ ] **Step 3.1: Write the failing test**

Create `tests/unit/test_config.py`:

```python
from pathlib import Path

from pipeline.config import Config


def test_config_default_paths(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    assert cfg.corpus_db == tmp_path / "data" / "corpus.sqlite"
    assert cfg.canonical_db == tmp_path / "data" / "changjuan.sqlite"
    assert cfg.exports_dir == tmp_path / "data" / "exports"
    assert cfg.corpora_dir == tmp_path / "corpora"


def test_config_chunk_overlap_defaults() -> None:
    cfg = Config()
    assert cfg.chunk_target_chars == 1800
    assert cfg.chunk_overlap_chars == 200
```

- [ ] **Step 3.2: Run the test, confirm it fails**

```
uv run pytest tests/unit/test_config.py -v
```

Expected: `ImportError: cannot import name 'Config'`.

- [ ] **Step 3.3: Implement `pipeline/config.py`**

```python
"""Runtime configuration for the changjuan pipeline.

Single source of truth for paths, batch sizes, and tunable constants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    repo_root: Path = field(default_factory=_default_repo_root)
    chunk_target_chars: int = 1800
    chunk_overlap_chars: int = 200

    @property
    def data_dir(self) -> Path:
        return self.repo_root / "data"

    @property
    def corpus_db(self) -> Path:
        return self.data_dir / "corpus.sqlite"

    @property
    def canonical_db(self) -> Path:
        return self.data_dir / "changjuan.sqlite"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def corpora_dir(self) -> Path:
        return self.repo_root / "corpora"
```

- [ ] **Step 3.4: Run the test, confirm it passes**

```
uv run pytest tests/unit/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 3.5: Add `affects:` glob to the architecture article**

Edit `knowledge/concepts/pipeline/architecture.md`'s frontmatter:

```yaml
affects:
  - pipeline/config.py
```

- [ ] **Step 3.6: Append to `knowledge/log.md`**

```markdown
## [2026-05-20] pipeline: Config dataclass for paths and tunables

Added `pipeline.config.Config` — a frozen dataclass that centralizes repo paths, data-dir paths, and chunking tunables (`chunk_target_chars=1800`, `chunk_overlap_chars=200`). Future stages read from this rather than hardcoding paths.

Articles touched: `concepts/pipeline/architecture.md` (added `affects: [pipeline/config.py]`).
```

- [ ] **Step 3.7: Commit**

```bash
git add pipeline/config.py tests/unit/test_config.py knowledge/concepts/pipeline/architecture.md knowledge/log.md
git commit -m "feat(pipeline): add Config dataclass for paths and tunables"
```

---

## Task 4 — SQLite helpers (`pipeline/db.py`) + shared fixtures

**Files:**
- Create: `pipeline/db.py`, `tests/conftest.py`, `tests/unit/test_db.py`

- [ ] **Step 4.1: Write the failing test**

Create `tests/unit/test_db.py`:

```python
from pathlib import Path

import pytest

from pipeline.db import connect, apply_schema


SCHEMA_SQL = """
CREATE TABLE widgets (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES widgets(id)
);
"""


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with connect(db) as conn:
        cur = conn.execute("PRAGMA foreign_keys;")
        assert cur.fetchone()[0] == 1


def test_apply_schema_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with connect(db) as conn:
        apply_schema(conn, SCHEMA_SQL)
        apply_schema(conn, SCHEMA_SQL)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        names = {row[0] for row in cur}
        assert "widgets" in names


def test_foreign_key_violation_raises(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with connect(db) as conn:
        apply_schema(conn, SCHEMA_SQL)
        with pytest.raises(Exception):
            conn.execute("INSERT INTO widgets (id, parent_id) VALUES ('a', 'missing');")
            conn.commit()
```

- [ ] **Step 4.2: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_db_dir(tmp_path: Path) -> Path:
    """Empty directory for ad-hoc sqlite databases."""
    (tmp_path / "data").mkdir()
    return tmp_path
```

- [ ] **Step 4.3: Run the test, confirm it fails**

```
uv run pytest tests/unit/test_db.py -v
```

Expected: `ImportError`.

- [ ] **Step 4.4: Implement `pipeline/db.py`**

```python
"""SQLite helpers: connection with sensible defaults + idempotent schema application."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with foreign keys + WAL enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def apply_schema(conn: sqlite3.Connection, sql: str) -> None:
    """Apply a SQL DDL script. Idempotent if the script uses IF NOT EXISTS."""
    conn.executescript(sql)
    conn.commit()
```

- [ ] **Step 4.5: Run the test, confirm it passes**

```
uv run pytest tests/unit/test_db.py -v
```

Expected: 3 passed.

- [ ] **Step 4.6: Append to log; commit**

```markdown
## [2026-05-20] pipeline: SQLite helpers (db.py)

Added `pipeline.db.connect` (context-manager: foreign_keys ON, WAL on, Row factory) and `pipeline.db.apply_schema` (idempotent DDL via `executescript`). All future stages use these rather than calling sqlite3 directly.

Articles touched: none yet (db.py is utility; will be referenced by article `affects:` globs once stages 1/7/9 land).
```

```bash
git add pipeline/db.py tests/conftest.py tests/unit/test_db.py knowledge/log.md
git commit -m "feat(pipeline): sqlite connect + apply_schema helpers"
```

---

## Task 5 — `corpus.sqlite` schema

**Files:**
- Create: `pipeline/schemas/corpus_schema.sql`, `tests/unit/test_corpus_schema.py`

- [ ] **Step 5.1: Write the failing test**

```python
from pathlib import Path

from pipeline.db import connect, apply_schema
from pipeline.schemas import CORPUS_SCHEMA


def _table_names(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}


def test_corpus_schema_creates_expected_tables(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        names = _table_names(conn)
    assert {"documents", "chunks", "citations"} <= names


def test_corpus_schema_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        apply_schema(conn, CORPUS_SCHEMA)
        # Should not raise; tables still present
        assert "documents" in _table_names(conn)


def test_documents_required_columns(tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(documents);")}
    assert {"id", "corpus", "title", "chapter_num", "chapter_title", "raw_text", "source_edition", "ingested_at"} <= cols
```

- [ ] **Step 5.2: Run, confirm failure**

```
uv run pytest tests/unit/test_corpus_schema.py -v
```

Expected: `ImportError: cannot import name 'CORPUS_SCHEMA'`.

- [ ] **Step 5.3: Create `pipeline/schemas/corpus_schema.sql`**

```sql
-- corpus.sqlite — immutable after stage 1.
-- One row per chapter (or canonical section in non-novel corpora).

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    corpus          TEXT NOT NULL CHECK (corpus IN ('dongzhoulieguozhi', 'zuozhuan', 'shiji')),
    title           TEXT NOT NULL,
    chapter_num     INTEGER NOT NULL,
    chapter_title   TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    source_edition  TEXT NOT NULL,
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (corpus, chapter_num)
);

CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id),
    paragraph_start INTEGER NOT NULL,
    paragraph_end   INTEGER NOT NULL,
    text            TEXT NOT NULL,
    hash            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(hash);

CREATE TABLE IF NOT EXISTS citations (
    id              TEXT PRIMARY KEY,
    chunk_id        TEXT NOT NULL REFERENCES chunks(id),
    span_start      INTEGER NOT NULL,
    span_end        INTEGER NOT NULL,
    quote           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id);
```

- [ ] **Step 5.4: Expose the schema string from `pipeline.schemas`**

Replace `pipeline/schemas/__init__.py` with:

```python
from pathlib import Path

_HERE = Path(__file__).parent

CORPUS_SCHEMA: str = (_HERE / "corpus_schema.sql").read_text(encoding="utf-8")
```

- [ ] **Step 5.5: Run, confirm pass**

```
uv run pytest tests/unit/test_corpus_schema.py -v
```

Expected: 3 passed.

- [ ] **Step 5.6: Knowledge update**

The `corpus.sqlite` schema is mentioned in `concepts/data-model/knowledge-graph.md` only obliquely (citations live in corpus.sqlite, every record cites). Add `affects:` glob:

Edit `knowledge/concepts/data-model/knowledge-graph.md` frontmatter to include:

```yaml
affects:
  - pipeline/schemas/corpus_schema.sql
```

Append log entry:

```markdown
## [2026-05-20] schema: corpus.sqlite (documents, chunks, citations)

Created the immutable source-side schema: `documents` (one per chapter), `chunks` (paragraph-aware splits with overlap), `citations` (verbatim quote spans). Foreign keys on `chunks.document_id` and `citations.chunk_id` enforced; `UNIQUE (corpus, chapter_num)` prevents accidental double-ingest. WAL mode and PRAGMA foreign_keys=ON by way of `pipeline.db.connect`.

Articles touched: `concepts/data-model/knowledge-graph.md` (+ affects glob for the schema file).
```

- [ ] **Step 5.7: Commit**

```bash
git add pipeline/schemas/corpus_schema.sql pipeline/schemas/__init__.py tests/unit/test_corpus_schema.py knowledge/concepts/data-model/knowledge-graph.md knowledge/log.md
git commit -m "feat(schema): corpus.sqlite — documents, chunks, citations"
```

---

## Task 6 — Stage 1 ingest: read `dongzhoulieguozhi` JSON → `documents`

**Files:**
- Create: `pipeline/stage1_ingest.py`, `tests/unit/test_stage1_ingest.py`

- [ ] **Step 6.1: Write the failing test**

```python
import json
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi


def _make_fake_corpus(corpora_dir: Path) -> Path:
    """Synthesize the dongzhoulieguozhi/json/东周列国志.json file the real corpus exposes."""
    repo = corpora_dir / "dongzhoulieguozhi"
    (repo / "json").mkdir(parents=True)
    data = {
        "title": "东周列国志",
        "chapters": [
            {"title": "第一回　test 1", "content": "para A\r\npara B"},
            {"title": "第二回　test 2", "content": "para C"},
        ],
    }
    p = repo / "json" / "东周列国志.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return repo


def test_ingest_inserts_one_row_per_chapter(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    _make_fake_corpus(cfg.corpora_dir)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        count = ingest_dongzhoulieguozhi(conn, cfg)
    assert count == 2
    with connect(cfg.corpus_db) as conn:
        rows = list(conn.execute("SELECT corpus, chapter_num, chapter_title FROM documents ORDER BY chapter_num;"))
    assert rows[0]["corpus"] == "dongzhoulieguozhi"
    assert rows[0]["chapter_num"] == 1
    assert rows[1]["chapter_num"] == 2


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    _make_fake_corpus(cfg.corpora_dir)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        ingest_dongzhoulieguozhi(conn, cfg)
        # second call must not crash on UNIQUE constraint
        ingest_dongzhoulieguozhi(conn, cfg)
        count = conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    assert count == 2
```

- [ ] **Step 6.2: Run, confirm failure**

```
uv run pytest tests/unit/test_stage1_ingest.py -v
```

Expected: `ImportError`.

- [ ] **Step 6.3: Implement `pipeline/stage1_ingest.py`**

```python
"""Stage 1 — Ingest source corpora into corpus.sqlite.

Reads the upstream dongzhoulieguozhi repo's pre-built JSON (`json/东周列国志.json`)
which holds one entry per chapter. Inserts one `documents` row per chapter with a
stable id `dzl:<chapter_num>` so downstream stages get reproducible references.

Idempotent: re-running over the same corpus has no effect (ON CONFLICT DO NOTHING
on the unique `(corpus, chapter_num)` constraint).
"""
from __future__ import annotations

import json
import sqlite3

from pipeline.config import Config


def ingest_dongzhoulieguozhi(conn: sqlite3.Connection, cfg: Config) -> int:
    """Ingest 东周列国志. Returns the number of rows inserted (or already present)."""
    src = cfg.corpora_dir / "dongzhoulieguozhi" / "json" / "东周列国志.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    rows = [
        {
            "id": f"dzl:{i + 1}",
            "corpus": "dongzhoulieguozhi",
            "title": data.get("title", "东周列国志"),
            "chapter_num": i + 1,
            "chapter_title": ch["title"],
            "raw_text": ch["content"],
            "source_edition": "dongzhoulieguozhi/json (upstream repo)",
        }
        for i, ch in enumerate(chapters)
    ]
    conn.executemany(
        """
        INSERT INTO documents (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition)
        VALUES (:id, :corpus, :title, :chapter_num, :chapter_title, :raw_text, :source_edition)
        ON CONFLICT (corpus, chapter_num) DO NOTHING;
        """,
        rows,
    )
    return len(rows)
```

- [ ] **Step 6.4: Run, confirm pass**

```
uv run pytest tests/unit/test_stage1_ingest.py -v
```

Expected: 2 passed.

- [ ] **Step 6.5: Knowledge update**

Edit `knowledge/concepts/pipeline/architecture.md` frontmatter `affects:` glob to include the new file:

```yaml
affects:
  - pipeline/config.py
  - pipeline/stage1_ingest.py
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] stage 1: ingest 东周列国志 from JSON

Implemented `pipeline.stage1_ingest.ingest_dongzhoulieguozhi`: reads the upstream `dongzhoulieguozhi/json/东周列国志.json`, inserts one row per chapter into `corpus.sqlite.documents` with stable id `dzl:<n>`. Idempotent via ON CONFLICT DO NOTHING on `(corpus, chapter_num)`.

Articles touched: `concepts/pipeline/architecture.md` (added `pipeline/stage1_ingest.py` to affects).
```

- [ ] **Step 6.6: Commit**

```bash
git add pipeline/stage1_ingest.py tests/unit/test_stage1_ingest.py knowledge/concepts/pipeline/architecture.md knowledge/log.md
git commit -m "feat(stage1): ingest 东周列国志 chapters from upstream JSON"
```

---

## Task 7 — Stage 1: smoke-test against the real 108-chapter corpus

**Files:**
- Modify: `tests/unit/test_stage1_ingest.py`

- [ ] **Step 7.1: Add an integration-flavoured test**

Append to `tests/unit/test_stage1_ingest.py`:

```python
import os
import pytest


@pytest.mark.skipif(
    not Path("corpora/dongzhoulieguozhi/json/东周列国志.json").exists(),
    reason="real corpus not present (symlink missing?)",
)
def test_ingest_real_corpus_has_108_chapters() -> None:
    """Sanity check against the real upstream corpus."""
    cfg = Config()
    tmp = Path(os.environ.get("PYTEST_TMP", "/tmp")) / "changjuan-test-corpus.sqlite"
    if tmp.exists():
        tmp.unlink()
    cfg_with_tmp = Config(repo_root=cfg.repo_root)
    # use tmp db path explicitly via apply_schema/ingest
    from pipeline.db import apply_schema, connect
    from pipeline.schemas import CORPUS_SCHEMA
    with connect(tmp) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = ingest_dongzhoulieguozhi(conn, cfg_with_tmp)
        assert n == 108
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE corpus='dongzhoulieguozhi';").fetchone()[0] == 108
```

- [ ] **Step 7.2: Run; confirm pass against the real corpus**

```
uv run pytest tests/unit/test_stage1_ingest.py::test_ingest_real_corpus_has_108_chapters -v
```

Expected: 1 passed. (If the symlink at `corpora/dongzhoulieguozhi` is missing or the JSON file path differs, the test skips — investigate before committing.)

- [ ] **Step 7.3: Knowledge update**

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] stage 1: 108-chapter sanity test wired up

Added a guard test that ingests the real upstream 东周列国志 (via the `corpora/dongzhoulieguozhi` symlink) and asserts exactly 108 chapter rows land. Skipped automatically if the corpus symlink is missing. This is our canary: when upstream changes shape, this fires before silent data loss.

`no article impact: same affects glob (pipeline/stage1_ingest.py).`
```

- [ ] **Step 7.4: Commit**

```bash
git add tests/unit/test_stage1_ingest.py knowledge/log.md
git commit -m "test(stage1): smoke-test against real 108-chapter corpus"
```

---

## Task 8 — Stage 2: chunking with paragraph-aware splits + overlap

**Files:**
- Create: `pipeline/stage2_chunk.py`, `tests/unit/test_stage2_chunk.py`

- [ ] **Step 8.1: Write the failing test**

```python
from pathlib import Path

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CORPUS_SCHEMA
from pipeline.stage2_chunk import chunk_documents


def _seed_doc(conn, doc_id: str, paragraphs: list[str]) -> None:
    text = "\n\n".join(paragraphs)
    conn.execute(
        "INSERT INTO documents (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition) "
        "VALUES (?, 'dongzhoulieguozhi', 't', 1, 'ch', ?, 'fixture');",
        (doc_id, text),
    )


def test_chunk_short_doc_yields_one_chunk(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path, chunk_target_chars=500, chunk_overlap_chars=50)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        _seed_doc(conn, "d1", ["short para one.", "short para two."])
        n = chunk_documents(conn, cfg)
        chunks = list(conn.execute("SELECT id, paragraph_start, paragraph_end, text FROM chunks;"))
    assert n == 1
    assert len(chunks) == 1
    assert chunks[0]["paragraph_start"] == 0
    assert chunks[0]["paragraph_end"] == 1  # inclusive last paragraph index


def test_chunk_long_doc_splits_on_paragraph_boundaries(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path, chunk_target_chars=120, chunk_overlap_chars=20)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        paragraphs = [f"para number {i} " + "x" * 80 for i in range(6)]
        _seed_doc(conn, "d1", paragraphs)
        chunk_documents(conn, cfg)
        chunks = list(conn.execute("SELECT paragraph_start, paragraph_end FROM chunks ORDER BY paragraph_start;"))
    # No chunk slices a paragraph mid-text
    for c in chunks:
        assert c["paragraph_start"] <= c["paragraph_end"]
    # Overlap means chunk N+1's start <= chunk N's end (in paragraph index space)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert nxt["paragraph_start"] <= prev["paragraph_end"] + 1


def test_chunk_ids_are_deterministic(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        _seed_doc(conn, "d1", ["alpha", "beta"])
        chunk_documents(conn, cfg)
        first = [row[0] for row in conn.execute("SELECT id FROM chunks ORDER BY paragraph_start;")]
    # Re-chunking the same doc yields the same chunk ids
    with connect(cfg.corpus_db) as conn:
        conn.execute("DELETE FROM chunks;")
        chunk_documents(conn, cfg)
        second = [row[0] for row in conn.execute("SELECT id FROM chunks ORDER BY paragraph_start;")]
    assert first == second
```

- [ ] **Step 8.2: Run, confirm failure**

```
uv run pytest tests/unit/test_stage2_chunk.py -v
```

Expected: `ImportError`.

- [ ] **Step 8.3: Implement `pipeline/stage2_chunk.py`**

```python
"""Stage 2 — paragraph-aware chunking with overlap.

A chunk never splits a paragraph mid-text. Chunks accumulate paragraphs until the
target character count is reached, then a new chunk starts. The new chunk's first
paragraph(s) overlap with the prior chunk's last paragraph(s) by approximately
`chunk_overlap_chars` characters — preserving cross-paragraph references for the
LLM extraction stage.

Chunk ids are deterministic: `chk:<document_id>:<paragraph_start>`. This lets
citations encode chunk identity stably across re-runs.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3

from pipeline.config import Config


_PARA_SEP = re.compile(r"\r?\n\s*\r?\n+")


def _split_paragraphs(raw: str) -> list[str]:
    parts = [p.strip() for p in _PARA_SEP.split(raw) if p.strip()]
    return parts


def _chunk_paragraphs(paragraphs: list[str], target: int, overlap: int) -> list[tuple[int, int, str]]:
    """Return list of (paragraph_start, paragraph_end_inclusive, text)."""
    if not paragraphs:
        return []
    chunks: list[tuple[int, int, str]] = []
    i = 0
    n = len(paragraphs)
    while i < n:
        start = i
        running = ""
        end = i
        while end < n and len(running) + len(paragraphs[end]) + 2 <= target:
            running = running + ("\n\n" if running else "") + paragraphs[end]
            end += 1
        if end == start:  # single paragraph longer than target — keep it whole
            running = paragraphs[end]
            end += 1
        chunks.append((start, end - 1, running))
        if end >= n:
            break
        # Walk back paragraphs from end until we've covered ~overlap chars
        back = end
        back_chars = 0
        while back > start + 1 and back_chars < overlap:
            back -= 1
            back_chars += len(paragraphs[back])
        i = back
    return chunks


def chunk_documents(conn: sqlite3.Connection, cfg: Config) -> int:
    """Chunk every document that has no chunks yet. Returns number of chunks written."""
    docs = conn.execute(
        "SELECT id, raw_text FROM documents WHERE id NOT IN (SELECT DISTINCT document_id FROM chunks);"
    ).fetchall()
    written = 0
    for doc in docs:
        paragraphs = _split_paragraphs(doc["raw_text"])
        for p_start, p_end, text in _chunk_paragraphs(paragraphs, cfg.chunk_target_chars, cfg.chunk_overlap_chars):
            chunk_id = f"chk:{doc['id']}:{p_start}"
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            conn.execute(
                "INSERT INTO chunks (id, document_id, paragraph_start, paragraph_end, text, hash) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (chunk_id, doc["id"], p_start, p_end, text, h),
            )
            written += 1
    return written
```

- [ ] **Step 8.4: Run, confirm pass**

```
uv run pytest tests/unit/test_stage2_chunk.py -v
```

Expected: 3 passed.

- [ ] **Step 8.5: Knowledge update + commit**

Edit `knowledge/concepts/pipeline/architecture.md` `affects:`:

```yaml
affects:
  - pipeline/config.py
  - pipeline/stage1_ingest.py
  - pipeline/stage2_chunk.py
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] stage 2: paragraph-aware chunking with overlap

Implemented `pipeline.stage2_chunk.chunk_documents`. Chunks accumulate paragraphs up to `chunk_target_chars` (default 1800), then start a new chunk that overlaps the prior chunk's tail by ~`chunk_overlap_chars` (default 200) characters. No chunk splits a paragraph mid-text. Chunk ids are deterministic `chk:<doc_id>:<paragraph_start>` so citations stay stable across re-runs. SHA-256 (first 16 chars) on chunk text in `hash` for LLM-cache keying in Phase 2.

Articles touched: `concepts/pipeline/architecture.md` (+ stage2_chunk.py to affects).
```

```bash
git add pipeline/stage2_chunk.py tests/unit/test_stage2_chunk.py knowledge/concepts/pipeline/architecture.md knowledge/log.md
git commit -m "feat(stage2): paragraph-aware chunking with overlap"
```

---

## Task 9 — Canonical schema: entity + relation tables

**Files:**
- Create: `pipeline/schemas/canonical_schema.sql`
- Modify: `pipeline/schemas/__init__.py`, `tests/unit/test_canonical_schema.py` (new)

- [ ] **Step 9.1: Write the failing test**

```python
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA


CORE_TABLES = {
    "persons", "person_variants", "states", "state_capitals", "places", "events",
    "event_participants", "event_places", "event_relations",
    "person_relations", "person_states", "entity_citations",
}


def _table_names(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}


def test_canonical_schema_creates_core_tables(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        names = _table_names(conn)
    missing = CORE_TABLES - names
    assert not missing, f"missing tables: {missing}"


def test_person_relations_includes_clan_member_kind(tmp_path: Path) -> None:
    """clan_member is the kind used until Family is promoted to a first-class entity."""
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Seed minimal rows to verify FK constraint on `kind`
        conn.execute("INSERT INTO persons (id, canonical_name, confidence, provenance) VALUES ('per:a', 'a', 0.9, 'auto');")
        conn.execute("INSERT INTO persons (id, canonical_name, confidence, provenance) VALUES ('per:b', 'b', 0.9, 'auto');")
        conn.execute(
            "INSERT INTO person_relations (from_person_id, to_person_id, kind, confidence, provenance) "
            "VALUES ('per:a', 'per:b', 'clan_member', 0.9, 'auto');"
        )
```

- [ ] **Step 9.2: Run, confirm failure**

```
uv run pytest tests/unit/test_canonical_schema.py -v
```

Expected: `ImportError: CANONICAL_SCHEMA`.

- [ ] **Step 9.3: Create `pipeline/schemas/canonical_schema.sql`**

```sql
-- changjuan.sqlite — canonical knowledge graph + candidate staging.
-- Schema follows the 2026-05-20 design spec §5.

-- =========================================================
-- ENTITY TABLES
-- =========================================================

CREATE TABLE IF NOT EXISTS persons (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    gender          TEXT,
    birth_date_json TEXT,
    death_date_json TEXT,
    notes           TEXT,
    state_id        TEXT REFERENCES states(id),
    clan_name       TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS person_variants (
    id          TEXT PRIMARY KEY,
    person_id   TEXT NOT NULL REFERENCES persons(id),
    variant     TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('本名','字','谥号','封号','别名')),
    UNIQUE (person_id, variant, kind)
);

CREATE TABLE IF NOT EXISTS states (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    founded_date_json   TEXT,
    ended_date_json     TEXT,
    ruling_clan         TEXT,
    type                TEXT,
    confidence          REAL NOT NULL,
    provenance          TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS places (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT,
    lat             REAL,
    lon             REAL,
    coord_confidence REAL,
    modern_equiv    TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS state_capitals (
    id                  TEXT PRIMARY KEY,
    state_id            TEXT NOT NULL REFERENCES states(id),
    place_id            TEXT NOT NULL REFERENCES places(id),
    from_date_json      TEXT,
    to_date_json        TEXT,
    citation_id         TEXT,
    confidence          REAL NOT NULL,
    provenance          TEXT NOT NULL CHECK (provenance IN ('auto','curated'))
);

CREATE TABLE IF NOT EXISTS events (
    id                  TEXT PRIMARY KEY,
    type                TEXT NOT NULL,
    date_json           TEXT,
    outcome             TEXT,
    summary             TEXT,
    primary_place_id    TEXT REFERENCES places(id),
    confidence          REAL NOT NULL,
    provenance          TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- RELATION TABLES
-- =========================================================

CREATE TABLE IF NOT EXISTS event_participants (
    event_id        TEXT NOT NULL REFERENCES events(id),
    person_id       TEXT NOT NULL REFERENCES persons(id),
    role            TEXT NOT NULL,
    role_detail     TEXT,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (event_id, person_id, role)
);

CREATE TABLE IF NOT EXISTS event_places (
    event_id        TEXT NOT NULL REFERENCES events(id),
    place_id        TEXT NOT NULL REFERENCES places(id),
    role            TEXT NOT NULL,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (event_id, place_id, role)
);

CREATE TABLE IF NOT EXISTS event_relations (
    from_event_id   TEXT NOT NULL REFERENCES events(id),
    to_event_id     TEXT NOT NULL REFERENCES events(id),
    kind            TEXT NOT NULL CHECK (kind IN ('causes','precedes','related')),
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (from_event_id, to_event_id, kind)
);

CREATE TABLE IF NOT EXISTS person_relations (
    from_person_id  TEXT NOT NULL REFERENCES persons(id),
    to_person_id    TEXT NOT NULL REFERENCES persons(id),
    kind            TEXT NOT NULL CHECK (kind IN (
        'parent','child','spouse','sibling','mentor','ruler','minister',
        'ally','rival','killed_by','clan_member'
    )),
    date_json       TEXT,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (from_person_id, to_person_id, kind)
);

CREATE TABLE IF NOT EXISTS person_states (
    person_id       TEXT NOT NULL REFERENCES persons(id),
    state_id        TEXT NOT NULL REFERENCES states(id),
    role            TEXT NOT NULL CHECK (role IN ('ruler','minister','exile','defector','citizen','other')),
    from_date_json  TEXT,
    to_date_json    TEXT,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (person_id, state_id, role, from_date_json)
);

CREATE TABLE IF NOT EXISTS entity_citations (
    entity_kind     TEXT NOT NULL CHECK (entity_kind IN ('person','state','place','event')),
    entity_id       TEXT NOT NULL,
    citation_id     TEXT NOT NULL,
    PRIMARY KEY (entity_kind, entity_id, citation_id)
);
```

- [ ] **Step 9.4: Update `pipeline/schemas/__init__.py`**

```python
from pathlib import Path

_HERE = Path(__file__).parent

CORPUS_SCHEMA: str = (_HERE / "corpus_schema.sql").read_text(encoding="utf-8")
CANONICAL_SCHEMA: str = (_HERE / "canonical_schema.sql").read_text(encoding="utf-8")
```

- [ ] **Step 9.5: Run, confirm pass**

```
uv run pytest tests/unit/test_canonical_schema.py -v
```

Expected: 2 passed.

- [ ] **Step 9.6: Knowledge update + commit**

Edit `knowledge/concepts/data-model/knowledge-graph.md` `affects:`:

```yaml
affects:
  - pipeline/schemas/corpus_schema.sql
  - pipeline/schemas/canonical_schema.sql
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] schema: changjuan.sqlite — entity + relation tables

Added entity tables (persons, person_variants, states, state_capitals, places, events) and relation tables (event_participants, event_places, event_relations, person_relations, person_states, entity_citations) per spec §5. `person_relations.kind` includes `clan_member` — the deferred-Family lever. Every row carries `confidence`, `provenance ∈ {auto, curated}`, `pipeline_run_id` for traceability.

Articles touched: `concepts/data-model/knowledge-graph.md` (+ canonical_schema.sql to affects).
```

```bash
git add pipeline/schemas/canonical_schema.sql pipeline/schemas/__init__.py tests/unit/test_canonical_schema.py knowledge/concepts/data-model/knowledge-graph.md knowledge/log.md
git commit -m "feat(schema): changjuan.sqlite entity and relation tables"
```

---

## Task 10 — Canonical schema: candidates, bookkeeping, views

**Files:**
- Modify: `pipeline/schemas/canonical_schema.sql`, `tests/unit/test_canonical_schema.py`

- [ ] **Step 10.1: Extend the test**

Append to `tests/unit/test_canonical_schema.py`:

```python
EXTRA_TABLES = {
    "candidate_persons", "candidate_events", "candidate_places", "candidate_states",
    "candidate_event_participants", "candidate_event_places",
    "candidate_event_relations", "candidate_person_relations", "candidate_person_states",
    "candidate_facts",
    "conflicts", "audit_log", "pipeline_runs", "llm_cache",
    "merge_candidates", "qa_samples",
}


def test_canonical_schema_creates_candidate_and_bookkeeping_tables(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        names = _table_names(conn)
    missing = EXTRA_TABLES - names
    assert not missing, f"missing: {missing}"


def test_field_history_view_exists(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        views = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='view';")}
    assert "field_history" in views


def test_audit_log_field_history_query(tmp_path: Path) -> None:
    """Sanity-check the view: insert a field-level audit row, read it back via field_history."""
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor) "
            "VALUES ('al:1', 'person', 'per:a', 'birth_year', 'set', NULL, '{\"value\": 697, \"confidence\": 0.6}', 'extract@v1');"
        )
        rows = list(conn.execute("SELECT entity_id, field, value_json, confidence, source FROM field_history;"))
    assert rows[0]["entity_id"] == "per:a"
    assert rows[0]["field"] == "birth_year"
    assert rows[0]["confidence"] == 0.6
    assert rows[0]["source"] == "extract@v1"
```

- [ ] **Step 10.2: Run, confirm failure**

```
uv run pytest tests/unit/test_canonical_schema.py -v
```

Expected: missing tables / view.

- [ ] **Step 10.3: Append to `pipeline/schemas/canonical_schema.sql`**

```sql
-- =========================================================
-- CANDIDATE TABLES (staging area for unvetted extractor output)
-- =========================================================

CREATE TABLE IF NOT EXISTS candidate_persons (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    gender          TEXT,
    birth_date_json TEXT,
    death_date_json TEXT,
    notes           TEXT,
    state_id        TEXT,
    clan_name       TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_events (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    date_json       TEXT,
    outcome         TEXT,
    summary         TEXT,
    primary_place_id TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_places (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT,
    lat             REAL,
    lon             REAL,
    coord_confidence REAL,
    modern_equiv    TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_states (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    founded_date_json TEXT,
    ended_date_json TEXT,
    ruling_clan     TEXT,
    type            TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_event_participants (
    candidate_event_id  TEXT NOT NULL,
    candidate_person_id TEXT NOT NULL,
    role                TEXT NOT NULL,
    role_detail         TEXT,
    pipeline_run_id     TEXT NOT NULL,
    PRIMARY KEY (candidate_event_id, candidate_person_id, role)
);

CREATE TABLE IF NOT EXISTS candidate_event_places (
    candidate_event_id  TEXT NOT NULL,
    candidate_place_id  TEXT NOT NULL,
    role                TEXT NOT NULL,
    pipeline_run_id     TEXT NOT NULL,
    PRIMARY KEY (candidate_event_id, candidate_place_id, role)
);

CREATE TABLE IF NOT EXISTS candidate_event_relations (
    from_candidate_event_id TEXT NOT NULL,
    to_candidate_event_id   TEXT NOT NULL,
    kind                    TEXT NOT NULL,
    pipeline_run_id         TEXT NOT NULL,
    PRIMARY KEY (from_candidate_event_id, to_candidate_event_id, kind)
);

CREATE TABLE IF NOT EXISTS candidate_person_relations (
    from_candidate_person_id TEXT NOT NULL,
    to_candidate_person_id   TEXT NOT NULL,
    kind                     TEXT NOT NULL,
    date_json                TEXT,
    pipeline_run_id          TEXT NOT NULL,
    PRIMARY KEY (from_candidate_person_id, to_candidate_person_id, kind)
);

CREATE TABLE IF NOT EXISTS candidate_person_states (
    candidate_person_id TEXT NOT NULL,
    candidate_state_id  TEXT NOT NULL,
    role                TEXT NOT NULL,
    from_date_json      TEXT,
    to_date_json        TEXT,
    pipeline_run_id     TEXT NOT NULL,
    PRIMARY KEY (candidate_person_id, candidate_state_id, role)
);

CREATE TABLE IF NOT EXISTS candidate_facts (
    id                      TEXT PRIMARY KEY,
    subject_kind            TEXT NOT NULL,
    subject_candidate_id    TEXT NOT NULL,
    field                   TEXT NOT NULL,
    value_json              TEXT NOT NULL,
    justification_quote     TEXT NOT NULL,
    justification_span      TEXT,
    pipeline_run_id         TEXT NOT NULL
);

-- =========================================================
-- BOOKKEEPING
-- =========================================================

CREATE TABLE IF NOT EXISTS conflicts (
    id                          TEXT PRIMARY KEY,
    subject_kind                TEXT NOT NULL,
    subject_id                  TEXT NOT NULL,
    field                       TEXT NOT NULL,
    variants_json               TEXT NOT NULL,
    current_best_variant_idx    INTEGER NOT NULL,
    resolution_rule             TEXT,
    status                      TEXT NOT NULL CHECK (status IN ('open','resolved')) DEFAULT 'open',
    curator_note                TEXT,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at                 TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              TEXT PRIMARY KEY,
    entity_kind     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    field           TEXT,
    change_kind     TEXT NOT NULL CHECK (change_kind IN ('create','set','delete','merge','split','curator_override')),
    before_json     TEXT,
    after_json      TEXT,
    actor           TEXT NOT NULL,
    at              TEXT NOT NULL DEFAULT (datetime('now')),
    citation_id     TEXT,
    pipeline_run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_entity_field ON audit_log(entity_kind, entity_id, field);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                      TEXT PRIMARY KEY,
    stage                   TEXT NOT NULL,
    started_at              TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at                TEXT,
    prompt_version          TEXT,
    model                   TEXT,
    scope_json              TEXT,
    stats_json              TEXT,
    stats_schema_version    INTEGER
);

CREATE TABLE IF NOT EXISTS llm_cache (
    id                          TEXT PRIMARY KEY,
    key_hash                    TEXT NOT NULL UNIQUE,
    model                       TEXT NOT NULL,
    prompt_template_version     TEXT NOT NULL,
    request_json                TEXT NOT NULL,
    response_json               TEXT NOT NULL,
    tokens_in                   INTEGER,
    tokens_out                  INTEGER,
    cost_usd                    REAL,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS merge_candidates (
    id                  TEXT PRIMARY KEY,
    kind                TEXT NOT NULL CHECK (kind IN ('person','state','place','event')),
    candidate_a_id      TEXT NOT NULL,
    candidate_b_id      TEXT NOT NULL,
    score               REAL NOT NULL,
    surface_features_json TEXT,
    llm_judgment_json   TEXT,
    status              TEXT NOT NULL CHECK (status IN ('open','merged','rejected')) DEFAULT 'open',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at         TEXT
);

CREATE TABLE IF NOT EXISTS qa_samples (
    id              TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    record_kind     TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    field           TEXT NOT NULL,
    verdict         TEXT NOT NULL CHECK (verdict IN ('yes','no','partial')),
    verifier_model  TEXT NOT NULL,
    at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- VIEWS
-- =========================================================

CREATE VIEW IF NOT EXISTS field_history AS
SELECT
    entity_kind,
    entity_id,
    field,
    json_extract(after_json, '$.value')      AS value_json,
    json_extract(after_json, '$.confidence') AS confidence,
    actor                                    AS source,
    citation_id,
    at,
    pipeline_run_id
FROM audit_log
WHERE field IS NOT NULL
ORDER BY entity_kind, entity_id, field, at;
```

- [ ] **Step 10.4: Run, confirm pass**

```
uv run pytest tests/unit/test_canonical_schema.py -v
```

Expected: 4 passed.

- [ ] **Step 10.5: Knowledge update + commit**

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] schema: changjuan.sqlite — candidate, bookkeeping, field_history view

Added candidate_* staging tables (per spec §7 — re-extraction safety), bookkeeping (conflicts, audit_log with the {value, confidence} field-level shape, pipeline_runs with stats_schema_version, llm_cache, merge_candidates, qa_samples), and the `field_history` view that reconstructs per-field history from audit_log without a redundant JSON blob on entity rows. Index on `audit_log(entity_kind, entity_id, field)` keeps the view fast.

Articles touched: `concepts/data-model/knowledge-graph.md` (no glob change — same file).
```

```bash
git add pipeline/schemas/canonical_schema.sql tests/unit/test_canonical_schema.py knowledge/log.md
git commit -m "feat(schema): candidate tables, bookkeeping, field_history view"
```

---

## Task 11 — Reign table (鲁公 + 周王)

**Files:**
- Create: `pipeline/reign_table.json`, `tests/unit/test_reign_table.py`

- [ ] **Step 11.1: Write the failing test**

```python
import json
from pathlib import Path


def _load_reigns() -> dict:
    p = Path(__file__).resolve().parents[2] / "pipeline" / "reign_table.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_reign_table_has_lu_and_zhou_keys() -> None:
    data = _load_reigns()
    assert "lu" in data
    assert "zhou" in data


def test_lu_xigong_year_28_is_632_bce() -> None:
    """鲁僖公二十八年 = 632 BCE (城濮之战 year). Anchor case."""
    data = _load_reigns()
    xigong = data["lu"]["僖公"]
    # Each entry: {"start_bce": <int>, "end_bce": <int>}
    assert xigong["start_bce"] - 27 == 632  # year 28 = start_bce - 27


def test_lu_yingong_year_1_is_722_bce() -> None:
    """鲁隐公元年 = 722 BCE (春秋 begins). Other anchor."""
    data = _load_reigns()
    assert data["lu"]["隐公"]["start_bce"] == 722


def test_zhou_pingwang_year_1_is_770_bce() -> None:
    """周平王元年 = 770 BCE (东周 begins)."""
    data = _load_reigns()
    assert data["zhou"]["平王"]["start_bce"] == 770
```

- [ ] **Step 11.2: Run, confirm failure**

```
uv run pytest tests/unit/test_reign_table.py -v
```

Expected: `FileNotFoundError`.

- [ ] **Step 11.3: Create `pipeline/reign_table.json`**

This is the canonical 鲁公 / 周王 reign chronology for the Spring-Autumn period. Years are BCE (positive integers in BCE convention, i.e., 722 = 722 BCE). Source: 杨伯峻《春秋左传注》chronology.

```json
{
  "_meta": {
    "convention": "All years are BCE as positive integers (722 means 722 BCE). Each reign entry has start_bce (the king/duke's year 1) and end_bce (last year). Reign year N corresponds to BCE year = start_bce - (N - 1).",
    "source": "杨伯峻《春秋左传注》chronology; verified against 史记·十二诸侯年表"
  },
  "zhou": {
    "平王":   {"start_bce": 770, "end_bce": 720},
    "桓王":   {"start_bce": 719, "end_bce": 697},
    "庄王":   {"start_bce": 696, "end_bce": 682},
    "釐王":   {"start_bce": 681, "end_bce": 677},
    "惠王":   {"start_bce": 676, "end_bce": 652},
    "襄王":   {"start_bce": 651, "end_bce": 619},
    "顷王":   {"start_bce": 618, "end_bce": 613},
    "匡王":   {"start_bce": 612, "end_bce": 607},
    "定王":   {"start_bce": 606, "end_bce": 586},
    "简王":   {"start_bce": 585, "end_bce": 572},
    "灵王":   {"start_bce": 571, "end_bce": 545},
    "景王":   {"start_bce": 544, "end_bce": 520},
    "敬王":   {"start_bce": 519, "end_bce": 476}
  },
  "lu": {
    "隐公":   {"start_bce": 722, "end_bce": 712},
    "桓公":   {"start_bce": 711, "end_bce": 694},
    "庄公":   {"start_bce": 693, "end_bce": 662},
    "闵公":   {"start_bce": 661, "end_bce": 660},
    "僖公":   {"start_bce": 659, "end_bce": 627},
    "文公":   {"start_bce": 626, "end_bce": 609},
    "宣公":   {"start_bce": 608, "end_bce": 591},
    "成公":   {"start_bce": 590, "end_bce": 573},
    "襄公":   {"start_bce": 572, "end_bce": 542},
    "昭公":   {"start_bce": 541, "end_bce": 510},
    "定公":   {"start_bce": 509, "end_bce": 495},
    "哀公":   {"start_bce": 494, "end_bce": 468}
  }
}
```

- [ ] **Step 11.4: Run, confirm pass**

```
uv run pytest tests/unit/test_reign_table.py -v
```

Expected: 4 passed. (If the 僖公 year-28 check fails, recompute: 659 - 27 = 632. ✓)

- [ ] **Step 11.5: Knowledge update + commit**

Create new article `knowledge/concepts/data-model/dates-and-reigns.md`:

```markdown
---
title: Dates, reigns, and inference kinds
type: concept
area: data-model
updated: 2026-05-20
status: thin
load_bearing: true
references:
  - concepts/data-model/knowledge-graph.md
affects:
  - pipeline/reign_table.json
  - pipeline/dates.py
---

## What this is

Every Date in changjuan is structured: `{year_bce, uncertainty, year_bce_end?, original, era, inference_kind}`. The `inference_kind` records *how* a BCE year was derived — not all dates in 东周列国志 are equally trustworthy. The bundled `pipeline/reign_table.json` provides the canonical 鲁公 and 周王 chronologies (722 BCE – 468 BCE for 鲁, 770 – 476 BCE for 周) so explicit-reign citations like 鲁僖公二十八年 dereference deterministically to 632 BCE.

## Why this shape, not the alternatives

Storing only `year_bce` would lose the distinction between a citation like 鲁僖公二十八年 (high trust) and a relative reference like 其年 (trust inherited from the anchor) or an era-only mention 春秋末 (range, not point). The pipeline's confidence scoring penalizes anything other than explicit-reign citations; without `inference_kind`, that penalty has nothing to attach to.

## What would invalidate this article

- A reign-year citation in the corpus that the reign table can't dereference (i.e., another state's reigns we haven't tabulated). Promotion path: add the state's reign block alongside `lu` and `zhou`.
- A new `inference_kind` becoming necessary as the corpus surfaces new date forms.

## First commitments

- `pipeline/reign_table.json` source: 杨伯峻《春秋左传注》, cross-checked against 史记·十二诸侯年表.
- `pipeline/dates.py` parsers handle: `explicit_reign_lu`, `explicit_reign_zhou`, `explicit_reign_other` (deferred until needed), `relative_to_prior_event`, `era_only`, `unknown`.
- Reign-year arithmetic: BCE year = `start_bce - (N - 1)` for reign year N.
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] data-model: reign table + dates-and-reigns article

Bundled `pipeline/reign_table.json` with 鲁 and 周 chronologies for the Spring-Autumn period. Created `concepts/data-model/dates-and-reigns.md` as a separate article from the knowledge-graph article — the date model is intricate enough (six `inference_kind` values, reign-year arithmetic) to warrant its own durable explanation.

Articles created: `concepts/data-model/dates-and-reigns.md`.
```

Update `knowledge/index.md` to list the new article under data-model.

```bash
git add pipeline/reign_table.json tests/unit/test_reign_table.py knowledge/concepts/data-model/dates-and-reigns.md knowledge/index.md knowledge/log.md
git commit -m "feat(data-model): bundled 鲁公/周王 reign table + dates-and-reigns article"
```

---

## Task 12 — Date parser: `explicit_reign_lu`

**Files:**
- Create: `pipeline/dates.py`, `tests/unit/test_dates.py`

- [ ] **Step 12.1: Write the failing test**

```python
import pytest

from pipeline.dates import parse_date


def test_lu_xigong_year_28() -> None:
    d = parse_date("鲁僖公二十八年")
    assert d["year_bce"] == 632
    assert d["uncertainty"] == "point"
    assert d["original"] == "鲁僖公二十八年"
    assert d["inference_kind"] == "explicit_reign_lu"


def test_lu_yingong_year_1() -> None:
    d = parse_date("鲁隐公元年")
    assert d["year_bce"] == 722
    assert d["inference_kind"] == "explicit_reign_lu"


def test_lu_zhuanggong_year_10() -> None:
    d = parse_date("鲁庄公十年")
    # 庄公 starts 693 BCE, so year 10 = 684 BCE
    assert d["year_bce"] == 684


@pytest.mark.parametrize("variant", ["鲁僖二十八年", "僖公二十八年"])
def test_lu_lenient_prefixes(variant: str) -> None:
    """Tolerate dropped 鲁 prefix or dropped 公 suffix (common in the novel)."""
    d = parse_date(variant)
    assert d["year_bce"] == 632
```

- [ ] **Step 12.2: Run, confirm failure**

```
uv run pytest tests/unit/test_dates.py -v
```

Expected: `ImportError: parse_date`.

- [ ] **Step 12.3: Implement `pipeline/dates.py` (Lu parser only)**

```python
"""Date parsing for 东周列国志.

The novel uses several date conventions; we dispatch to the matching parser by
pattern. Output is the structured Date dict described in concepts/data-model/dates-and-reigns.md.

This module starts with `explicit_reign_lu` only. Subsequent tasks add
`explicit_reign_zhou`, `relative_to_prior_event`, `era_only`, and `unknown`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

_REIGN_TABLE: dict | None = None


def _reigns() -> dict:
    global _REIGN_TABLE
    if _REIGN_TABLE is None:
        p = Path(__file__).parent / "reign_table.json"
        _REIGN_TABLE = json.loads(p.read_text(encoding="utf-8"))
    return _REIGN_TABLE


class DateDict(TypedDict, total=False):
    year_bce: int | None
    uncertainty: str
    year_bce_end: int
    original: str
    era: str | None
    inference_kind: str


# 一二三...十 mapping for reign-year parsing
_CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "元": 1}


def _cn_to_int(s: str) -> int:
    """Parse 元 / 一 / 十 / 二十 / 二十八 / 三十 etc. up to ~60 — enough for reign years."""
    if s in _CN_DIGIT:
        return _CN_DIGIT[s]
    if "十" in s:
        parts = s.split("十")
        tens = _CN_DIGIT[parts[0]] if parts[0] else 1
        ones = _CN_DIGIT[parts[1]] if parts[1] else 0
        return tens * 10 + ones
    raise ValueError(f"unparseable reign year: {s!r}")


_LU_PATTERN = re.compile(r"^(?:鲁)?(隐|桓|庄|闵|僖|文|宣|成|襄|昭|定|哀)(?:公)?([元一二三四五六七八九十]+)年$")


def parse_date(original: str) -> DateDict:
    """Parse a date string. Returns the structured Date dict."""
    m = _LU_PATTERN.match(original)
    if m:
        duke, year_cn = m.groups()
        duke_full = duke + "公"
        reign = _reigns()["lu"][duke_full]
        n = _cn_to_int(year_cn)
        return DateDict(
            year_bce=reign["start_bce"] - (n - 1),
            uncertainty="point",
            original=original,
            era="春秋",
            inference_kind="explicit_reign_lu",
        )
    # Subsequent tasks add Zhou, relative, era_only, unknown
    raise NotImplementedError(f"parse_date: no parser for {original!r}")
```

- [ ] **Step 12.4: Run, confirm pass**

```
uv run pytest tests/unit/test_dates.py -v
```

Expected: 4 passed (3 explicit + 2 parametrized lenient = 5? — confirm and adjust if 鲁庄公十年 fails; 693 - 9 = 684, ✓).

- [ ] **Step 12.5: Commit (knowledge already created in Task 11)**

```bash
git add pipeline/dates.py tests/unit/test_dates.py
git commit -m "feat(dates): parser for explicit_reign_lu (鲁公纪年)

Articles touched: none — dates-and-reigns.md affects glob already covers pipeline/dates.py."
```

---

## Task 13 — Date parser: `explicit_reign_zhou`

**Files:**
- Modify: `pipeline/dates.py`, `tests/unit/test_dates.py`

- [ ] **Step 13.1: Add failing tests**

Append to `tests/unit/test_dates.py`:

```python
def test_zhou_pingwang_year_1() -> None:
    d = parse_date("周平王元年")
    assert d["year_bce"] == 770
    assert d["inference_kind"] == "explicit_reign_zhou"


def test_zhou_xiangwang_year_20() -> None:
    """周襄王 starts 651 BCE; year 20 = 632 BCE."""
    d = parse_date("周襄王二十年")
    assert d["year_bce"] == 632
    assert d["inference_kind"] == "explicit_reign_zhou"
```

- [ ] **Step 13.2: Run, confirm failure**

```
uv run pytest tests/unit/test_dates.py -v
```

Expected: NotImplementedError on 周平王元年.

- [ ] **Step 13.3: Extend `pipeline/dates.py`**

Add below the Lu pattern:

```python
_ZHOU_PATTERN = re.compile(r"^周(平|桓|庄|釐|惠|襄|顷|匡|定|简|灵|景|敬)(?:王)?([元一二三四五六七八九十]+)年$")


def _try_zhou(original: str) -> DateDict | None:
    m = _ZHOU_PATTERN.match(original)
    if not m:
        return None
    king, year_cn = m.groups()
    king_full = king + "王"
    reign = _reigns()["zhou"][king_full]
    n = _cn_to_int(year_cn)
    return DateDict(
        year_bce=reign["start_bce"] - (n - 1),
        uncertainty="point",
        original=original,
        era="春秋",
        inference_kind="explicit_reign_zhou",
    )
```

Update `parse_date` to try Zhou after Lu:

```python
def parse_date(original: str) -> DateDict:
    if (d := _try_lu(original)) is not None:
        return d
    if (d := _try_zhou(original)) is not None:
        return d
    raise NotImplementedError(f"parse_date: no parser for {original!r}")
```

Refactor the Lu logic into `_try_lu` (returning `DateDict | None`).

- [ ] **Step 13.4: Run, confirm pass**

```
uv run pytest tests/unit/test_dates.py -v
```

Expected: all passed.

- [ ] **Step 13.5: Commit**

```bash
git add pipeline/dates.py tests/unit/test_dates.py
git commit -m "feat(dates): parser for explicit_reign_zhou (周王纪年)

no knowledge impact: same article (dates-and-reigns.md) and same affects glob."
```

---

## Task 14 — Date parser: `era_only` + `unknown`

**Files:**
- Modify: `pipeline/dates.py`, `tests/unit/test_dates.py`

- [ ] **Step 14.1: Add failing tests**

```python
def test_era_only_chunqiu_late() -> None:
    d = parse_date("春秋末")
    assert d["inference_kind"] == "era_only"
    assert d["uncertainty"] == "range"
    assert d["era"] == "春秋"
    assert 500 <= d["year_bce"] <= 480  # midpoint of "late 春秋"
    assert d["year_bce_end"] is not None


def test_era_only_zhanguo_early() -> None:
    d = parse_date("战国初")
    assert d["era"] == "战国"
    assert d["inference_kind"] == "era_only"


def test_unknown_passthrough() -> None:
    d = parse_date("某时")
    assert d["inference_kind"] == "unknown"
    assert d["year_bce"] is None
    assert d["original"] == "某时"
```

- [ ] **Step 14.2: Run, confirm failure**

Expected: NotImplementedError.

- [ ] **Step 14.3: Extend `pipeline/dates.py`**

```python
_ERA_PATTERNS = [
    (re.compile(r"^春秋初$"),  ("春秋", 770, 720)),
    (re.compile(r"^春秋早期$"), ("春秋", 770, 700)),
    (re.compile(r"^春秋中期$"), ("春秋", 700, 600)),
    (re.compile(r"^春秋末$"),   ("春秋", 510, 476)),
    (re.compile(r"^春秋晚期$"), ("春秋", 550, 476)),
    (re.compile(r"^战国初$"),   ("战国", 475, 430)),
    (re.compile(r"^战国早期$"), ("战国", 475, 400)),
    (re.compile(r"^战国中期$"), ("战国", 400, 300)),
    (re.compile(r"^战国末$"),   ("战国", 260, 221)),
    (re.compile(r"^战国晚期$"), ("战国", 300, 221)),
]


def _try_era(original: str) -> DateDict | None:
    for pat, (era, start, end) in _ERA_PATTERNS:
        if pat.match(original):
            return DateDict(
                year_bce=(start + end) // 2,
                year_bce_end=end,
                uncertainty="range",
                original=original,
                era=era,
                inference_kind="era_only",
            )
    return None


def _unknown(original: str) -> DateDict:
    return DateDict(
        year_bce=None,
        uncertainty="point",
        original=original,
        era=None,
        inference_kind="unknown",
    )


def parse_date(original: str) -> DateDict:
    if (d := _try_lu(original)) is not None:
        return d
    if (d := _try_zhou(original)) is not None:
        return d
    if (d := _try_era(original)) is not None:
        return d
    return _unknown(original)
```

- [ ] **Step 14.4: Run, confirm pass**

Expected: all passed. (Note: the `_unknown` fallback means `parse_date` no longer raises; tests for unparseable inputs return `inference_kind='unknown'`.)

- [ ] **Step 14.5: Commit**

```bash
git add pipeline/dates.py tests/unit/test_dates.py
git commit -m "feat(dates): era_only ranges + unknown fallback"
```

---

## Task 15 — Date parser: `relative_to_prior_event`

**Files:**
- Modify: `pipeline/dates.py`, `tests/unit/test_dates.py`

- [ ] **Step 15.1: Add failing test**

```python
def test_relative_明年_with_anchor() -> None:
    anchor = parse_date("鲁僖公二十八年")  # 632 BCE
    d = parse_date("明年", anchor=anchor)
    assert d["year_bce"] == 631
    assert d["inference_kind"] == "relative_to_prior_event"
    assert d["uncertainty"] == "point"


def test_relative_其年_returns_anchor_year() -> None:
    anchor = parse_date("鲁僖公二十八年")
    d = parse_date("其年", anchor=anchor)
    assert d["year_bce"] == 632
    assert d["inference_kind"] == "relative_to_prior_event"


def test_relative_前年_with_anchor() -> None:
    anchor = parse_date("鲁僖公二十八年")
    d = parse_date("前年", anchor=anchor)
    assert d["year_bce"] == 633


def test_relative_without_anchor_returns_unknown() -> None:
    d = parse_date("明年")
    assert d["inference_kind"] == "unknown"
```

- [ ] **Step 15.2: Run, confirm failure**

- [ ] **Step 15.3: Extend `pipeline/dates.py`**

Update the `parse_date` signature to accept an optional anchor:

```python
_RELATIVE_OFFSETS = {
    "其年": 0,
    "明年": -1,    # next year — BCE year decreases
    "次年": -1,
    "去年": +1,    # last year
    "前年": +1,
    "是岁": 0,
    "是年": 0,
}


def _try_relative(original: str, anchor: DateDict | None) -> DateDict | None:
    # Strip a leading 是冬/是夏/是春/是秋 — they're season markers attached to 是年.
    stripped = re.sub(r"^是[春夏秋冬]", "是年", original)
    if stripped not in _RELATIVE_OFFSETS:
        return None
    if anchor is None or anchor.get("year_bce") is None:
        return None
    offset = _RELATIVE_OFFSETS[stripped]
    return DateDict(
        year_bce=anchor["year_bce"] + offset,
        uncertainty="point",
        original=original,
        era=anchor.get("era"),
        inference_kind="relative_to_prior_event",
    )


def parse_date(original: str, anchor: DateDict | None = None) -> DateDict:
    if (d := _try_lu(original)) is not None:
        return d
    if (d := _try_zhou(original)) is not None:
        return d
    if (d := _try_relative(original, anchor)) is not None:
        return d
    if (d := _try_era(original)) is not None:
        return d
    return _unknown(original)
```

- [ ] **Step 15.4: Run, confirm pass**

- [ ] **Step 15.5: Knowledge update + commit**

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] dates: all six inference_kinds parseable

`pipeline.dates.parse_date(original, anchor=None)` now handles all five non-`explicit_reign_other` kinds: explicit_reign_lu, explicit_reign_zhou, relative_to_prior_event (其年/明年/次年/去年/前年/是岁/是年/是+season), era_only (春秋初/中/末/晚期 + 战国初/中/末/晚期), unknown (fallback). `explicit_reign_other` remains deferred until a non-鲁/非周 reign citation appears that needs deterministic resolution.

Articles touched: none (dates-and-reigns.md affects glob unchanged).
```

```bash
git add pipeline/dates.py tests/unit/test_dates.py knowledge/log.md
git commit -m "feat(dates): relative_to_prior_event with anchor chaining"
```

---

## Task 16 — `pipeline/stage4_normalize.py` wrapper

**Files:**
- Create: `pipeline/stage4_normalize.py`, `tests/unit/test_stage4_normalize.py`

- [ ] **Step 16.1: Write the failing test**

```python
from pipeline.stage4_normalize import normalize_date_string


def test_normalize_returns_json_string() -> None:
    s = normalize_date_string("鲁僖公二十八年")
    import json
    d = json.loads(s)
    assert d["year_bce"] == 632
    assert d["inference_kind"] == "explicit_reign_lu"
```

- [ ] **Step 16.2: Run, confirm failure** → **Step 16.3: Implement**:

```python
"""Stage 4 — normalization helpers.

Thin layer over pipeline.dates for stages 3/5/7 to call when they have raw date
strings extracted from chunks. Returns JSON strings ready to insert into the
*_date_json columns of corpus.sqlite and changjuan.sqlite.
"""
from __future__ import annotations

import json

from pipeline.dates import DateDict, parse_date


def normalize_date_string(original: str, anchor_json: str | None = None) -> str:
    anchor: DateDict | None = json.loads(anchor_json) if anchor_json else None
    d = parse_date(original, anchor=anchor)
    return json.dumps(d, ensure_ascii=False)
```

- [ ] **Step 16.4: Run, confirm pass** → **Step 16.5: Commit**

```bash
git add pipeline/stage4_normalize.py tests/unit/test_stage4_normalize.py
git commit -m "feat(stage4): normalize_date_string wrapper returning JSON"
```

---

## Task 17 — Stage 7 load: insert candidate Person → canonical (simple case)

**Files:**
- Create: `pipeline/stage7_load.py`, `tests/unit/test_stage7_load.py`

- [ ] **Step 17.1: Write the failing test**

```python
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage7_load import load_candidate_persons


def _seed_canonical(tmp: Path):
    cm = connect(tmp / "changjuan.sqlite").__enter__()
    apply_schema(cm, CANONICAL_SCHEMA)
    return cm


def test_load_new_person_creates_canonical_row(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'fixture quote');"
        )
        n = load_candidate_persons(conn, pipeline_run_id="run:1")
    assert n == 1
    with connect(tmp_path / "changjuan.sqlite") as conn:
        rows = list(conn.execute("SELECT id, canonical_name, provenance FROM persons;"))
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "重耳"
    assert rows[0]["provenance"] == "auto"


def test_load_emits_create_audit_log(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'fixture');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        logs = list(conn.execute("SELECT entity_id, change_kind, actor FROM audit_log;"))
    assert any(r["change_kind"] == "create" and r["actor"].startswith("load@") for r in logs)
```

- [ ] **Step 17.2: Run, confirm failure** → **Step 17.3: Implement**:

```python
"""Stage 7 — Load candidates into canonical store with field-level merge semantics.

This task implements only the simple case: a candidate Person that does not match
any existing canonical Person becomes a new canonical Person. Subsequent tasks
add: name-variant union, scalar field merging, Conflict emission, and respect for
curator overrides.
"""
from __future__ import annotations

import re
import sqlite3
import uuid


def _slugify(name: str) -> str:
    """Naive Chinese→ASCII-ish slug — fine for v1; will be replaced when pinyin is needed."""
    safe = re.sub(r"[^\w]+", "-", name).strip("-").lower()
    return safe or uuid.uuid4().hex[:8]


def load_candidate_persons(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    """Promote unmatched candidate_persons rows into canonical persons.

    Naive matcher for Task 17: no linking yet. Every candidate becomes a new
    canonical Person whose id is `per:<slug>` or `per:_<hash>` for fallback.
    Task 18+ add variant union, scalar merge, conflict emission.
    """
    cur = conn.execute(
        "SELECT id, canonical_name, gender, birth_date_json, death_date_json, notes, "
        "state_id, clan_name, confidence, chunk_id, quote "
        "FROM candidate_persons WHERE pipeline_run_id = ?;",
        (pipeline_run_id,),
    )
    candidates = cur.fetchall()
    inserted = 0
    for c in candidates:
        person_id = f"per:{_slugify(c['canonical_name'])}"
        # If id collision, append a hash suffix
        existing = conn.execute("SELECT 1 FROM persons WHERE id = ?;", (person_id,)).fetchone()
        if existing is not None:
            person_id = f"{person_id}-{uuid.uuid4().hex[:6]}"
        conn.execute(
            """
            INSERT INTO persons
                (id, canonical_name, gender, birth_date_json, death_date_json, notes,
                 state_id, clan_name, confidence, provenance, pipeline_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'auto', ?);
            """,
            (person_id, c["canonical_name"], c["gender"], c["birth_date_json"],
             c["death_date_json"], c["notes"], c["state_id"], c["clan_name"],
             c["confidence"], pipeline_run_id),
        )
        audit_id = f"al:{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO audit_log
                (id, entity_kind, entity_id, change_kind, before_json, after_json, actor, pipeline_run_id)
            VALUES (?, 'person', ?, 'create', NULL, ?, ?, ?);
            """,
            (audit_id, person_id,
             f'{{"canonical_name": "{c["canonical_name"]}", "confidence": {c["confidence"]}}}',
             f"load@v1", pipeline_run_id),
        )
        inserted += 1
    return inserted
```

- [ ] **Step 17.4: Run, confirm pass** → **Step 17.5: Commit**:

```bash
git add pipeline/stage7_load.py tests/unit/test_stage7_load.py
git commit -m "feat(stage7): load candidate_persons → persons (simple create path)

Articles touched: none (architecture.md affects glob already includes pipeline/stage*; will add pipeline/stage7_load.py to it in Task 20 when the load surface is complete.)"
```

---

## Task 18 — Stage 7 load: variant union when matching by canonical name

**Files:**
- Modify: `pipeline/stage7_load.py`, `tests/unit/test_stage7_load.py`

- [ ] **Step 18.1: Add failing test**

```python
def test_load_matches_existing_person_by_canonical_name(tmp_path: Path) -> None:
    """Second candidate with same canonical_name should NOT create a duplicate Person."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # First load
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 0.95, 'run:1', 'chk:dzl:1:0', 'fixture');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second load with same canonical name
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:2', '重耳', 0.92, 'run:2', 'chk:dzl:1:5', 'fixture 2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        rows = list(conn.execute("SELECT id, canonical_name FROM persons;"))
    assert len(rows) == 1, f"expected 1 Person, got {len(rows)}: {rows}"
```

- [ ] **Step 18.2: Run, confirm failure**

The current impl creates a hash-suffixed id, so two `重耳` candidates produce two Persons. Test fails.

- [ ] **Step 18.3: Update `load_candidate_persons` to match-by-canonical-name**

Replace the matching logic:

```python
def load_candidate_persons(conn: sqlite3.Connection, pipeline_run_id: str) -> int:
    cur = conn.execute(
        "SELECT id, canonical_name, gender, birth_date_json, death_date_json, notes, "
        "state_id, clan_name, confidence, chunk_id, quote "
        "FROM candidate_persons WHERE pipeline_run_id = ?;",
        (pipeline_run_id,),
    )
    candidates = cur.fetchall()
    affected = 0
    for c in candidates:
        existing = conn.execute(
            "SELECT id FROM persons WHERE canonical_name = ?;",
            (c["canonical_name"],),
        ).fetchone()
        if existing is None:
            person_id = f"per:{_slugify(c['canonical_name'])}"
            _create_person(conn, person_id, c, pipeline_run_id)
        else:
            person_id = existing["id"]
            # No-op for fields in Task 18; later tasks add variant union and scalar merge.
        affected += 1
    return affected


def _create_person(conn, person_id: str, c, pipeline_run_id: str) -> None:
    conn.execute(
        """
        INSERT INTO persons
            (id, canonical_name, gender, birth_date_json, death_date_json, notes,
             state_id, clan_name, confidence, provenance, pipeline_run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'auto', ?);
        """,
        (person_id, c["canonical_name"], c["gender"], c["birth_date_json"],
         c["death_date_json"], c["notes"], c["state_id"], c["clan_name"],
         c["confidence"], pipeline_run_id),
    )
    _audit(conn, "person", person_id, "create",
           after_json=f'{{"canonical_name": "{c["canonical_name"]}", "confidence": {c["confidence"]}}}',
           actor="load@v1", pipeline_run_id=pipeline_run_id)


def _audit(conn, entity_kind, entity_id, change_kind, after_json, actor, pipeline_run_id,
           field=None, before_json=None, citation_id=None):
    conn.execute(
        """
        INSERT INTO audit_log
            (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor, citation_id, pipeline_run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (f"al:{uuid.uuid4().hex[:12]}", entity_kind, entity_id, field, change_kind,
         before_json, after_json, actor, citation_id, pipeline_run_id),
    )
```

- [ ] **Step 18.4: Run, confirm pass** → **Step 18.5: Commit**:

```bash
git add pipeline/stage7_load.py tests/unit/test_stage7_load.py
git commit -m "feat(stage7): match candidate Persons against existing by canonical_name"
```

---

## Task 19 — Stage 7 load: scalar field merge + Conflict emission

**Files:**
- Modify: `pipeline/stage7_load.py`, `tests/unit/test_stage7_load.py`

- [ ] **Step 19.1: Add failing tests**

```python
def test_load_updates_scalar_when_new_confidence_higher(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # First load: gender unset
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', NULL, 0.5, 'run:1', 'chk:dzl:1:0', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second load: gender='M', higher confidence
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:2', '重耳', 'M', 0.9, 'run:2', 'chk:dzl:1:5', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        row = conn.execute("SELECT gender FROM persons WHERE canonical_name='重耳';").fetchone()
    assert row["gender"] == "M"


def test_load_does_not_overwrite_curated(tmp_path: Path) -> None:
    """If the canonical Person is provenance='curated', re-extraction must not silently overwrite."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Pre-seed a curated Person
        conn.execute(
            "INSERT INTO persons (id, canonical_name, gender, confidence, provenance) "
            "VALUES ('per:zhong-er', '重耳', 'F', 0.99, 'curated');"
        )
        # New extraction proposes a different gender
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 'M', 0.95, 'run:1', 'chk:1', 'q');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        gender = conn.execute("SELECT gender FROM persons WHERE canonical_name='重耳';").fetchone()["gender"]
        conflicts = list(conn.execute("SELECT subject_id, field FROM conflicts;"))
    assert gender == "F", "curated value must not be silently overwritten"
    assert len(conflicts) == 1
    assert conflicts[0]["field"] == "gender"


def test_load_emits_conflict_on_disagreement_at_similar_confidence(tmp_path: Path) -> None:
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 'M', 0.85, 'run:1', 'chk:1', 'q1');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Second extraction disagrees, similar confidence
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, gender, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:2', '重耳', 'F', 0.83, 'run:2', 'chk:2', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        conflicts = list(conn.execute("SELECT field, variants_json, current_best_variant_idx FROM conflicts;"))
    assert len(conflicts) == 1
    import json as _json
    variants = _json.loads(conflicts[0]["variants_json"])
    assert {"M", "F"} == {v["value"] for v in variants}
```

- [ ] **Step 19.2: Run, confirm failure** → **Step 19.3: Implement scalar-merge logic**

Add to `pipeline/stage7_load.py`:

```python
# Confidence delta below which two values count as "similar"
_SIMILAR_CONFIDENCE_DELTA = 0.1


_SCALAR_FIELDS = ("gender", "birth_date_json", "death_date_json", "notes", "state_id", "clan_name")


def _merge_scalar_fields(conn, person_id: str, c, pipeline_run_id: str) -> None:
    existing = conn.execute(
        f"SELECT provenance, {', '.join(_SCALAR_FIELDS)}, confidence FROM persons WHERE id = ?;",
        (person_id,),
    ).fetchone()
    for field in _SCALAR_FIELDS:
        new_val = c[field]
        if new_val is None:
            continue
        old_val = existing[field]
        if old_val == new_val:
            continue
        if old_val is None:
            # First time we see a non-null value: set it, log it.
            _set_scalar(conn, person_id, field, new_val, c["confidence"], pipeline_run_id)
            continue
        if existing["provenance"] == "curated":
            _emit_conflict(conn, "person", person_id, field, old_val, existing["confidence"],
                            new_val, c["confidence"], pipeline_run_id)
            continue
        # Both auto: if new confidence beats old by a meaningful margin, update; otherwise conflict.
        if c["confidence"] > existing["confidence"] + _SIMILAR_CONFIDENCE_DELTA:
            _set_scalar(conn, person_id, field, new_val, c["confidence"], pipeline_run_id)
        else:
            _emit_conflict(conn, "person", person_id, field, old_val, existing["confidence"],
                            new_val, c["confidence"], pipeline_run_id)


def _set_scalar(conn, person_id: str, field: str, value, confidence: float, pipeline_run_id: str) -> None:
    conn.execute(
        f"UPDATE persons SET {field} = ?, updated_at = datetime('now') WHERE id = ?;",
        (value, person_id),
    )
    _audit(conn, "person", person_id, "set", field=field,
           after_json=f'{{"value": {_json_scalar(value)}, "confidence": {confidence}}}',
           actor="load@v1", pipeline_run_id=pipeline_run_id)


def _emit_conflict(conn, subject_kind, subject_id, field, old_val, old_conf, new_val, new_conf, pipeline_run_id) -> None:
    import json as _json
    variants = [
        {"value": old_val, "confidence": old_conf, "source": "existing"},
        {"value": new_val, "confidence": new_conf, "source": f"run:{pipeline_run_id}"},
    ]
    # Current best: highest confidence wins
    best_idx = 0 if old_conf >= new_conf else 1
    conn.execute(
        """
        INSERT INTO conflicts (id, subject_kind, subject_id, field, variants_json, current_best_variant_idx, resolution_rule, status)
        VALUES (?, ?, ?, ?, ?, ?, 'highest_confidence', 'open');
        """,
        (f"cfl:{uuid.uuid4().hex[:12]}", subject_kind, subject_id, field,
         _json.dumps(variants, ensure_ascii=False), best_idx),
    )


def _json_scalar(v) -> str:
    import json as _json
    return _json.dumps(v, ensure_ascii=False)
```

Update the main loop to call `_merge_scalar_fields` when matching an existing Person:

```python
        if existing is None:
            person_id = f"per:{_slugify(c['canonical_name'])}"
            _create_person(conn, person_id, c, pipeline_run_id)
        else:
            person_id = existing["id"]
            _merge_scalar_fields(conn, person_id, c, pipeline_run_id)
```

- [ ] **Step 19.4: Run, confirm pass** → **Step 19.5: Commit**

```bash
git add pipeline/stage7_load.py tests/unit/test_stage7_load.py
git commit -m "feat(stage7): scalar field merge + Conflict emission

Auto-resolution rule (highest_confidence) and curated-never-overwritten rule
from spec §7 implemented for Person scalar fields."
```

---

## Task 20 — Stage 7 load: name-variant union

**Files:**
- Modify: `pipeline/stage7_load.py`, `tests/unit/test_stage7_load.py`

- [ ] **Step 20.1: Add failing test**

```python
def test_load_unions_name_variants(tmp_path: Path) -> None:
    """A candidate that maps to an existing Person but introduces new variant kinds should add them."""
    with connect(tmp_path / "changjuan.sqlite") as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # First load: 重耳 with no variants from candidate row (variants on candidate are added separately later)
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 0.9, 'run:1', 'chk:1', 'q');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:1")
        # Stage 5 (Phase 2) will populate variant proposals; for now seed candidate_persons rows that share
        # canonical_name 晋文公 — the loader should union '晋文公' as a 谥号 variant of the same Person.
        # This requires the loader to consult an alias map. For Task 20 we use a simple rule:
        # if a new candidate's canonical_name appears in any existing person's variants AS canonical_name,
        # the candidate maps to that Person and its own canonical_name becomes a new variant.
        # Pre-seed a known variant:
        conn.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind) "
            "VALUES ('pv:1', 'per:zhong-er', '晋文公', '谥号');"
        )
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:2', '晋文公', 0.92, 'run:2', 'chk:2', 'q2');"
        )
        load_candidate_persons(conn, pipeline_run_id="run:2")
        rows = list(conn.execute("SELECT id, canonical_name FROM persons;"))
        variants = list(conn.execute("SELECT variant, kind FROM person_variants WHERE person_id='per:zhong-er';"))
    # Still one Person; '晋文公' was already a variant; no duplicate should be created.
    assert len(rows) == 1
    assert any(v["variant"] == "晋文公" for v in variants)
```

- [ ] **Step 20.2: Run, confirm failure** (the loader doesn't yet look at variants).

- [ ] **Step 20.3: Update `load_candidate_persons` matching to also consult `person_variants`**

```python
def _find_existing_person(conn, name: str) -> str | None:
    row = conn.execute("SELECT id FROM persons WHERE canonical_name = ?;", (name,)).fetchone()
    if row is not None:
        return row["id"]
    row = conn.execute("SELECT person_id FROM person_variants WHERE variant = ?;", (name,)).fetchone()
    return row["person_id"] if row else None
```

Replace the matching line in the main loop:

```python
        existing_id = _find_existing_person(conn, c["canonical_name"])
        if existing_id is None:
            person_id = f"per:{_slugify(c['canonical_name'])}"
            _create_person(conn, person_id, c, pipeline_run_id)
        else:
            person_id = existing_id
            _merge_scalar_fields(conn, person_id, c, pipeline_run_id)
```

- [ ] **Step 20.4: Run, confirm pass**

- [ ] **Step 20.5: Knowledge update + commit**

Edit `knowledge/concepts/pipeline/architecture.md` to add stage7_load.py:

```yaml
affects:
  - pipeline/config.py
  - pipeline/stage1_ingest.py
  - pipeline/stage2_chunk.py
  - pipeline/stage7_load.py
```

Append to log:

```markdown
## [2026-05-20] stage 7: load semantics — match-by-variant, scalar merge, Conflict

Stage 7 now matches incoming candidate_persons against existing canonical Persons by checking both `canonical_name` and `person_variants.variant`. On match, scalar fields are merged per spec §7: curated-never-overwritten, higher-confidence-wins-by-margin, otherwise emit Conflict. Conflict records carry both variants with their confidences and an auto-resolved `current_best_variant_idx` set by `highest_confidence`.

Articles touched: `concepts/pipeline/architecture.md` (+ stage7_load.py to affects).
```

```bash
git add pipeline/stage7_load.py tests/unit/test_stage7_load.py knowledge/concepts/pipeline/architecture.md knowledge/log.md
git commit -m "feat(stage7): variant-aware Person matching"
```

---

## Task 21 — Stage 9 export: manifest + SQLite snapshot

**Files:**
- Create: `pipeline/stage9_export.py`, `tests/unit/test_stage9_export.py`

- [ ] **Step 21.1: Write failing test**

```python
import json
import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage9_export import export_bundle


def test_export_creates_manifest_and_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "changjuan-export-test-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute("INSERT INTO persons (id, canonical_name, confidence, provenance) VALUES ('per:a', 'a', 0.9, 'auto');")
    export_bundle(src, out, version="test-v1")
    assert (out / "manifest.json").is_file()
    assert (out / "changjuan.sqlite").is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["version"] == "test-v1"
    assert manifest["counts"]["persons"] == 1


def test_export_snapshot_is_readable_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "changjuan-export-test-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(src, out, version="test-v1")
    with sqlite3.connect(out / "changjuan.sqlite") as snap:
        cur = snap.execute("SELECT name FROM sqlite_master WHERE type='table';")
        names = {r[0] for r in cur}
    assert "persons" in names
```

- [ ] **Step 21.2: Run, confirm failure** → **Step 21.3: Implement**

```python
"""Stage 9 — Freeze and export.

Produces `unroll-export-vN/` with:
- manifest.json: version, generated_at, counts per canonical table, source corpus editions
- changjuan.sqlite: read-only snapshot with candidate_* tables prefix-excluded
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_CANONICAL_TABLES = (
    "persons", "person_variants", "states", "state_capitals", "places", "events",
    "event_participants", "event_places", "event_relations",
    "person_relations", "person_states", "entity_citations",
    "conflicts", "audit_log", "pipeline_runs", "merge_candidates", "qa_samples",
)
SCHEMA_VERSION = 1


def export_bundle(src_db: Path, out_dir: Path, *, version: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    snap_path = out_dir / "changjuan.sqlite"
    _snapshot_canonical_only(src_db, snap_path)

    counts = _count_rows(snap_path)
    manifest = {
        "version": version,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "source_corpus_editions": _source_editions(src_db),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def _snapshot_canonical_only(src_db: Path, snap_path: Path) -> None:
    if snap_path.exists():
        snap_path.unlink()
    # Copy file then drop candidate_* tables. Simpler than building from scratch and preserves indexes/views.
    shutil.copyfile(src_db, snap_path)
    with sqlite3.connect(snap_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")  # we're about to drop tables
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';")
        for (name,) in cur.fetchall():
            conn.execute(f"DROP TABLE IF EXISTS {name};")
        # Also drop llm_cache (an implementation detail of extraction, not part of the export contract)
        conn.execute("DROP TABLE IF EXISTS llm_cache;")
        conn.execute("VACUUM;")


def _count_rows(snap_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(snap_path) as conn:
        for t in _CANONICAL_TABLES:
            row = conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()
            counts[t] = row[0]
    return counts


def _source_editions(src_db: Path) -> dict[str, str]:
    """Pull `source_edition` strings from the corpus.sqlite documents table if present.

    For v1, we look in a corpus.sqlite next to src_db; if absent, return empty.
    """
    corpus_db = src_db.parent / "corpus.sqlite"
    if not corpus_db.exists():
        return {}
    with sqlite3.connect(corpus_db) as conn:
        rows = conn.execute("SELECT corpus, MAX(source_edition) FROM documents GROUP BY corpus;").fetchall()
    return {corpus: edition for corpus, edition in rows}
```

- [ ] **Step 21.4: Run, confirm pass** → **Step 21.5: Commit**

```bash
git add pipeline/stage9_export.py tests/unit/test_stage9_export.py
git commit -m "feat(stage9): export bundle (manifest + canonical-only sqlite snapshot)"
```

---

## Task 22 — Stage 9 export: assert no candidate_* tables in snapshot

**Files:**
- Modify: `tests/unit/test_stage9_export.py`

- [ ] **Step 22.1: Add the assertion test**

```python
def test_export_strips_all_candidate_tables(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "x-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Seed a candidate_persons row so the table is non-empty in src
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', 'x', 0.5, 'r', 'c', 'q');"
        )
    export_bundle(src, out, version="x-v1")
    with sqlite3.connect(out / "changjuan.sqlite") as snap:
        cur = snap.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';")
        leaked = [r[0] for r in cur]
    assert leaked == [], f"export leaked candidate tables: {leaked}"


def test_export_strips_llm_cache(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "x-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(src, out, version="x-v1")
    with sqlite3.connect(out / "changjuan.sqlite") as snap:
        cur = snap.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_cache';")
        assert cur.fetchone() is None
```

- [ ] **Step 22.2: Run, confirm pass** (impl already handles this)

- [ ] **Step 22.3: Commit**

```bash
git add tests/unit/test_stage9_export.py
git commit -m "test(stage9): assert no candidate_* or llm_cache tables in export"
```

---

## Task 23 — Stage 9 export: round-trip test

**Files:**
- Modify: `tests/unit/test_stage9_export.py`

- [ ] **Step 23.1: Add round-trip test**

```python
def test_export_roundtrip_preserves_canonical_data(tmp_path: Path) -> None:
    """Load export bundle into a fresh sqlite handle; counts and key rows must match source."""
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "rt-v1"
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute("INSERT INTO persons (id, canonical_name, confidence, provenance) VALUES ('per:a', 'a', 0.9, 'auto');")
        conn.execute("INSERT INTO persons (id, canonical_name, confidence, provenance) VALUES ('per:b', 'b', 0.5, 'curated');")
        conn.execute("INSERT INTO events (id, type, confidence, provenance) VALUES ('evt:1', 'battle', 0.8, 'auto');")
    export_bundle(src, out, version="rt-v1")

    # Fresh handle on the snapshot
    with sqlite3.connect(out / "changjuan.sqlite") as snap:
        persons = list(snap.execute("SELECT id, canonical_name, provenance FROM persons ORDER BY id;"))
        events = list(snap.execute("SELECT id, type FROM events;"))
    assert [r[0] for r in persons] == ["per:a", "per:b"]
    assert [r[2] for r in persons] == ["auto", "curated"]
    assert events == [("evt:1", "battle")]

    # Manifest counts agree with snapshot reality
    import json as _json
    manifest = _json.loads((out / "manifest.json").read_text())
    assert manifest["counts"]["persons"] == 2
    assert manifest["counts"]["events"] == 1
```

- [ ] **Step 23.2: Run, confirm pass** → **Step 23.3: Commit**

```bash
git add tests/unit/test_stage9_export.py
git commit -m "test(stage9): export round-trip preserves canonical data"
```

---

## Task 24 — Stage 9 export: knowledge update

**Files:**
- Modify: `knowledge/concepts/pipeline/architecture.md`, `knowledge/log.md`

- [ ] **Step 24.1: Update architecture article's affects glob**

Edit `knowledge/concepts/pipeline/architecture.md` to add the stage9 file:

```yaml
affects:
  - pipeline/config.py
  - pipeline/stage1_ingest.py
  - pipeline/stage2_chunk.py
  - pipeline/stage7_load.py
  - pipeline/stage9_export.py
```

Optionally add an `export-contract` paragraph at the bottom of the body, or split it into its own article. For Phase 1 keep it in architecture.md.

- [ ] **Step 24.2: Log entry**

```markdown
## [2026-05-20] stage 9: export bundle + round-trip test

`pipeline.stage9_export.export_bundle(src, out, version=...)` produces `out/manifest.json` and `out/changjuan.sqlite`. The snapshot is built by copy-then-drop: `candidate_*` tables and `llm_cache` are stripped via `name LIKE 'candidate_%'` enumeration (fail-loud if a future schema change adds a candidate table — no allowlist to forget). Manifest carries `version`, `schema_version`, `generated_at`, per-table counts, and source-corpus editions pulled from `corpus.sqlite.documents.source_edition`. Round-trip test confirms canonical rows survive intact.

Articles touched: `concepts/pipeline/architecture.md` (+ stage9_export.py to affects).
```

- [ ] **Step 24.3: Commit**

```bash
git add knowledge/concepts/pipeline/architecture.md knowledge/log.md
git commit -m "docs: living-docs update for stage 9 export contract"
```

---

## Task 25 — LLM cache stub (Phase 2 placeholder)

**Files:**
- Create: `pipeline/llm_cache.py`, `tests/unit/test_llm_cache.py`

- [ ] **Step 25.1: Write failing test**

```python
import hashlib
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.llm_cache import cache_key, get, put
from pipeline.schemas import CANONICAL_SCHEMA


def test_cache_key_is_stable() -> None:
    k1 = cache_key(model="claude-sonnet", prompt_template_version="v1", request={"prompt": "hi"})
    k2 = cache_key(model="claude-sonnet", prompt_template_version="v1", request={"prompt": "hi"})
    k3 = cache_key(model="claude-sonnet", prompt_template_version="v2", request={"prompt": "hi"})
    assert k1 == k2
    assert k1 != k3


def test_put_then_get_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        key = cache_key(model="m", prompt_template_version="v", request={"x": 1})
        put(conn, key, model="m", prompt_template_version="v", request={"x": 1}, response={"ok": True})
        got = get(conn, key)
    assert got == {"ok": True}


def test_get_miss_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "changjuan.sqlite"
    with connect(db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        assert get(conn, "nope") is None
```

- [ ] **Step 25.2: Run, confirm failure** → **Step 25.3: Implement**

```python
"""LLM response cache — keyed by (model, prompt_template_version, normalized request JSON).

Phase 1 builds the cache primitives without any LLM client. Phase 2 (stage 3
extraction) wires the cache around its calls.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid


def cache_key(*, model: str, prompt_template_version: str, request: dict) -> str:
    payload = json.dumps(
        {"model": model, "pv": prompt_template_version, "req": request},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def put(conn: sqlite3.Connection, key: str, *, model: str, prompt_template_version: str,
        request: dict, response: dict, tokens_in: int = 0, tokens_out: int = 0,
        cost_usd: float = 0.0) -> None:
    conn.execute(
        """
        INSERT INTO llm_cache
            (id, key_hash, model, prompt_template_version, request_json, response_json, tokens_in, tokens_out, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (key_hash) DO NOTHING;
        """,
        (f"lc:{uuid.uuid4().hex[:12]}", key, model, prompt_template_version,
         json.dumps(request, ensure_ascii=False, sort_keys=True),
         json.dumps(response, ensure_ascii=False, sort_keys=True),
         tokens_in, tokens_out, cost_usd),
    )


def get(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute("SELECT response_json FROM llm_cache WHERE key_hash = ?;", (key,)).fetchone()
    if row is None:
        return None
    return json.loads(row["response_json"])
```

- [ ] **Step 25.4: Run, confirm pass** → **Step 25.5: Commit**

```bash
git add pipeline/llm_cache.py tests/unit/test_llm_cache.py
git commit -m "feat(pipeline): LLM cache primitives (no LLM client yet)"
```

---

## Task 26 — CLI scaffold (typer)

**Files:**
- Create: `pipeline/cli.py`, `tests/unit/test_cli.py`

- [ ] **Step 26.1: Write failing test**

```python
from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app


def test_cli_has_ingest_chunk_load_export_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "chunk", "load", "export"):
        assert cmd in result.stdout


def test_cli_ingest_dry_runs(tmp_path: Path, monkeypatch) -> None:
    """Smoke-test: invoking `changjuan ingest` with --repo-root pointing at an empty tmp dir
    should exit cleanly with 'no corpora found' rather than crash."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", "--repo-root", str(tmp_path)])
    # Either exits 0 with a "no corpora" message, or exits 1 with a clear error — both acceptable; crash is not.
    assert result.exit_code in (0, 1)
    assert "Traceback" not in result.stdout
```

- [ ] **Step 26.2: Run, confirm failure** → **Step 26.3: Implement**

```python
"""changjuan CLI — typer-based entry point.

Exposes one subcommand per pipeline stage that has a stable user-facing surface.
Phase 1 wires ingest / chunk / load / export.
"""
from __future__ import annotations

from pathlib import Path

import structlog
import typer

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi
from pipeline.stage2_chunk import chunk_documents
from pipeline.stage7_load import load_candidate_persons
from pipeline.stage9_export import export_bundle


app = typer.Typer(help="changjuan — Eastern-Zhou knowledge graph pipeline.")
log = structlog.get_logger()


def _cfg(repo_root: Path | None) -> Config:
    return Config(repo_root=repo_root) if repo_root else Config()


@app.command()
def ingest(repo_root: Path | None = typer.Option(None, help="Override the repo root.")) -> None:
    """Stage 1: read source corpora into corpus.sqlite."""
    cfg = _cfg(repo_root)
    src = cfg.corpora_dir / "dongzhoulieguozhi" / "json" / "东周列国志.json"
    if not src.exists():
        typer.echo(f"no corpora found at {src}", err=True)
        raise typer.Exit(code=1)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = ingest_dongzhoulieguozhi(conn, cfg)
    typer.echo(f"ingested {n} chapters into {cfg.corpus_db}")


@app.command()
def chunk(repo_root: Path | None = typer.Option(None)) -> None:
    """Stage 2: split documents into overlapping paragraph-aware chunks."""
    cfg = _cfg(repo_root)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = chunk_documents(conn, cfg)
    typer.echo(f"wrote {n} chunks into {cfg.corpus_db}")


@app.command()
def load(
    pipeline_run_id: str = typer.Argument(..., help="Pipeline run id to promote (matches candidate_persons.pipeline_run_id)."),
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 7: promote candidates → canonical with field-level merge."""
    cfg = _cfg(repo_root)
    with connect(cfg.canonical_db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        n = load_candidate_persons(conn, pipeline_run_id=pipeline_run_id)
    typer.echo(f"loaded {n} candidate_persons rows under pipeline_run_id={pipeline_run_id}")


@app.command()
def export(
    version: str = typer.Argument(..., help="Export bundle version label (e.g., 2026-05-v1)."),
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 9: freeze a versioned export bundle."""
    cfg = _cfg(repo_root)
    out_dir = cfg.exports_dir / f"changjuan-export-{version}"
    export_bundle(cfg.canonical_db, out_dir, version=version)
    typer.echo(f"export bundle written to {out_dir}")
```

- [ ] **Step 26.4: Run, confirm pass** → **Step 26.5: Knowledge update + commit**

Add new article `knowledge/concepts/runtime/cli.md`:

```markdown
---
title: changjuan CLI commands
type: concept
area: runtime
updated: 2026-05-20
status: thin
load_bearing: false
references:
  - concepts/pipeline/architecture.md
affects:
  - pipeline/cli.py
---

## What this is

The `changjuan` command is a typer-based CLI exposing one subcommand per pipeline stage that has a stable user-facing surface. Phase 1 wires `ingest`, `chunk`, `load`, `export`. Stages without a CLI verb (3 extract, 5 link, 6 canon-check) get one as their phase plans land.

## Why this shape, not the alternatives

A single `changjuan run` mega-command was considered and rejected — it would hide the cost profile of each stage and make resumption harder. Separate subcommands match the stage-checkpointed pipeline model directly.

## What would invalidate this article

- A stage acquiring more than one user-facing verb (e.g., separate `link` and `link-rescue`).
- The pipeline becoming agentic (one command, no stages).

## First commitments

- All commands take `--repo-root` to allow non-cwd execution (testing, multiple checkouts).
- `load` takes a required `pipeline_run_id` positional — promotion is always scoped to a specific extraction batch.
- `export` takes a required `version` positional — export bundles are always versioned at the bundle dirname.
```

Update `knowledge/index.md` to add a `runtime` area listing this article.

Append log entry, then commit:

```bash
git add pipeline/cli.py tests/unit/test_cli.py knowledge/concepts/runtime/cli.md knowledge/index.md knowledge/log.md
git commit -m "feat(cli): typer-based changjuan ingest/chunk/load/export"
```

---

## Task 27 — End-to-end round-trip integration test

**Files:**
- Create: `tests/integration/test_roundtrip.py`

- [ ] **Step 27.1: Write the test**

```python
"""End-to-end Phase 1 integration test.

Walks the deterministic pipeline: ingest a tiny synthetic corpus → chunk → seed a
synthetic candidate_persons row → load → export. Asserts the export bundle has
the expected data and no candidate tables. This is the regression target for the
Phase 1 build sequence.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi
from pipeline.stage2_chunk import chunk_documents
from pipeline.stage7_load import load_candidate_persons
from pipeline.stage9_export import export_bundle


def _seed_fake_corpus(corpora_dir: Path) -> None:
    repo = corpora_dir / "dongzhoulieguozhi" / "json"
    repo.mkdir(parents=True)
    (repo / "东周列国志.json").write_text(
        json.dumps({
            "title": "东周列国志",
            "chapters": [
                {"title": "第一回　test", "content": "para 1 about 重耳.\n\npara 2 about 晋."},
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_phase1_roundtrip(tmp_path: Path) -> None:
    cfg = Config(repo_root=tmp_path)
    _seed_fake_corpus(cfg.corpora_dir)

    # 1. Ingest
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n_docs = ingest_dongzhoulieguozhi(conn, cfg)
    assert n_docs == 1

    # 2. Chunk
    with connect(cfg.corpus_db) as conn:
        n_chunks = chunk_documents(conn, cfg)
    assert n_chunks >= 1

    # 3. Load synthetic candidates (Phase 2 will produce these from LLM; Phase 1 fakes them)
    with connect(cfg.canonical_db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        conn.execute(
            "INSERT INTO candidate_persons (id, canonical_name, confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES ('cper:1', '重耳', 0.9, 'run:1', 'chk:dzl:1:0', 'para 1 about 重耳');"
        )
        n_loaded = load_candidate_persons(conn, pipeline_run_id="run:1")
    assert n_loaded == 1

    # 4. Export
    out = cfg.exports_dir / "changjuan-export-rt-v1"
    export_bundle(cfg.canonical_db, out, version="rt-v1")

    # Bundle assertions
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["counts"]["persons"] == 1
    assert "audit_log" in manifest["counts"]
    with sqlite3.connect(out / "changjuan.sqlite") as snap:
        leaked = list(snap.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';"))
        person_name = snap.execute("SELECT canonical_name FROM persons;").fetchone()[0]
    assert leaked == []
    assert person_name == "重耳"
```

- [ ] **Step 27.2: Run, confirm pass**

```
uv run pytest tests/integration/test_roundtrip.py -v
```

Expected: 1 passed.

- [ ] **Step 27.3: Run the full test suite as a final gate**

```
uv run pytest -v
```

Expected: all tests green.

- [ ] **Step 27.4: Knowledge update + Phase-1-done log entry**

Append to `knowledge/log.md`:

```markdown
## [2026-05-20] Phase 1 complete — deterministic foundation in place

The full deterministic ETL skeleton wires end-to-end. `tests/integration/test_roundtrip.py` exercises: ingest → chunk → seed synthetic candidates → load (with field-level merge semantics) → export (manifest + canonical-only snapshot). The pipeline is ready for stage 3 (LLM extraction) in Phase 2.

Tables in `changjuan.sqlite`: persons, person_variants, states, state_capitals, places, events, event_participants, event_places, event_relations, person_relations, person_states, entity_citations, candidate_* (9 staging tables), conflicts, audit_log, pipeline_runs, llm_cache, merge_candidates, qa_samples. Plus the `field_history` view.

CLI verbs working: `changjuan ingest`, `changjuan chunk`, `changjuan load <pipeline_run_id>`, `changjuan export <version>`.

Articles updated this phase: knowledge-graph.md, architecture.md, dates-and-reigns.md (new), cli.md (new), with affects globs covering every file in `pipeline/`.

Next phase: golden-chapter annotation + stage 3 extraction prompt + LLM client + sampling QA harness.
```

- [ ] **Step 27.5: Commit**

```bash
git add tests/integration/test_roundtrip.py knowledge/log.md
git commit -m "test(integration): Phase 1 round-trip — ingest → chunk → load → export"
```

---

## Phase 1 acceptance check

Before declaring Phase 1 done, run all of:

- [ ] `uv run pytest -v` — all tests green
- [ ] `uv run pre-commit run --all-files` — clean
- [ ] `./scripts/validate-articles` — `✅ All N article(s) have valid frontmatter.`
- [ ] `./scripts/drift-check` (with no staged changes) — clean
- [ ] `git log --oneline` — clean linear history; each commit has either an article touch or `no knowledge impact: <reason>` in the body
- [ ] `changjuan ingest && changjuan chunk` against the real 108-chapter corpus produces `data/corpus.sqlite` with 108 documents and N chunks
- [ ] `changjuan load run:test && changjuan export 2026-05-phase1-smoke` against a synthetic candidate produces a non-empty export bundle

If any check fails, treat as a Phase 1 task and fix before opening Plan 2 (golden + extraction).
