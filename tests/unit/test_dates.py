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
