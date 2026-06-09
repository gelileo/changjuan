# Factory `prices` passthrough — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thread an optional per-book `prices` map from `book-meta.json` through `export_bundle`'s `manifest.json` into `publish_depot`'s catalog entry, omitting the key when a book is free.

**Architecture:** Two independent hops, each gated on presence. `stage9_export.export_bundle` validates `book_meta["prices"]` and adds `manifest["prices"]` only when non-empty; `publish_depot.build_entry` copies `prices` into the catalog entry only when the manifest has it. Free books carry no `prices` key — matching the reader's "absent → free" contract.

**Tech Stack:** Python 3.12, pytest, ruff/ruff-format/mypy, Typer; Living-Docs drift-check pre-commit hook (maps changed `pipeline/*.py` → a `knowledge/concepts/**` article via `affects:` frontmatter and **blocks the commit unless that article is staged too**).

**Design spec:** `docs/superpowers/specs/2026-06-09-factory-prices-passthrough-design.md`

---

## Critical: the drift-check pre-commit hook

Each task changes a `pipeline/*.py` file whose `affects:` glob maps to a knowledge article. The commit will **fail** unless the article is staged in the same commit:

- `pipeline/stage9_export.py` → `knowledge/concepts/pipeline/export-contract.md` (Task 1)
- `pipeline/publish_depot.py` → `knowledge/concepts/pipeline/depot.md` (Task 2)

Each task's commit also appends an entry to `knowledge/log.md`. Do NOT defer the knowledge edits — they are part of the same commit.

---

## Task 1: `validate_prices` + manifest emission

**Files:**
- Modify: `pipeline/stage9_export.py`
- Test: `tests/unit/test_stage9_export.py`
- Docs (same commit): `knowledge/concepts/pipeline/export-contract.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing tests**

At the top of `tests/unit/test_stage9_export.py`, add `import pytest` (the file uses bare `assert` today) and import `validate_prices`:

```python
import pytest
from pipeline.stage9_export import export_bundle, validate_prices
```

(Merge the `validate_prices` import into the existing `from pipeline.stage9_export import export_bundle` line.)

Append these tests to the file:

```python
def test_validate_prices_none_and_empty_are_free() -> None:
    assert validate_prices(None) is None
    assert validate_prices({}) is None


def test_validate_prices_returns_normalized_map() -> None:
    assert validate_prices({"CNY": 18, "USD": 2.99}) == {"CNY": 18, "USD": 2.99}


def test_validate_prices_rejects_unknown_currency() -> None:
    with pytest.raises(ValueError):
        validate_prices({"EUR": 5})


def test_validate_prices_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        validate_prices({"CNY": 0})
    with pytest.raises(ValueError):
        validate_prices({"USD": -1})


def test_validate_prices_rejects_nonnumber() -> None:
    with pytest.raises(ValueError):
        validate_prices({"USD": "18"})
    with pytest.raises(ValueError):
        validate_prices({"USD": True})  # bool is an int subclass — must be rejected


