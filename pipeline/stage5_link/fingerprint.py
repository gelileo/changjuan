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
from collections.abc import Iterable


def candidate_fingerprint(name: str, variants: Iterable[str]) -> str:
    """Compute a 16-hex SHA-1 fingerprint over (name, sorted(set(variants)))."""
    normalized = sorted(set(variants))
    payload = json.dumps({"name": name, "variants": normalized}, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
