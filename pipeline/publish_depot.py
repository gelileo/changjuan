"""Publish an export bundle into the changjuan-depot repo (sub-project B1).

Copies an export's single-file graph.sqlite into the depot as
books/<book_id>/<book_id>-<version>.sqlite and writes/merges catalog.json.
The catalog entry IS the book's manifest plus a `bundle` descriptor, so the
reader (B2) needs no separate manifest fetch.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CATALOG_SCHEMA = 1
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/gelileo/changjuan-depot/main/"
# Manifest fields copied verbatim into a catalog entry.
_MANIFEST_FIELDS = (
    "book_id",
    "slug",
    "title",
    "author",
    "edition",
    "cover",
    "capabilities",
    "schema_version",
    "counts",
    "version",
)


def sha256_file(path: Path) -> str:
    """Streamed SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_entry(
    manifest: dict[str, Any], *, bundle_path: str, bytes_: int, sha256: str
) -> dict[str, Any]:
    """Catalog entry = manifest fields (+ language default) + bundle descriptor."""
    entry: dict[str, Any] = {k: manifest.get(k) for k in _MANIFEST_FIELDS}
    entry["language"] = manifest.get("language", "zh-CN")
    entry["bundle"] = {"path": bundle_path, "bytes": bytes_, "sha256": sha256}
    return entry


def upsert_catalog(
    catalog: dict[str, Any], entry: dict[str, Any], generated_at: str
) -> dict[str, Any]:
    """Pure: replace the entry for entry['book_id'] (or append), sorted by book_id."""
    books: list[dict[str, Any]] = [
        b for b in catalog.get("books", []) if b.get("book_id") != entry["book_id"]
    ]
    books.append(entry)
    books.sort(key=lambda b: b["book_id"])
    return {
        "catalog_schema": CATALOG_SCHEMA,
        "generated_at": generated_at,
        "source": catalog.get("source") or {"name": "changjuan depot", "baseUrl": DEFAULT_BASE_URL},
        "books": books,
    }


def publish_book(
    export_dir: Path, depot_dir: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    """Copy export_dir/graph.sqlite into the depot as a single-file bundle and
    write/merge depot_dir/catalog.json. Returns the updated catalog dict.

    Idempotent per (book_id, version): re-publishing overwrites the bundle file
    and replaces the catalog entry. Does NOT git-commit/push.
    """
    manifest = json.loads((export_dir / "manifest.json").read_text("utf-8"))
    book_id = manifest["book_id"]
    version = manifest["version"]
    rel = f"books/{book_id}/{book_id}-{version}.sqlite"

    dest = depot_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(export_dir / "graph.sqlite", dest)

    entry = build_entry(
        manifest, bundle_path=rel, bytes_=dest.stat().st_size, sha256=sha256_file(dest)
    )
    catalog_path = depot_dir / "catalog.json"
    existing: dict[str, Any] = (
        json.loads(catalog_path.read_text("utf-8")) if catalog_path.exists() else {}
    )
    stamp = generated_at or datetime.now(UTC).isoformat()
    updated = upsert_catalog(existing, entry, stamp)
    catalog_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated
