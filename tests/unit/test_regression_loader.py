"""Merge regression set loader — validates YAML structure + cross-references."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.golden.regression_loader import RegressionLoadError, load_regression_set


def _write(p: Path, data: dict[str, object]) -> None:
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def reg_dir(tmp_path: Path) -> Path:
    """Returns the directory in which the regression YAML should live."""
    return tmp_path


def _minimal_pair(name_a: str = "甲", name_b: str = "乙") -> dict[str, object]:
    return {
        "rationale": "test",
        "source": "synthetic",
        "person_a": {"canonical_name": name_a},
        "person_b": {"canonical_name": name_b},
    }


def test_loads_empty_set(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {"same_person_pairs": [], "different_person_pairs": []})
    regset = load_regression_set(f)
    assert regset["same_person_pairs"] == []
    assert regset["different_person_pairs"] == []


def test_loads_populated_set(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(
        f,
        {
            "same_person_pairs": [_minimal_pair("重耳", "晋文公")],
            "different_person_pairs": [_minimal_pair("重耳", "重耳")],
        },
    )
    regset = load_regression_set(f)
    assert len(regset["same_person_pairs"]) == 1
    assert regset["same_person_pairs"][0]["person_a"]["canonical_name"] == "重耳"
    assert len(regset["different_person_pairs"]) == 1


def test_rejects_missing_top_level_key(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {"same_person_pairs": []})  # missing different_person_pairs
    with pytest.raises(RegressionLoadError, match="different_person_pairs"):
        load_regression_set(f)


def test_rejects_pair_missing_required_field(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(
        f,
        {
            "same_person_pairs": [
                {
                    # missing rationale, source
                    "person_a": {"canonical_name": "甲"},
                    "person_b": {"canonical_name": "乙"},
                }
            ],
            "different_person_pairs": [],
        },
    )
    with pytest.raises(RegressionLoadError, match="rationale|source"):
        load_regression_set(f)


def test_rejects_pair_missing_person(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(
        f,
        {
            "same_person_pairs": [
                {
                    "rationale": "x",
                    "source": "y",
                    "person_a": {"canonical_name": "甲"},
                    # missing person_b
                }
            ],
            "different_person_pairs": [],
        },
    )
    with pytest.raises(RegressionLoadError, match="person_b"):
        load_regression_set(f)


def test_rejects_person_missing_canonical_name(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(
        f,
        {
            "same_person_pairs": [
                {
                    "rationale": "x",
                    "source": "y",
                    "person_a": {"state_id": "sta:jin"},  # missing canonical_name
                    "person_b": {"canonical_name": "乙"},
                }
            ],
            "different_person_pairs": [],
        },
    )
    with pytest.raises(RegressionLoadError, match="canonical_name"):
        load_regression_set(f)


def test_rejects_invalid_social_category(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(
        f,
        {
            "same_person_pairs": [
                {
                    "rationale": "x",
                    "source": "y",
                    "person_a": {"canonical_name": "甲", "social_category": "wizard"},
                    "person_b": {"canonical_name": "乙"},
                }
            ],
            "different_person_pairs": [],
        },
    )
    with pytest.raises(RegressionLoadError, match="social_category"):
        load_regression_set(f)
