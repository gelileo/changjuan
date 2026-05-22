"""Merge regression set loader. Validates structure + cross-references."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_VALID_SOCIAL_CATEGORIES = frozenset(
    {
        "royalty",
        "noble",
        "official",
        "military",
        "religious",
        "clergy",
        "commoner",
        "servant",
        "foreign",
        "mythic",
        "unknown",
    }
)

_REQUIRED_TOP_KEYS = ("same_person_pairs", "different_person_pairs")
_REQUIRED_PAIR_FIELDS = ("rationale", "source", "person_a", "person_b")


class RegressionLoadError(Exception):
    """Raised when the merge regression YAML fails validation."""


def _validate_person(person: dict[str, Any], where: str) -> None:
    if not isinstance(person, dict):
        raise RegressionLoadError(f"{where}: person record must be a dict")
    if not person.get("canonical_name"):
        raise RegressionLoadError(f"{where}: missing or empty canonical_name")
    cat = person.get("social_category")
    if cat is not None and cat not in _VALID_SOCIAL_CATEGORIES:
        raise RegressionLoadError(
            f"{where}: invalid social_category '{cat}' "
            f"(must be one of {sorted(_VALID_SOCIAL_CATEGORIES)})"
        )


def _validate_pair(pair: dict[str, Any], where: str) -> None:
    if not isinstance(pair, dict):
        raise RegressionLoadError(f"{where}: pair must be a dict")
    for f in _REQUIRED_PAIR_FIELDS:
        if f not in pair:
            raise RegressionLoadError(f"{where}: missing required field '{f}'")
    _validate_person(pair["person_a"], f"{where}.person_a")
    _validate_person(pair["person_b"], f"{where}.person_b")


def load_regression_set(path: Path) -> dict[str, Any]:
    """Load + validate the merge regression set YAML. Raises on schema violations."""
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RegressionLoadError(f"{path.name}: top level must be a dict")

    for key in _REQUIRED_TOP_KEYS:
        if key not in data:
            raise RegressionLoadError(f"{path.name}: missing required key '{key}'")
        if not isinstance(data[key], list):
            raise RegressionLoadError(f"{path.name}: '{key}' must be a list")

    for i, pair in enumerate(data["same_person_pairs"]):
        _validate_pair(pair, f"same_person_pairs[{i}]")
    for i, pair in enumerate(data["different_person_pairs"]):
        _validate_pair(pair, f"different_person_pairs[{i}]")

    return data
