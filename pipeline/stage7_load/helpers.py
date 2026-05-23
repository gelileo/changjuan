from __future__ import annotations

import re
import uuid
from typing import Any

# Confidence delta below which two values count as "similar" — disagreement triggers Conflict.
_SIMILAR_CONFIDENCE_DELTA = 0.1

_PERSON_SCALAR_FIELDS = (
    "gender",
    "birth_date_json",
    "death_date_json",
    "notes",
    "state_id",
    "clan_name",
    "social_category",
)

_PRECISION_RANK: dict[str, int] = {"point": 3, "circa": 2, "range": 1}


def _slugify(name: str) -> str:
    """Naive Chinese→ASCII-ish slug — fine for v1; will be replaced when pinyin is needed."""
    safe = re.sub(r"[^\w]+", "-", name).strip("-").lower()
    return safe or uuid.uuid4().hex[:8]


def merge_date_field(
    current: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Pick the winner between two date entries.

    Inputs are dicts of the form ``{"value": DateDict, "confidence": float}``.
    Returns the winner dict (or None if both are None).

    Rule (spec §7.2):
      - A more-precise date (lower uncertainty rank) wins over a less-precise one,
        even at slightly lower confidence (within _SIMILAR_CONFIDENCE_DELTA).
      - Otherwise higher confidence wins; on tie, current wins.
    """
    if current is None or current.get("value") is None:
        return new
    if new is None or new.get("value") is None:
        return current

    cur_value: dict[str, Any] = current["value"]
    new_value: dict[str, Any] = new["value"]
    cur_prec = _PRECISION_RANK.get(str(cur_value.get("uncertainty", "point")), 0)
    new_prec = _PRECISION_RANK.get(str(new_value.get("uncertainty", "point")), 0)
    cur_conf = float(current.get("confidence", 0.0))
    new_conf = float(new.get("confidence", 0.0))

    if new_prec > cur_prec and new_conf >= cur_conf - _SIMILAR_CONFIDENCE_DELTA:
        return new
    if cur_prec > new_prec and cur_conf >= new_conf - _SIMILAR_CONFIDENCE_DELTA:
        return current
    if new_conf > cur_conf:
        return new
    return current
