"""Stage 4 — normalization helpers.

Thin layer over pipeline.dates for stages 3/5/7 to call when they have raw date
strings extracted from chunks. Returns JSON strings ready to insert into the
*_date_json columns of corpus.sqlite and changjuan.sqlite.
"""

from __future__ import annotations

import json

from pipeline.dates import DateDict, parse_date


def normalize_date_string(original: str, anchor_json: str | None = None) -> str:
    """Parse a raw date string and return a JSON-serialised DateDict.

    Args:
        original: The raw date string from the corpus (e.g. '鲁僖公二十八年').
        anchor_json: Optional JSON string of a prior DateDict to resolve
                     relative references (其年, 明年, etc.).

    Returns:
        A JSON string suitable for insertion into *_date_json columns.
    """
    anchor: DateDict | None = json.loads(anchor_json) if anchor_json else None
    d = parse_date(original, anchor=anchor)
    return json.dumps(d, ensure_ascii=False)
