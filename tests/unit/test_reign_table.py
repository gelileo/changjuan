import json
from pathlib import Path


def _load_reigns() -> dict:  # type: ignore[type-arg]
    p = Path(__file__).resolve().parents[2] / "pipeline" / "reign_table.json"
    return json.loads(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_reign_table_has_lu_and_zhou_keys() -> None:
    data = _load_reigns()
    assert "lu" in data
    assert "zhou" in data


def test_lu_xigong_year_28_is_632_bce() -> None:
    """鲁僖公二十八年 = 632 BCE (城濮之战 year). Anchor case."""
    data = _load_reigns()
    xigong = data["lu"]["僖公"]
    # Each entry: {"start_bce": <int>, "end_bce": <int>}
    assert xigong["start_bce"] - 27 == 632  # year 28 = start_bce - 27


def test_lu_yingong_year_1_is_722_bce() -> None:
    """鲁隐公元年 = 722 BCE (春秋 begins). Other anchor."""
    data = _load_reigns()
    assert data["lu"]["隐公"]["start_bce"] == 722


def test_zhou_pingwang_year_1_is_770_bce() -> None:
    """周平王元年 = 770 BCE (东周 begins)."""
    data = _load_reigns()
    assert data["zhou"]["平王"]["start_bce"] == 770
