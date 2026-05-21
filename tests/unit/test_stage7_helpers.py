"""merge_date_field — more-precise wins, then higher-confidence wins."""

from pipeline.stage7_load.helpers import merge_date_field


def test_merge_date_field_point_beats_range_at_lower_confidence() -> None:
    """A more-precise date (point) wins over a less-precise (range) even at slightly
    lower confidence — spec §7.2 rule."""
    cur = {
        "value": {"year_bce": 770, "year_bce_end": 760, "uncertainty": "range"},
        "confidence": 0.9,
    }
    new = {"value": {"year_bce": 771, "uncertainty": "point"}, "confidence": 0.85}
    winner = merge_date_field(cur, new)
    assert winner == new


def test_merge_date_field_higher_confidence_wins_when_precision_same() -> None:
    cur = {"value": {"year_bce": 770, "uncertainty": "point"}, "confidence": 0.7}
    new = {"value": {"year_bce": 771, "uncertainty": "point"}, "confidence": 0.85}
    assert merge_date_field(cur, new) == new


def test_merge_date_field_returns_other_when_one_is_none() -> None:
    new = {"value": {"year_bce": 771, "uncertainty": "point"}, "confidence": 0.85}
    assert merge_date_field(None, new) == new
    assert merge_date_field(new, None) == new


def test_merge_date_field_tie_keeps_current() -> None:
    cur = {"value": {"year_bce": 770, "uncertainty": "point"}, "confidence": 0.85}
    new = {"value": {"year_bce": 771, "uncertainty": "point"}, "confidence": 0.85}
    assert merge_date_field(cur, new) == cur
