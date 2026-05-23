"""Stable identity hash for a candidate person across re-extractions.

The fingerprint is the key reject-memory uses to recognize the same
candidate even after a re-link or re-extraction run. It is computed from
candidate-side data only — no canonical-side dependency — so it remains
stable across canonical-side merges performed later.

Properties:
  - Deterministic given (name, variants).
  - Order-insensitive and dedup-insensitive over variants.
  - Changes when the name changes or a new variant is added (genuine new
    evidence; re-flagging is intentional).

See concepts/pipeline/linking.md for the role this plays in the linker
filter, and the Phase 6 spec §3.2 for trade-offs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable


def candidate_fingerprint(name: str, variants: Iterable[str]) -> str:
    """Compute a 16-hex SHA-1 fingerprint over (name, sorted(set(variants)))."""
    normalized = sorted(set(variants))
    payload = json.dumps({"name": name, "variants": normalized}, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def fingerprint_for_candidate_a(conn: sqlite3.Connection, cand_a_id: str) -> str | None:
    """Compute candidate_fingerprint for the A-side of a merge_candidates row.

    Phase 5.1 dual-table: A may be in candidate_persons (typical) or persons.
    Returns None if cand_a_id is found in neither table (caller should treat
    as "can't filter this pair").
    """
    cp = conn.execute(
        "SELECT canonical_name, variants_json FROM candidate_persons WHERE id = ?",
        (cand_a_id,),
    ).fetchone()
    if cp is not None:
        name = cp[0]
        raw = cp[1]
        variants: list[str] = []
        if raw:
            parsed = json.loads(raw)
            variants = [v["variant"] for v in parsed if isinstance(v, dict) and "variant" in v]
        return candidate_fingerprint(name, variants)

    p = conn.execute("SELECT canonical_name FROM persons WHERE id = ?", (cand_a_id,)).fetchone()
    if p is None:
        return None
    variant_rows = conn.execute(
        "SELECT variant FROM person_variants WHERE person_id = ?", (cand_a_id,)
    ).fetchall()
    return candidate_fingerprint(p[0], [r[0] for r in variant_rows])
