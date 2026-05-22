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


def test_person_match_blocked_by_social_category_mismatch() -> None:
    golden = _g(
        persons=[
            {
                "id": "per:a",
                "canonical_name": "重耳",
                "state_id": "sta:jin",
                "social_category": "noble",
            }
        ]
    )
    cands = _g(
        persons=[{"canonical_name": "重耳", "state_id": "sta:jin", "social_category": "royalty"}]
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["person"]["tp"] == 0
    assert report["per_entity_type"]["person"]["fp"] == 1
    assert report["per_entity_type"]["person"]["fn"] == 1


def test_person_match_ignores_missing_social_category() -> None:
    """When either side omits social_category, it doesn't block the match."""
    golden = _g(persons=[{"id": "per:a", "canonical_name": "重耳", "state_id": "sta:jin"}])
    cands = _g(
        persons=[{"canonical_name": "重耳", "state_id": "sta:jin", "social_category": "royalty"}]
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["person"]["tp"] == 1


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


def test_person_match_with_chunk_local_state_id_resolves_via_lookup() -> None:
    """Person matcher resolves state_id to name via the lookup; chunk-local
    's1' (candidate) and canonical 'sta:zhou' (golden) both resolve to '周'."""
    golden = _g(
        persons=[{"id": "per:a", "canonical_name": "周宣王", "state_id": "sta:zhou"}],
        states=[{"id": "sta:zhou", "name": "周"}],
    )
    cands = _g(
        persons=[{"id": "p1", "canonical_name": "周宣王", "state_id": "s1"}],
        states=[{"id": "s1", "name": "周"}],
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["person"]["tp"] == 1


def test_event_match_with_chunk_local_primary_place_id_resolves_via_lookup() -> None:
    golden = _g(
        events=[
            {
                "id": "evt:a",
                "type": "战",
                "date": {"year_bce": 789},
                "primary_place_id": "pla:qian-mu",
            }
        ],
        places=[{"id": "pla:qian-mu", "name": "千亩"}],
    )
    cands = _g(
        events=[
            {
                "id": "e1",
                "type": "战",
                "date": {"year_bce": 789},
                "primary_place_id": "pl1",
            }
        ],
        places=[{"id": "pl1", "name": "千亩"}],
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["event"]["tp"] == 1


def test_event_match_year_alone_suffices_when_place_differs() -> None:
    """type matches; year matches; place differs → still counted as match (relaxed matcher)."""
    golden = _g(
        events=[
            {
                "id": "evt:a",
                "type": "战",
                "date": {"year_bce": 789},
                "primary_place_id": "pla:qian-mu",
            }
        ],
        places=[{"id": "pla:qian-mu", "name": "千亩"}],
    )
    cands = _g(
        events=[{"id": "e1", "type": "战", "date": {"year_bce": 789}, "primary_place_id": "pl1"}],
        places=[{"id": "pl1", "name": "镐京"}],  # different place name
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["event"]["tp"] == 1


def test_event_match_place_alone_suffices_when_year_differs() -> None:
    """type matches; place matches; year differs by more than 1 → still match (relaxed matcher)."""
    golden = _g(
        events=[
            {
                "id": "evt:a",
                "type": "战",
                "date": {"year_bce": 789},
                "primary_place_id": "pla:qian-mu",
            }
        ],
        places=[{"id": "pla:qian-mu", "name": "千亩"}],
    )
    cands = _g(
        events=[{"id": "e1", "type": "战", "date": {"year_bce": 800}, "primary_place_id": "pl1"}],
        places=[{"id": "pl1", "name": "千亩"}],
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["event"]["tp"] == 1


def test_event_match_type_alone_does_not_suffice() -> None:
    """type matches but BOTH year AND place differ → still mismatch (relaxed but not loose)."""
    golden = _g(
        events=[
            {
                "id": "evt:a",
                "type": "战",
                "date": {"year_bce": 789},
                "primary_place_id": "pla:qian-mu",
            }
        ],
        places=[{"id": "pla:qian-mu", "name": "千亩"}],
    )
    cands = _g(
        events=[{"id": "e1", "type": "战", "date": {"year_bce": 800}, "primary_place_id": "pl1"}],
        places=[{"id": "pl1", "name": "镐京"}],
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["event"]["tp"] == 0


def test_relation_match_with_id_resolution() -> None:
    golden = _g(
        persons=[{"id": "per:a", "canonical_name": "周宣王"}],
        events=[{"id": "evt:a", "type": "战"}],
        relations=[
            {"kind": "event_participant", "event_id": "evt:a", "person_id": "per:a", "role": "主将"}
        ],
    )
    cands = _g(
        persons=[{"id": "p1", "canonical_name": "周宣王"}],
        events=[{"id": "e1", "type": "战"}],
        relations=[
            {"kind": "event_participant", "event_id": "e1", "person_id": "p1", "role": "主将"}
        ],
    )
    report = compute_pr(golden, cands)
    assert report["per_entity_type"]["relation"]["tp"] == 1
