from __future__ import annotations

import re
import uuid

# Confidence delta below which two values count as "similar" — disagreement triggers Conflict.
_SIMILAR_CONFIDENCE_DELTA = 0.1

_PERSON_SCALAR_FIELDS = (
    "gender",
    "birth_date_json",
    "death_date_json",
    "notes",
    "state_id",
    "clan_name",
)


def _slugify(name: str) -> str:
    """Naive Chinese→ASCII-ish slug — fine for v1; will be replaced when pinyin is needed."""
    safe = re.sub(r"[^\w]+", "-", name).strip("-").lower()
    return safe or uuid.uuid4().hex[:8]
