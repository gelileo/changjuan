"""Linker regression-set assertion. Every same-pair must score >= auto-threshold;
every different-pair must score < auto-threshold."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import config
from pipeline.stage5_link.scoring import person_match_score
from tests.golden.regression_loader import load_regression_set

pytestmark = pytest.mark.regression


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_known_same_pairs_score_above_auto_merge_threshold() -> None:
    regset = load_regression_set(REPO_ROOT / "tests" / "golden" / "merge_regression.yaml")
    failures = []
    for pair in regset["same_person_pairs"]:
        result = person_match_score(pair["person_a"], pair["person_b"])
        if result["score"] < config.LINKER_AUTO_MERGE_THRESHOLD:
            failures.append(
                f"{pair['person_a']['canonical_name']} ↔ {pair['person_b']['canonical_name']}: "
                f"scored {result['score']:.2f} (below {config.LINKER_AUTO_MERGE_THRESHOLD}). "
                f"Rationale: {pair['rationale']}. Features: {result['features']}"
            )
    assert not failures, "\n".join(failures)


def test_known_different_pairs_score_below_auto_merge_threshold() -> None:
    regset = load_regression_set(REPO_ROOT / "tests" / "golden" / "merge_regression.yaml")
    failures = []
    for pair in regset["different_person_pairs"]:
        result = person_match_score(pair["person_a"], pair["person_b"])
        if result["score"] >= config.LINKER_AUTO_MERGE_THRESHOLD:
            failures.append(
                f"{pair['person_a']['canonical_name']} ↔ {pair['person_b']['canonical_name']}: "
                f"scored {result['score']:.2f} (>= {config.LINKER_AUTO_MERGE_THRESHOLD}). "
                f"Rationale: {pair['rationale']}. Features: {result['features']}"
            )
    assert not failures, "\n".join(failures)
