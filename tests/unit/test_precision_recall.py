"""Precision/Recall harness — pure-code; given golden + candidates, computes per-kind P/R."""

from __future__ import annotations

from tests.golden.precision_recall import compute_pr


def _g(**overrides: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    base: dict[str, list[dict[str, object]]] = {
        "persons": [],
        "events": [],
        "places": [],
        "states": [],
        "citations": [],
        "relations": [],
    }
    base.update(overrides)
    return base


def test_person_p_r_with_perfect_match() -> None:
    golden = _g(persons=[{"id": "per:a", "canonical_name": "重耳", "state_id": "sta:jin"}])
    cands = _g(persons=[{"canonical_name": "重耳", "state_id": "sta:jin"}])
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["person"]["precision"] == 1.0
    assert report["per_entity_type"]["person"]["recall"] == 1.0


def test_person_recall_drops_when_missing() -> None:
    golden = _g(
        persons=[
            {"id": "per:a", "canonical_name": "重耳", "state_id": "sta:jin"},
            {"id": "per:b", "canonical_name": "晋文公", "state_id": "sta:jin"},
        ]
    )
    cands = _g(persons=[{"canonical_name": "重耳", "state_id": "sta:jin"}])
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["person"]["recall"] == 0.5
    assert report["per_entity_type"]["person"]["fn"] == 1


def test_person_precision_drops_with_extras() -> None:
    golden = _g(persons=[{"id": "per:a", "canonical_name": "重耳", "state_id": "sta:jin"}])
    cands = _g(
        persons=[
            {"canonical_name": "重耳", "state_id": "sta:jin"},
            {"canonical_name": "周幽王", "state_id": "sta:zhou"},  # spurious
        ]
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["person"]["precision"] == 0.5
    assert report["per_entity_type"]["person"]["fp"] == 1


def test_event_matches_on_type_year_and_place() -> None:
    golden = _g(
        events=[
            {
                "id": "evt:1",
                "type": "攻陷",
                "date": {"year_bce": 771},
                "primary_place_id": "pla:haojing",
            }
        ]
    )
    cands = _g(
        events=[{"type": "攻陷", "date": {"year_bce": 771}, "primary_place_id": "pla:haojing"}]
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["event"]["precision"] == 1.0


def test_event_year_within_one_year_counts_as_match() -> None:
    golden = _g(
        events=[
            {
                "id": "evt:1",
                "type": "战",
                "date": {"year_bce": 632},
                "primary_place_id": "pla:cheng-pu",
            }
        ]
    )
    cands = _g(
        events=[{"type": "战", "date": {"year_bce": 633}, "primary_place_id": "pla:cheng-pu"}]
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["event"]["tp"] == 1