def test_export_includes_prices_when_present(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "p1"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    meta = {**_MINIMAL_BOOK_META, "prices": {"CNY": 18, "USD": 2.99}}
    export_bundle(
        src, out, version="v1", corpus_db=corpus, book_meta=meta,
        readable_dir=tmp_path / "readable",
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["prices"] == {"CNY": 18, "USD": 2.99}


def test_export_omits_prices_when_absent(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "p2"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    export_bundle(
        src, out, version="v1", corpus_db=corpus, book_meta=_MINIMAL_BOOK_META,
        readable_dir=tmp_path / "readable",
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert "prices" not in manifest


def test_export_rejects_malformed_prices(tmp_path: Path) -> None:
    src = tmp_path / "changjuan.sqlite"
    out = tmp_path / "exports" / "p3"
    corpus = _empty_corpus(tmp_path)
    with connect(src) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    meta = {**_MINIMAL_BOOK_META, "prices": {"EUR": 5}}
    with pytest.raises(ValueError):
        export_bundle(
            src, out, version="v1", corpus_db=corpus, book_meta=meta,
            readable_dir=tmp_path / "readable",
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_stage9_export.py -q`
Expected: FAIL — `cannot import name 'validate_prices'` (collection error) until Step 3.

- [ ] **Step 3: Add `validate_prices` + thread it into the manifest**

In `pipeline/stage9_export.py`, add this near the top of the module (after the imports, before `export_bundle`):

```python
PRICE_CURRENCIES = ("CNY", "USD")


def validate_prices(raw: object) -> dict[str, float] | None:
    """Normalize a book-meta `prices` value for the manifest.

    Returns None when absent/empty (the book is free). Raises ValueError on a
    malformed map: an unknown currency, or an amount that is not a positive
    number. Currencies are limited to what the reader resolves (CNY/USD).
    """
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"prices must be an object, got {type(raw).__name__}")
    out: dict[str, float] = {}
    for cur, amt in raw.items():
        if cur not in PRICE_CURRENCIES:
            raise ValueError(f"unsupported price currency {cur!r}; allowed: {PRICE_CURRENCIES}")
        if isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt <= 0:
            raise ValueError(f"price for {cur} must be a positive number, got {amt!r}")
        out[cur] = amt
    return out
```

Then in `export_bundle`, immediately after the `manifest` dict is constructed and **before** the `(out_dir / "manifest.json").write_text(...)` call, insert:

```python
    prices = validate_prices(book_meta.get("prices"))
    if prices:
        manifest["prices"] = prices
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_stage9_export.py -q`
Expected: PASS (all existing + 8 new tests green).

- [ ] **Step 5: Update the knowledge article (required by drift-check)**

In `knowledge/concepts/pipeline/export-contract.md`, under the `## manifest.json contents` section, document the new optional field. Add a short paragraph stating: `manifest.json` carries an optional `prices` object (e.g. `{"CNY": 18, "USD": 2.99}`) sourced from `book-meta.json`, validated by `validate_prices` (currencies limited to CNY/USD; each amount a positive number; malformed input fails the export with `ValueError`); the key is **omitted entirely for free books** (no `prices: null`), matching the reader's "absent → free" contract. Bump the `updated:` frontmatter date to `2026-06-09`.

- [ ] **Step 6: Append a `knowledge/log.md` entry**

Append a dated entry following the existing format at the end of `knowledge/log.md`, e.g.:

```markdown
## 2026-06-09 — factory prices passthrough (manifest)

Added optional `prices` to manifest.json via `validate_prices` in
`stage9_export.py` (CNY/USD, positive, omitted when free).

Articles touched: concepts/pipeline/export-contract.md.
```

- [ ] **Step 7: Commit (drift-check + ruff + mypy run here)**

```bash
git add pipeline/stage9_export.py tests/unit/test_stage9_export.py knowledge/concepts/pipeline/export-contract.md knowledge/log.md
git commit -m "feat(export): optional prices in manifest, validated + omitted when free"
```
Expected: the pre-commit hook's Living-Docs drift check passes (export-contract.md is staged); ruff/ruff-format/mypy pass. If drift-check fails complaining the article isn't updated, confirm `export-contract.md` is staged.

---

## Task 2: catalog entry passthrough

**Files:**
- Modify: `pipeline/publish_depot.py`
- Test: `tests/unit/test_publish_depot.py`
- Docs (same commit): `knowledge/concepts/pipeline/depot.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_publish_depot.py` (it already imports `build_entry`):

```python
def _full_manifest(**extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "book_id": "x",
        "slug": "x",
        "title": "X",
        "author": "—",
        "edition": None,
        "cover": None,
        "capabilities": ["cast"],
        "schema_version": 6,
        "counts": {"persons": 1},
        "version": "v1",
    }
    base.update(extra)
    return base


def test_build_entry_carries_prices_when_present() -> None:
    entry = build_entry(
        _full_manifest(prices={"CNY": 18, "USD": 2.99}),
        bundle_path="books/x/x-v1.sqlite", bytes_=10, sha256="abc",
    )
    assert entry["prices"] == {"CNY": 18, "USD": 2.99}


def test_build_entry_omits_prices_when_absent() -> None:
    entry = build_entry(
        _full_manifest(), bundle_path="books/x/x-v1.sqlite", bytes_=10, sha256="abc",
    )
    assert "prices" not in entry
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_publish_depot.py -q`
Expected: FAIL — `test_build_entry_carries_prices_when_present` errors with `KeyError: 'prices'` (entry has no such key yet).

- [ ] **Step 3: Add the conditional passthrough in `build_entry`**

In `pipeline/publish_depot.py`, inside `build_entry`, after `entry["language"] = manifest.get("language", "zh-CN")` and **before** `entry["bundle"] = {...}`, insert:

```python
    if manifest.get("prices"):
        entry["prices"] = manifest["prices"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_publish_depot.py -q`
Expected: PASS (existing + 2 new tests green).

- [ ] **Step 5: Update the knowledge article (required by drift-check)**

In `knowledge/concepts/pipeline/depot.md`, under `## Catalog contract`, add a sentence: a catalog entry carries an optional `prices` object (CNY/USD), passed through from the manifest **only when present** (free books omit it) — the reader treats an absent `prices` as free. (If the article has an `updated:` frontmatter field, bump it to `2026-06-09`; the current frontmatter shown has none — add nothing if absent.)

- [ ] **Step 6: Append a `knowledge/log.md` entry**

Append:

```markdown
## 2026-06-09 — factory prices passthrough (catalog)

`publish_depot.build_entry` now copies `prices` from the manifest into the
catalog entry when present (omitted for free books).

Articles touched: concepts/pipeline/depot.md.
```

- [ ] **Step 7: Commit**

```bash
git add pipeline/publish_depot.py tests/unit/test_publish_depot.py knowledge/concepts/pipeline/depot.md knowledge/log.md
git commit -m "feat(depot): pass prices from manifest into catalog entry when present"
```
Expected: drift-check (depot.md staged) + ruff/ruff-format/mypy pass.

---

## Final verification (coordinator)

- [ ] `pytest -q` — full suite green.
- [ ] `ruff check . && ruff format --check . && mypy pipeline` (or the project's configured commands) — clean.
- [ ] `git log --oneline main..HEAD` shows the spec + 2 implementation commits.
- [ ] Manual sanity (optional): a `book-meta.json` with `"prices": {"CNY": 18, "USD": 2.99}` → after `export` its `manifest.json` has `prices`; after `publish-depot` the catalog entry has `prices`. (No real book is priced as part of this change — dzl stays free.)
