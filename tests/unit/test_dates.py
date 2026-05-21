import pytest

from pipeline.dates import parse_date


def test_lu_xigong_year_28() -> None:
    d = parse_date("鲁僖公二十八年")
    assert d["year_bce"] == 632
    assert d["uncertainty"] == "point"
    assert d["original"] == "鲁僖公二十八年"
    assert d["inference_kind"] == "explicit_reign_lu"


def test_lu_yingong_year_1() -> None:
    d = parse_date("鲁隐公元年")
    assert d["year_bce"] == 722
    assert d["inference_kind"] == "explicit_reign_lu"


def test_lu_zhuanggong_year_10() -> None:
    d = parse_date("鲁庄公十年")
    # 庄公 starts 693 BCE, so year 10 = 684 BCE
    assert d["year_bce"] == 684


@pytest.mark.parametrize("variant", ["鲁僖二十八年", "僖公二十八年"])
def test_lu_lenient_prefixes(variant: str) -> None:
    """Tolerate dropped 鲁 prefix or dropped 公 suffix (common in the novel)."""
    d = parse_date(variant)
    assert d["year_bce"] == 632


def test_zhou_pingwang_year_1() -> None:
    d = parse_date("周平王元年")
    assert d["year_bce"] == 770
    assert d["inference_kind"] == "explicit_reign_zhou"


def test_zhou_xiangwang_year_20() -> None:
    """周襄王 starts 651 BCE; year 20 = 632 BCE."""
    d = parse_date("周襄王二十年")
    assert d["year_bce"] == 632
    assert d["inference_kind"] == "explicit_reign_zhou"


def test_era_only_chunqiu_late() -> None:
    d = parse_date("春秋末")
    assert d["inference_kind"] == "era_only"
    assert d["uncertainty"] == "range"
    assert d["era"] == "春秋"
    year = d["year_bce"]
    assert year is not None
    assert (
        476 <= year <= 510
    )  # midpoint of "late 春秋" (plan typo corrected: 500<=x<=480 was impossible)
    assert d["year_bce_end"] is not None


def test_era_only_zhanguo_early() -> None:
    d = parse_date("战国初")
    assert d["era"] == "战国"
    assert d["inference_kind"] == "era_only"


def test_unknown_passthrough() -> None:
    d = parse_date("某时")
    assert d["inference_kind"] == "unknown"
    assert d["year_bce"] is None
    assert d["original"] == "某时"


def test_relative_明年_with_anchor() -> None:
    anchor = parse_date("鲁僖公二十八年")  # 632 BCE
    d = parse_date("明年", anchor=anchor)
    assert d["year_bce"] == 631
    assert d["inference_kind"] == "relative_to_prior_event"
    assert d["uncertainty"] == "point"


def test_relative_其年_returns_anchor_year() -> None:
    anchor = parse_date("鲁僖公二十八年")
    d = parse_date("其年", anchor=anchor)
    assert d["year_bce"] == 632
    assert d["inference_kind"] == "relative_to_prior_event"


def test_relative_前年_with_anchor() -> None:
    anchor = parse_date("鲁僖公二十八年")
    d = parse_date("前年", anchor=anchor)
    assert d["year_bce"] == 633


def test_relative_without_anchor_returns_unknown() -> None:
    d = parse_date("明年")
    assert d["inference_kind"] == "unknown"


def test_datedict_accepts_relative_anchor_event_id() -> None:
    """The schema-level Date dict accepts an optional relative_anchor_event_id field."""
    from pipeline.dates import DateDict

    d: DateDict = {
        "year_bce": None,
        "uncertainty": "point",
        "original": "其后五年",
        "era": None,
        "inference_kind": "relative_to_prior_event",
        "relative_anchor_event_id": "evt:zhou-you-wang-killed-771bce",
    }
    assert d["relative_anchor_event_id"] == "evt:zhou-you-wang-killed-771bce"


def test_lu_xi_gong_33_resolves_to_627_bce() -> None:
    """鲁僖公33年 → 627 BCE (鲁僖公 reigned 659-627 BCE; year 1 = 659, year 33 = 627)."""
    d = parse_date("鲁僖公三十三年")
    assert d["year_bce"] == 627


def test_lu_wen_gong_1_resolves_to_626_bce() -> None:
    """鲁文公1年 → 626 BCE (鲁文公 reigned 626-609 BCE)."""
    d = parse_date("鲁文公元年")
    assert d["year_bce"] == 626


def test_lu_zhuang_gong_32_resolves_to_662_bce() -> None:
    """鲁庄公32年 → 662 BCE (鲁庄公 reigned 693-662 BCE; year 32 = 662)."""
    d = parse_date("鲁庄公三十二年")
    assert d["year_bce"] == 662
