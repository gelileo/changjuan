"""resolve_relative_dates — record-walking wrapper around parse_date(anchor=...) plus
explicit relative_anchor_event_id support."""

from __future__ import annotations

import pytest

from pipeline.dates import RelativeResolveError, resolve_relative_dates


def _ev(
    id_: str,
    original: str | None = None,
    year: int | None = None,
    anchor_id: str | None = None,
    kind: str = "explicit_reign_zhou",
) -> dict[str, object]:
    rec: dict[str, object] = {
        "id": id_,
        "type": "战",
        "date": {
            "inference_kind": kind,
            "original": original or "",
            "year_bce": year,
            "uncertainty": "point",
            "era": None,
        },
    }
    if anchor_id is not None:
        date = rec["date"]
        assert isinstance(date, dict)
        date["relative_anchor_event_id"] = anchor_id
        date["inference_kind"] = "relative_to_prior_event"
    return rec


def _date(rec: dict[str, object]) -> dict[str, object]:
    """Extract the 'date' sub-dict, asserting the type for mypy."""
    d = rec["date"]
    assert isinstance(d, dict)
    return d


def test_within_chunk_walkback_resolves() -> None:
    records = [
        _ev("e1", original="周幽王十一年", year=771, kind="explicit_reign_zhou"),
        _ev("e2", original="明年", kind="relative_to_prior_event"),
    ]
    out = resolve_relative_dates(records, conn=None)
    assert _date(out[1])["year_bce"] == 770  # 771 + (-1) BCE arithmetic


def test_cascading_relatives() -> None:
    records = [
        _ev("e1", original="周幽王十一年", year=771, kind="explicit_reign_zhou"),
        _ev("e2", original="明年", kind="relative_to_prior_event"),
        _ev("e3", original="明年", kind="relative_to_prior_event"),
    ]
    out = resolve_relative_dates(records, conn=None)
    assert _date(out[1])["year_bce"] == 770
    assert _date(out[2])["year_bce"] == 769


def test_no_prior_anchor_leaves_null_and_reduces_confidence() -> None:
    records = [_ev("e1", original="明年", kind="relative_to_prior_event")]
    out = resolve_relative_dates(records, conn=None)
    assert _date(out[0])["year_bce"] is None


def test_explicit_anchor_overrides_walkback() -> None:
    """When relative_anchor_event_id is set, use the anchor's year (looked up via db helper),
    not the chunk-local walkback."""
    records = [
        _ev("e1", original="周幽王十一年", year=771, kind="explicit_reign_zhou"),  # walkback target
        _ev("e2", original="明年", anchor_id="evt:other-source", kind="relative_to_prior_event"),
    ]

    def fake_lookup(conn: object, event_id: str) -> dict[str, object] | None:
        assert event_id == "evt:other-source"
        return {"year_bce": 600}

    out = resolve_relative_dates(records, conn=None, anchor_lookup=fake_lookup)
    assert _date(out[1])["year_bce"] == 599  # 600 + (-1)


def test_dangling_anchor_raises() -> None:
    records = [_ev("e1", original="明年", anchor_id="evt:nope", kind="relative_to_prior_event")]

    def fake_lookup(conn: object, event_id: str) -> dict[str, object] | None:
        return None

    with pytest.raises(RelativeResolveError, match="dangling"):
        resolve_relative_dates(records, conn=None, anchor_lookup=fake_lookup)


def test_anchor_cycle_raises() -> None:
    """An anchor pointing back to its own source raises."""
    records = [
        _ev("e1", original="明年", anchor_id="e1", kind="relative_to_prior_event"),
    ]

    def fake_lookup(conn: object, event_id: str) -> dict[str, object] | None:
        return {"id": event_id, "year_bce": None, "relative_anchor_event_id": "e1"}

    with pytest.raises(RelativeResolveError, match="cycle"):
        resolve_relative_dates(records, conn=None, anchor_lookup=fake_lookup)


def test_parenthesized_original_treated_as_same_year() -> None:
    """Agent-emitted parenthesized notes like '(千亩之后)' mean 'same narrative
    beat, same year' and walkback should resolve them to the rolling anchor's year."""
    records = [
        _ev("e1", original="周宣王三十九年", year=789, kind="explicit_reign_zhou"),
        _ev("e2", original="(千亩之后)", kind="relative_to_prior_event"),
        _ev("e3", original="(料民回京时)", kind="relative_to_prior_event"),
    ]
    out = resolve_relative_dates(records, conn=None)
    assert out[1]["date"]["year_bce"] == 789  # type: ignore[index]
    assert out[2]["date"]["year_bce"] == 789  # type: ignore[index]


def test_non_parenthesized_unknown_original_stays_null() -> None:
    """Don't invent dates for tokens we don't recognize and aren't paren-shorthand."""
    records = [
        _ev("e1", original="周宣王三十九年", year=789, kind="explicit_reign_zhou"),
        _ev("e2", original="某神秘时间", kind="relative_to_prior_event"),
    ]
    out = resolve_relative_dates(records, conn=None)
    assert out[1]["date"]["year_bce"] is None  # type: ignore[index]


def test_empty_parens_stays_null() -> None:
    """Don't treat '()' as offset=0; it carries no semantic content."""
    records = [
        _ev("e1", original="周宣王三十九年", year=789, kind="explicit_reign_zhou"),
        _ev("e2", original="()", kind="relative_to_prior_event"),
    ]
    out = resolve_relative_dates(records, conn=None)
    assert out[1]["date"]["year_bce"] is None  # type: ignore[index]
