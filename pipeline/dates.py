"""Date parsing for 东周列国志.

The novel uses several date conventions; we dispatch to the matching parser by
pattern. Output is the structured Date dict described in concepts/data-model/dates-and-reigns.md.

This module starts with `explicit_reign_lu` only. Subsequent tasks add
`explicit_reign_zhou`, `relative_to_prior_event`, `era_only`, and `unknown`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NotRequired, TypedDict

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
    relative_anchor_event_id: NotRequired[str | None]


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


_ERA_PATTERNS: list[tuple[re.Pattern[str], tuple[str, int, int]]] = [
    (re.compile(r"^春秋初$"), ("春秋", 770, 720)),
    (re.compile(r"^春秋早期$"), ("春秋", 770, 700)),
    (re.compile(r"^春秋中期$"), ("春秋", 700, 600)),
    (re.compile(r"^春秋末$"), ("春秋", 510, 476)),
    (re.compile(r"^春秋晚期$"), ("春秋", 550, 476)),
    (re.compile(r"^战国初$"), ("战国", 475, 430)),
    (re.compile(r"^战国早期$"), ("战国", 475, 400)),
    (re.compile(r"^战国中期$"), ("战国", 400, 300)),
    (re.compile(r"^战国末$"), ("战国", 260, 221)),
    (re.compile(r"^战国晚期$"), ("战国", 300, 221)),
]


def _try_era(original: str) -> DateDict | None:
    for pat, (era, start, end) in _ERA_PATTERNS:
        if pat.match(original):
            return DateDict(
                year_bce=(start + end) // 2,
                year_bce_end=end,
                uncertainty="range",
                original=original,
                era=era,
                inference_kind="era_only",
            )
    return None


_RELATIVE_OFFSETS: dict[str, int] = {
    "其年": 0,
    "明年": -1,  # next year — BCE year decreases
    "次年": -1,
    "去年": +1,  # last year
    "前年": +1,
    "是岁": 0,
    "是年": 0,
}


def _try_relative(original: str, anchor: DateDict | None) -> DateDict | None:
    # Strip a leading 是冬/是夏/是春/是秋 — they're season markers attached to 是年.
    stripped = re.sub(r"^是[春夏秋冬]", "是年", original)
    if stripped not in _RELATIVE_OFFSETS:
        return None
    if anchor is None or anchor.get("year_bce") is None:
        return None
    anchor_year = anchor["year_bce"]
    assert isinstance(anchor_year, int)
    offset = _RELATIVE_OFFSETS[stripped]
    return DateDict(
        year_bce=anchor_year + offset,
        uncertainty="point",
        original=original,
        era=anchor.get("era"),
        inference_kind="relative_to_prior_event",
    )


def _unknown(original: str) -> DateDict:
    return DateDict(
        year_bce=None,
        uncertainty="point",
        original=original,
        era=None,
        inference_kind="unknown",
    )


def parse_date(original: str, anchor: DateDict | None = None) -> DateDict:
    """Parse a date string. Returns the structured Date dict.

    Never raises — returns inference_kind='unknown' for unrecognized inputs.
    The optional `anchor` is a previously-parsed DateDict used to resolve
    relative references (其年, 明年, 次年, 去年, 前年, 是岁, 是年, 是+season).
    Without an anchor, relative references fall through to unknown.
    """
    if (d := _try_lu(original)) is not None:
        return d
    if (d := _try_zhou(original)) is not None:
        return d
    if (d := _try_relative(original, anchor)) is not None:
        return d
    if (d := _try_era(original)) is not None:
        return d
    return _unknown(original)


class RelativeResolveError(Exception):
    """Raised on dangling/cyclic relative-anchor references."""


def _default_anchor_lookup(conn: object, event_id: str) -> dict[str, object] | None:
    """Default lookup: query canonical events table by id; return {'year_bce': ...} or None."""
    if conn is None:
        return None
    # conn is a sqlite3.Connection at runtime
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT json_extract(date_json, '$.year_bce') FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    return {"year_bce": row[0]}


def _offset_from_original(original: str, override: int | None) -> int | None:
    """Return the BCE-arithmetic offset to apply.
    `override` is calendar-years-later (so negated).
    Parenthesized narrative notes ("(千亩之后)", "(料民回京时)") are treated as
    offset=0 (same year as the rolling anchor) — they're the agent's shorthand
    for "same narrative beat, no explicit relative-time token applies."
    Returns None for non-parenthesized unknown strings so the resolver leaves
    year_bce null rather than silently inventing a date."""
    if override is not None:
        return -override
    if original in _RELATIVE_OFFSETS:
        return _RELATIVE_OFFSETS[original]
    stripped = original.strip()
    if stripped.startswith("(") and stripped.endswith(")") and len(stripped) > 2:
        return 0
    return None


def resolve_relative_dates(
    records: Sequence[dict[str, object]],
    conn: object,
    *,
    anchor_lookup: Callable[[object, str], dict[str, object] | None] | None = None,
    offset_override: int | None = None,
) -> list[dict[str, object]]:
    """Resolve `relative_to_prior_event` records in-place against the same batch (walkback)
    or via an explicit `relative_anchor_event_id` looked up through `anchor_lookup`.

    Returns the same records (mutated in place for convenience).
    """
    lookup = anchor_lookup or _default_anchor_lookup
    by_id: dict[str, dict[str, object]] = {}
    for r in records:
        rid = r.get("id")
        if isinstance(rid, str):
            by_id[rid] = r
    rolling_anchor: dict[str, object] | None = None

    for record in records:
        date_raw = record.get("date")
        if not isinstance(date_raw, dict):
            continue
        date: dict[str, object] = date_raw
        kind = date.get("inference_kind")

        if kind != "relative_to_prior_event":
            if date.get("year_bce") is not None:
                rolling_anchor = date
            continue

        explicit_id_raw = date.get("relative_anchor_event_id")
        if explicit_id_raw is not None:
            if not isinstance(explicit_id_raw, str):
                date["year_bce"] = None
                continue
            explicit_id: str = explicit_id_raw
            record_id = record.get("id")
            if explicit_id == record_id:
                raise RelativeResolveError(f"anchor cycle: event {record_id} anchors to itself")
            visited: set[str | None] = {record_id if isinstance(record_id, str) else None}
            cursor: str | None = explicit_id
            anchor_record: dict[str, object] | None = None
            while cursor is not None:
                if cursor in visited:
                    raise RelativeResolveError(f"anchor cycle through {cursor}")
                visited.add(cursor)
                chunk_match = by_id.get(cursor)
                if chunk_match is not None:
                    anchor_record = chunk_match
                else:
                    anchor_record = lookup(conn, cursor)
                if anchor_record is None:
                    raise RelativeResolveError(f"dangling relative_anchor_event_id '{cursor}'")
                next_anchor_date_raw = anchor_record.get("date")
                next_anchor_date = (
                    next_anchor_date_raw
                    if isinstance(next_anchor_date_raw, dict)
                    else anchor_record
                )
                next_id_raw = next_anchor_date.get("relative_anchor_event_id")
                if next_id_raw is None:
                    break
                if not isinstance(next_id_raw, str):
                    break
                cursor = next_id_raw
            assert anchor_record is not None  # loop body guarantees this
            anchor_year_container = anchor_record.get("date")
            if isinstance(anchor_year_container, dict):
                anchor_year = anchor_year_container.get("year_bce")
            else:
                anchor_year = anchor_record.get("year_bce")
            if anchor_year is None:
                date["year_bce"] = None
                continue
            original_str = date.get("original", "")
            if not isinstance(original_str, str):
                original_str = ""
            offset = _offset_from_original(original_str, offset_override)
            if offset is None:
                date["year_bce"] = None
                continue
            assert isinstance(anchor_year, int)
            date["year_bce"] = anchor_year + offset
            continue

        # Walkback path
        if rolling_anchor is None or rolling_anchor.get("year_bce") is None:
            date["year_bce"] = None
            continue
        original_str = date.get("original", "")
        if not isinstance(original_str, str):
            original_str = ""
        offset = _offset_from_original(original_str, None)
        if offset is None:
            date["year_bce"] = None
            continue
        rolling_year = rolling_anchor["year_bce"]
        assert isinstance(rolling_year, int)
        date["year_bce"] = rolling_year + offset
        if date["year_bce"] is not None:
            rolling_anchor = date

    return list(records)
