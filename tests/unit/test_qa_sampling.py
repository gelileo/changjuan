"""Deterministic 5% sampler for sampling QA — same pipeline_run_id always yields the same sample."""

from __future__ import annotations

from typing import Any

from pipeline.qa_sampling import select_sample


def _facts(n: int, run_id: str = "run:test") -> list[dict[str, Any]]:
    return [
        {"pipeline_run_id": run_id, "record_id": f"r{i}", "field": "canonical_name"}
        for i in range(n)
    ]


def test_sample_is_deterministic_across_runs() -> None:
    facts = _facts(1000)
    s1 = select_sample(facts)
    s2 = select_sample(facts)
    assert s1 == s2


def test_sample_size_approx_five_percent() -> None:
    facts = _facts(1000)
    s = select_sample(facts)
    # 5% of 1000 = 50; ±20% jitter from hash distribution; floor=30 always applies
    assert 30 <= len(s) <= 70


def test_sample_floor_kicks_in_for_small_runs() -> None:
    facts = _facts(100)
    s = select_sample(facts)
    assert len(s) >= 30


def test_sample_ceiling_kicks_in_for_huge_runs() -> None:
    facts = _facts(10000)
    s = select_sample(facts)
    assert len(s) <= 250


def test_sample_floor_caps_at_input_size() -> None:
    """If total facts < floor, the sample is the whole input."""
    facts = _facts(10)
    s = select_sample(facts)
    assert len(s) == 10
