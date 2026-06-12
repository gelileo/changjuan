import pytest

from pipeline.profile import (
    PROFILES,
    UnknownProfileError,
    default_group_type,
    derive_reader_capabilities,
    relation_kinds_for,
)


def test_history_profile_has_expected_etl_capabilities():
    assert PROFILES["history"]["capabilities"] == [
        "persons",
        "relations",
        "events",
        "chronology",
        "geography",
        "groups",
    ]


def test_history_person_relation_kinds_match_legacy_set():
    assert relation_kinds_for("history", "person") == {
        "parent",
        "child",
        "spouse",
        "sibling",
        "mentor",
        "ruler",
        "minister",
        "ally",
        "rival",
        "killed_by",
        "clan_member",
    }


def test_history_event_relation_kinds():
    assert relation_kinds_for("history", "event") == {"causes", "precedes", "related"}


def test_unknown_profile_raises():
    with pytest.raises(UnknownProfileError):
        relation_kinds_for("nonsuch", "person")


def test_derive_reader_capabilities_for_history():
    etl = ["persons", "relations", "events", "chronology", "geography", "groups"]
    assert derive_reader_capabilities(etl) == ["cast", "timeline", "groups"]


def test_derive_reader_capabilities_for_cast_like_set():
    etl = ["persons", "relations", "events", "groups", "themes"]
    assert derive_reader_capabilities(etl) == ["cast", "groups", "themes"]


def test_derive_reader_capabilities_is_order_stable():
    etl = ["groups", "themes", "persons", "chronology"]
    assert derive_reader_capabilities(etl) == ["cast", "timeline", "groups", "themes"]


def test_relation_kinds_for_rejects_unknown_relation():
    with pytest.raises(ValueError):
        relation_kinds_for("history", "typo")


def test_relation_kinds_for_returns_a_copy_not_the_live_set():
    kinds = relation_kinds_for("history", "person")
    kinds.add("invented")
    assert "invented" not in relation_kinds_for("history", "person")


def test_cast_profile_capabilities():
    assert PROFILES["cast"]["capabilities"] == [
        "persons",
        "relations",
        "events",
        "groups",
        "themes",
    ]


def test_cast_default_group_type_is_clan():
    assert default_group_type("cast") == "clan"


def test_cast_person_relation_vocab_is_domestic():
    kinds = relation_kinds_for("cast", "person")
    assert {"spouse", "master", "servant", "romantic", "concubine"} <= kinds
    assert "ruler" not in kinds and "killed_by" not in kinds


def test_cast_derives_reader_caps_without_timeline():
    assert derive_reader_capabilities(
        list(PROFILES["cast"]["capabilities"])  # type: ignore
    ) == [
        "cast",
        "groups",
        "themes",
    ]


def test_cast_vocab_includes_native_hlm_kinds():
    # Added from the kg-hongloumeng taxonomy; modern labels excluded.
    kinds = relation_kinds_for("cast", "person")
    assert {"consort", "subject", "neighbor", "colleague", "patron"} <= kinds
    # modern/anachronistic labels must NOT be kinds (they belong in relation_detail or nowhere)
    assert "男友" not in kinds and "雇主" not in kinds
