"""Person matcher scoring formula — pure function over two Person records."""

from __future__ import annotations

from typing import Any

from pipeline.stage5_link.scoring import person_match_score


def _p(name: str, **fields: Any) -> dict[str, Any]:
    """Minimal Person record builder."""
    rec: dict[str, Any] = {"canonical_name": name}
    rec.update(fields)
    return rec


def test_hard_veto_when_no_variant_overlap() -> None:
    a = _p("重耳", state_id="sta:jin", clan_name="姬", social_category="noble")
    b = _p("管仲", state_id="sta:jin", clan_name="姬", social_category="noble")
    result = person_match_score(a, b)
    assert result["score"] == 0.0
    assert result["features"]["variant_overlap"] == "none"


def test_strong_variant_overlap_canonical_in_other_variants() -> None:
    """Canonical name of A appears in B's variants[] → strong variant overlap."""
    a = _p("重耳")
    b = _p("晋文公", variants=[{"variant": "重耳", "kind": "本名"}])
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "strong"
    assert result["score"] == 0.50  # only strong variant contributes; no other signals


def test_partial_variant_overlap_non_canonical_match() -> None:
    """Non-canonical variants match → partial overlap."""
    a = _p("X", variants=[{"variant": "shared_alias", "kind": "别名"}])
    b = _p("Y", variants=[{"variant": "shared_alias", "kind": "别名"}])
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "partial"
    assert result["score"] == 0.20


def test_full_perfect_match() -> None:
    """Strong variant + state same + clan same + category same + temporal compatible."""
    a = _p(
        "重耳",
        variants=[{"variant": "公子重耳", "kind": "别名"}],
        state_id="sta:jin",
        clan_name="姬",
        social_category="noble",
        death_date={
            "year_bce": 628,
            "uncertainty": "point",
            "inference_kind": "explicit_reign_other",
        },
    )
    b = _p(
        "公子重耳",
        variants=[{"variant": "重耳", "kind": "本名"}],
        state_id="sta:jin",
        clan_name="姬",
        social_category="noble",
        death_date={
            "year_bce": 628,
            "uncertainty": "point",
            "inference_kind": "explicit_reign_other",
        },
    )
    result = person_match_score(a, b)
    assert result["score"] == 1.00  # clamped
    assert result["features"]["state_agreement"] == "same"
    assert result["features"]["clan_agreement"] == "same"
    assert result["features"]["social_category_agreement"] == "same"
    assert result["features"]["temporal_proximity"] == "compatible"


def test_state_disagreement_subtracts() -> None:
    a = _p("重耳", variants=[{"variant": "公子重耳", "kind": "别名"}], state_id="sta:jin")
    b = _p("公子重耳", state_id="sta:wei")  # different state
    result = person_match_score(a, b)
    assert result["features"]["state_agreement"] == "different"
    # +0.50 (strong variant) - 0.40 (state diff) = 0.10
    assert abs(result["score"] - 0.10) < 1e-9


def test_clan_disagreement_subtracts() -> None:
    a = _p(
        "X", variants=[{"variant": "shared", "kind": "别名"}], state_id="sta:jin", clan_name="姬"
    )
    b = _p(
        "Y", variants=[{"variant": "shared", "kind": "别名"}], state_id="sta:jin", clan_name="姚"
    )  # different clan
    result = person_match_score(a, b)
    assert result["features"]["clan_agreement"] == "different"
    # +0.20 (partial variant) + 0.20 (state) - 0.20 (clan diff) = 0.20
    assert abs(result["score"] - 0.20) < 1e-9


def test_temporal_conflict_subtracts() -> None:
    """Dates more than 150y apart trigger temporal_proximity = conflict."""
    a = _p(
        "X",
        variants=[{"variant": "shared", "kind": "别名"}],
        death_date={"year_bce": 950, "uncertainty": "point", "inference_kind": "era_only"},
    )
    b = _p(
        "Y",
        variants=[{"variant": "shared", "kind": "别名"}],
        birth_date={"year_bce": 700, "uncertainty": "point", "inference_kind": "era_only"},
    )
    result = person_match_score(a, b)
    assert result["features"]["temporal_proximity"] == "conflict"
    # +0.50 (strong) - 0.30 (temporal conflict) = 0.20
    assert abs(result["score"] - 0.20) < 1e-9


def test_one_null_does_not_penalize() -> None:
    """When state_id missing on one side, no penalty (insufficient evidence)."""
    a = _p("X", variants=[{"variant": "shared", "kind": "别名"}], state_id="sta:jin")
    b = _p("Y", variants=[{"variant": "shared", "kind": "别名"}])  # no state_id
    result = person_match_score(a, b)
    assert result["features"]["state_agreement"] == "one_null"
    assert abs(result["score"] - 0.20) < 1e-9  # just the partial variant


def test_score_clamps_to_zero() -> None:
    """Heavy negative contributions should clamp at 0, not go negative."""
    a = _p(
        "X",
        variants=[{"variant": "shared", "kind": "别名"}],
        state_id="sta:jin",
        clan_name="姬",
        social_category="noble",
        death_date={"year_bce": 950, "uncertainty": "point", "inference_kind": "era_only"},
    )
    b = _p(
        "Y",
        variants=[{"variant": "shared", "kind": "别名"}],
        state_id="sta:wei",
        clan_name="姚",
        social_category="royalty",
        birth_date={"year_bce": 700, "uncertainty": "point", "inference_kind": "era_only"},
    )
    result = person_match_score(a, b)
    # +0.20 - 0.40 - 0.20 - 0.10 - 0.30 = -0.80 → clamp to 0.0
    assert result["score"] == 0.0


def test_score_clamps_to_one() -> None:
    """All-positive contributions sum to 1.00 exactly; verify scoring reaches that value."""
    a = _p(
        "重耳",
        variants=[{"variant": "公子重耳", "kind": "别名"}],
        state_id="sta:jin",
        clan_name="姬",
        social_category="noble",
        death_date={
            "year_bce": 628,
            "uncertainty": "point",
            "inference_kind": "explicit_reign_other",
        },
    )
    b = _p(
        "公子重耳",
        variants=[{"variant": "重耳", "kind": "本名"}],
        state_id="sta:jin",
        clan_name="姬",
        social_category="noble",
        death_date={
            "year_bce": 628,
            "uncertainty": "point",
            "inference_kind": "explicit_reign_other",
        },
    )
    result = person_match_score(a, b)
    assert result["score"] == 1.0
