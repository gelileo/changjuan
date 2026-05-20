"""Date parsing for 东周列国志.

The novel uses several date conventions; we dispatch to the matching parser by
pattern. Output is the structured Date dict described in concepts/data-model/dates-and-reigns.md.

This module starts with `explicit_reign_lu` only. Subsequent tasks add
`explicit_reign_zhou`, `relative_to_prior_event`, `era_only`, and `unknown`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

_REIGN_TABLE: dict[str, object] | None = None


def _reigns() -> dict[str, object]:
    global _REIGN_TABLE
    if _REIGN_TABLE is None:
        p = Path(__file__).parent / "reign_table.json"
        _REIGN_TABLE = json.loads(p.read_text(encoding="utf-8"))
    return _REIGN_TABLE


class DateDict(TypedDict, total=False):
    year_bce: int | None
    uncertainty: str
    year_bce_end: int
    original: str
    era: str | None
    inference_kind: str


# 一二三...十 mapping for reign-year parsing
_CN_DIGIT: dict[str, int] = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "元": 1,
}


def _cn_to_int(s: str) -> int:
    """Parse 元 / 一 / 十 / 二十 / 二十八 / 三十 etc. up to ~60 — enough for reign years."""
    if s in _CN_DIGIT:
        return _CN_DIGIT[s]
    if "十" in s:
        parts = s.split("十")
        tens = _CN_DIGIT[parts[0]] if parts[0] else 1
        ones = _CN_DIGIT[parts[1]] if parts[1] else 0
        return tens * 10 + ones
    raise ValueError(f"unparseable reign year: {s!r}")


_LU_PATTERN = re.compile(
    r"^(?:鲁)?(隐|桓|庄|闵|僖|文|宣|成|襄|昭|定|哀)(?:公)?([元一二三四五六七八九十]+)年$"
)


def _try_lu(original: str) -> DateDict | None:
    m = _LU_PATTERN.match(original)
    if not m:
        return None
    duke, year_cn = m.groups()
    duke_full = duke + "公"
    reigns = _reigns()
    lu_reigns = reigns["lu"]
    assert isinstance(lu_reigns, dict)
    reign = lu_reigns[duke_full]
    assert isinstance(reign, dict)
    n = _cn_to_int(year_cn)
    return DateDict(
        year_bce=reign["start_bce"] - (n - 1),
        uncertainty="point",
        original=original,
        era="春秋",
        inference_kind="explicit_reign_lu",
    )


_ZHOU_PATTERN = re.compile(
    r"^周(平|桓|庄|釐|惠|襄|顷|匡|定|简|灵|景|敬)(?:王)?([元一二三四五六七八九十]+)年$"
)


def _try_zhou(original: str) -> DateDict | None:
    m = _ZHOU_PATTERN.match(original)
    if not m:
        return None
    king, year_cn = m.groups()
    king_full = king + "王"
    reigns = _reigns()
    zhou_reigns = reigns["zhou"]
    assert isinstance(zhou_reigns, dict)
    reign = zhou_reigns[king_full]
    assert isinstance(reign, dict)
    n = _cn_to_int(year_cn)
    return DateDict(
        year_bce=reign["start_bce"] - (n - 1),
        uncertainty="point",
        original=original,
        era="春秋",
        inference_kind="explicit_reign_zhou",
    )


def parse_date(original: str) -> DateDict:
    """Parse a date string. Returns the structured Date dict."""
    if (d := _try_lu(original)) is not None:
        return d
    if (d := _try_zhou(original)) is not None:
        return d
    # Subsequent tasks add relative, era_only, unknown
    raise NotImplementedError(f"parse_date: no parser for {original!r}")
