"""Deterministic confidence scorer for stage-3 extracted records.

v1 stub: function of citation quote length + justification completeness + base.
Returns floats in [0.7, 0.95]. The 0.95 ceiling reserves 1.0 for curated records.

Future phases will tune scoring weights against sampling-QA reliability diagrams;
the function signature is the stable entry point so callers don't change.
"""

from __future__ import annotations

from typing import Any

_BASE = 0.7
_CITATION_BONUS_PER_CHAR = 1 / 100  # max 0.15 at 15+ char quotes
_CITATION_BONUS_MAX = 0.15
_JUSTIFICATION_BONUS_FULL = 0.10
_SCORE_CEILING = 0.95


def score_extraction_record(record: dict[str, Any]) -> float:
    """Score a single extracted record. Returns float in [_BASE, _SCORE_CEILING]."""
    quote = (record.get("citation") or {}).get("quote") or ""
    citation_bonus = min(len(quote) * _CITATION_BONUS_PER_CHAR, _CITATION_BONUS_MAX)

    scalar_fields = record.get("_scalar_fields") or []
    justifications = record.get("justifications") or {}
    all_present = bool(scalar_fields) and all(justifications.get(f) for f in scalar_fields)
    justification_bonus = _JUSTIFICATION_BONUS_FULL if all_present else 0.0

    return min(_BASE + citation_bonus + justification_bonus, _SCORE_CEILING)
