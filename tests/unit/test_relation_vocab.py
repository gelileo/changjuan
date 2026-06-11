from pipeline.stage7_load.relations import _valid_event_kinds, _valid_person_kinds


def test_valid_person_kinds_from_history_profile():
    kinds = _valid_person_kinds("history")
    assert "clan_member" in kinds and "ally" in kinds
    assert "恋慕" not in kinds


def test_valid_event_kinds_from_history_profile():
    assert _valid_event_kinds("history") == {"causes", "precedes", "related"}
