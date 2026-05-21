"""Golden YAML loader — validates structure, citation FKs, chunk FKs, date enum, anchor cycles."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.golden.loader import GoldenLoadError, load_golden


def _write(p: Path, data: object) -> None:
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def golden_dir(tmp_path: Path) -> Path:
    d = tmp_path / "ch01"
    d.mkdir()
    _write(
        d / "citations.yaml",
        [
            {
                "id": "cit:1",
                "chunk_id": "chk:ch01-001",
                "paragraph": 1,
                "span": [0, 4],
                "quote": "重耳",
            },
        ],
    )
    _write(
        d / "persons.yaml",
        [
            {"id": "per:zhong-er", "canonical_name": "重耳", "citations": ["cit:1"]},
        ],
    )
    for name in ("events", "places", "states", "relations"):
        _write(d / f"{name}.yaml", [])
    return d


def test_loads_valid_golden_set(golden_dir):
    g = load_golden(golden_dir)
    assert len(g["persons"]) == 1
    assert len(g["citations"]) == 1
    assert g["persons"][0]["canonical_name"] == "重耳"


def test_rejects_dangling_citation_reference(golden_dir):
    _write(
        golden_dir / "persons.yaml",
        [
            {"id": "per:x", "canonical_name": "X", "citations": ["cit:NOPE"]},
        ],
    )
    with pytest.raises(GoldenLoadError, match="cit:NOPE"):
        load_golden(golden_dir)


def test_rejects_missing_required_field(golden_dir):
    _write(
        golden_dir / "persons.yaml",
        [
            {"id": "per:x"},  # missing canonical_name
        ],
    )
    with pytest.raises(GoldenLoadError, match="canonical_name"):
        load_golden(golden_dir)


def test_rejects_unknown_inference_kind(golden_dir):
    _write(
        golden_dir / "events.yaml",
        [
            {
                "id": "evt:x",
                "type": "战",
                "date": {"inference_kind": "bogus"},
                "citations": ["cit:1"],
            },
        ],
    )
    with pytest.raises(GoldenLoadError, match="inference_kind"):
        load_golden(golden_dir)


def test_rejects_relative_anchor_cycle(golden_dir):
    _write(
        golden_dir / "events.yaml",
        [
            {
                "id": "evt:a",
                "type": "战",
                "date": {
                    "inference_kind": "relative_to_prior_event",
                    "relative_anchor_event_id": "evt:b",
                    "original": "明年",
                },
                "citations": ["cit:1"],
            },
            {
                "id": "evt:b",
                "type": "战",
                "date": {
                    "inference_kind": "relative_to_prior_event",
                    "relative_anchor_event_id": "evt:a",
                    "original": "明年",
                },
                "citations": ["cit:1"],
            },
        ],
    )
    with pytest.raises(GoldenLoadError, match="cycle"):
        load_golden(golden_dir)
