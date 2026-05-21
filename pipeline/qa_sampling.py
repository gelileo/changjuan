"""Deterministic 5% sampler for sampling QA.

Sample membership is keyed by hash(pipeline_run_id, record_id, field). Same input
always produces the same sample. Bounded by config.QA_SAMPLE_FLOOR and QA_SAMPLE_CEILING.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pipeline import config


def _hash_to_float(pipeline_run_id: str, record_id: str, field: str) -> float:
    """Stable [0, 1) hash."""
    h = hashlib.sha256(f"{pipeline_run_id}|{record_id}|{field}".encode()).digest()
    n = int.from_bytes(h[:8], "big")
    return n / (1 << 64)


def select_sample(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the deterministic ~5% sample of `facts`, bounded by floor/ceiling."""
    if not facts:
        return []
    target = max(
        min(int(len(facts) * config.QA_SAMPLE_FRACTION) + 1, config.QA_SAMPLE_CEILING),
        config.QA_SAMPLE_FLOOR,
    )
    target = min(target, len(facts))

    scored = [(_hash_to_float(f["pipeline_run_id"], f["record_id"], f["field"]), f) for f in facts]
    scored.sort(key=lambda pair: pair[0])
    return [f for _, f in scored[:target]]
