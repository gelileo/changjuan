# Factory `prices` passthrough (design)

**Date:** 2026-06-09
**Status:** designed (not yet implemented)
**Scope:** changjuan factory (Python ETL). Thread an optional per-book `prices`
map from the hand-authored `book-meta.json` source, through `export_bundle`'s
`manifest.json`, into `publish_depot`'s catalog entry — so a paid book's
localized price reaches the reader's already-shipped purchase UI. Pure plumbing:
no real book is priced here, no payment processing, no reader change.

---

## 1. Problem

The reader's purchase feature (sub-project C, shipped) reads an optional
`prices?: { CNY?: number; USD?: number }` off each catalog entry; **absent/empty
means free**. Its tests use a fixture catalog where a paid book carries
`{ CNY: 18, USD: 2.99 }` and a free book carries no `prices` key. But the
**factory cannot yet produce that field** — `prices` exists in neither
`book-meta.json`, `manifest.json`, nor the depot `catalog.json`. So every real
book the factory publishes is unconditionally free. This change adds the missing
passthrough.

## 2. Code reality (grounding — verified against `main`)

The book-metadata flow is three hops, none carrying `prices`:

1. **Source:** `data/books/<book_id>/book-meta.json` — today: `book_id`, `slug`,
   `title`, `author`, `edition`, `cover`, `capabilities` (dzl's example has
   exactly these).
2. **`pipeline/stage9_export.py` `export_bundle(...)`** builds `manifest.json` by
   copying specific `book_meta` fields into a dict literal (`book_id`, `slug`,
   `title`, `author`, `edition`, `cover`, `capabilities`) plus `version`,
   `schema_version` (`SCHEMA_VERSION`), `generated_at`, `counts`,
   `source_corpus_editions`. `book_meta` is loaded from `book-meta.json` by
   `pipeline/cli.py` and passed in.
3. **`pipeline/publish_depot.py` `build_entry(manifest, *, bundle_path, bytes_,
   sha256)`** builds the catalog entry as `{k: manifest.get(k) for k in
   _MANIFEST_FIELDS}` (whitelist: `book_id, slug, title, author, edition, cover,
   capabilities, schema_version, counts, version`) + `language` (default
   `"zh-CN"`) + a `bundle` descriptor. The module docstring states the invariant:
   *"the catalog entry IS the book's manifest plus a `bundle` descriptor."*

Reader contract (consumer, already shipped): `src/depot/pricing.ts`
`resolvePrice(prices, region)` returns `null` (→ free) when `prices` is
absent/empty; otherwise picks the region's currency (`currencyForRegion` yields
only `CNY`/`USD`), falling back to `USD` then any present entry.

## 3. Approach (chosen: thread through, omit when absent)

Add `prices` as an optional field at each hop, **emitting the key only when the
book actually has prices**. Free books' manifests and catalog entries have no
`prices` key — matching the reader's fixture shape and the "absent → free"
contract exactly. (Rejected: forcing `prices` into the `_MANIFEST_FIELDS`
whitelist, which would emit a noisy `"prices": null` on every free book — a shape
not present in the fixture. Rejected: writing `prices` into the catalog entry
directly from book-meta, bypassing the manifest — breaks the "entry = manifest +
bundle" invariant.)

## 4. Changes

### 4a. `book-meta.json` (source, per book)
Optional `prices` object, e.g.:

```json
{ "book_id": "x", "...": "...", "prices": { "CNY": 18, "USD": 2.99 } }
```

A free book omits `prices` entirely. **dzl's `data/books/dzl/book-meta.json` is
left unchanged** (the bundled flagship stays free). No real book is priced in
this change.

### 4b. `pipeline/stage9_export.py`
Add a pure module-level validator and thread the result into the manifest:

```python
PRICE_CURRENCIES = ("CNY", "USD")

def validate_prices(raw: object) -> dict[str, float] | None:
    """Normalize a book-meta `prices` value. Returns None when absent/empty (free).
    Raises ValueError on a malformed map (unknown currency, non-positive, non-number)."""
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

In `export_bundle`, after the `manifest` dict is built and before it is written,
conditionally add the key:

```python
prices = validate_prices(book_meta.get("prices"))
if prices:
    manifest["prices"] = prices
```

(`isinstance(amt, bool)` guard rejects `True`/`False`, which are `int` subclasses
in Python.)

### 4c. `pipeline/publish_depot.py`
Leave `_MANIFEST_FIELDS` unchanged. In `build_entry`, after the whitelist copy
and `language` default, before assigning `bundle`:

```python
if manifest.get("prices"):
    entry["prices"] = manifest["prices"]
```

So the catalog entry carries `prices` only for paid books.

## 5. Testing

- **`tests/unit/test_stage9_export.py`:**
  - `book_meta` with valid `prices` → written `manifest["prices"] == {"CNY": 18, "USD": 2.99}`.
  - `book_meta` without `prices` → `"prices" not in manifest`.
  - `book_meta` with malformed prices (unknown currency `"EUR"`; amount `0`/negative; amount `"18"`) → `export_bundle` raises `ValueError`.
- **`tests/unit/test_stage9_export.py` (direct):** `validate_prices` returns `None`
  for `None`/`{}`; returns the normalized dict for a valid map; raises for each
  malformed case (mirrors the above without the sqlite build).
- **`tests/unit/test_publish_depot.py`:** `build_entry` includes `prices` when the
  manifest has it; omits `prices` when the manifest lacks it.
- Existing `pytest` suite, `ruff`/`ruff-format`/`mypy`, and the drift-check stay green.

## 6. Knowledge (same-task, per Living Docs)

- `knowledge/concepts/pipeline/export-contract.md` — document the manifest's
  optional `prices` (sourced from `book-meta.json`; `validate_prices` rule:
  CNY/USD only, positive numbers; omitted when free).
- `knowledge/concepts/pipeline/depot.md` — note the catalog entry passes `prices`
  through when present (the "entry = manifest + bundle" invariant now includes the
  optional `prices`).
- Append a `knowledge/log.md` entry listing the touched articles.

## 7. Out of scope

- Real payment processing / receipts / any backend (the reader's `purchaseBook`
  is a stub).
- Setting an actual price on dzl or any real book (plumbing only).
- Any reader change — it already consumes `prices`.
- Currencies beyond CNY/USD (the reader resolves only those); adding a third would
  be a coordinated reader+factory change.
- A live-FX / single-base-price model — prices are explicit per-currency, matching
  the reader's design.
