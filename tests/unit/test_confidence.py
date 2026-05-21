"""Confidence scorer stub — function of citation quote length + justification completeness."""

from typing import Any

from pipeline.confidence import score_extraction_record


def _rec(
    quote: str = "重耳",
    justifications: dict[str, str] | None = None,
    scalar_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "citation": {"quote": quote},
        "justifications": justifications or {},
        "_scalar_fields": scalar_fields or ["canonical_name"],
    }


def test_base_score_with_minimal_input() -> None:
    score = score_extraction_record(_rec(quote="x"))
    assert score >= 0.7


def test_score_never_exceeds_ceiling() -> None:
    rec = _rec(
        quote="x" * 1000,
        justifications={f: "y" for f in ["a", "b", "c"]},
        scalar_fields=["a", "b", "c"],
    )
    score = score_extraction_record(rec)
    assert score <= 0.95


def test_longer_citation_increases_score() -> None:
    short = score_extraction_record(_rec(quote="x"))
    long = score_extraction_record(_rec(quote="x" * 50))
    assert long > short


def test_complete_justifications_increase_score() -> None:
    no_justif = score_extraction_record(_rec(scalar_fields=["a", "b"], justifications={}))
    full = score_extraction_record(
        _rec(scalar_fields=["a", "b"], justifications={"a": "x", "b": "y"})
    )
    assert full > no_justif
