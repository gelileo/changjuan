import json

from pipeline.stage4_normalize import normalize_date_string


def test_normalize_returns_json_string() -> None:
    s = normalize_date_string("鲁僖公二十八年")
    d = json.loads(s)
    assert d["year_bce"] == 632
    assert d["inference_kind"] == "explicit_reign_lu"
