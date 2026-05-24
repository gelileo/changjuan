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
    """Dates more than 150y apart trigger temporal_proximity = conflict.

    Strong overlap: a's canonical_name appears in b's variants[]."""
    a = _p(
        "X",
        variants=[{"variant": "Y", "kind": "别名"}],
        death_date={"year_bce": 950, "uncertainty": "point", "inference_kind": "era_only"},
    )
    b = _p(
        "Y",
        variants=[{"variant": "X", "kind": "本名"}],
        birth_date={"year_bce": 700, "uncertainty": "point", "inference_kind": "era_only"},
    )
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "strong"
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


def test_temporal_compatible_with_partial_overlap_adds_independently() -> None:
    """Temporal contributions apply regardless of variant_overlap level.

    Spec §4 walkthrough table (e.g., 召公奭↔召虎: partial + state same - temporal conflict)
    confirms temporal is an independent dimension.
    """
    # Partial overlap (shared variant string only, canonicals differ).
    a = _p(
        "X",
        variants=[{"variant": "shared", "kind": "别名"}],
        state_id="sta:jin",
        death_date={"year_bce": 650, "uncertainty": "point", "inference_kind": "era_only"},
    )
    b = _p(
        "Y",
        variants=[{"variant": "shared", "kind": "别名"}],
        state_id="sta:jin",
        death_date={"year_bce": 640, "uncertainty": "point", "inference_kind": "era_only"},
    )
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "partial"
    assert result["features"]["state_agreement"] == "same"
    assert result["features"]["temporal_proximity"] == "compatible"
    # +0.20 (partial) + 0.20 (state same) + 0.10 (temporal compatible) = 0.50
    assert abs(result["score"] - 0.50) < 1e-9


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


def test_strong_variant_same_state_diff_social_no_penalty() -> None:
    """Phase 7 follow-on: when name match is strong AND state agrees, a different
    social_category tracks role evolution (公子 → 君, 大夫 → 正卿, etc.) rather
    than identity mismatch. Skip the -0.10 penalty.

    Score: strong(+0.50) + state_same(+0.20) + clan one_null(±0) +
    social different (waived → ±0) + temporal unknown(±0) = 0.70 ≥ threshold.

    Surfaced by Ch.6-10 walks: 4 of 5 queued candidates were this exact pattern
    (公孙阏 noble→military, 公子佗 noble→royalty, 公子翚 noble→official,
    宋庄公 noble→royalty).
    """
    a = _p(
        "公子佗",
        state_id="sta:chen",
        social_category="noble",  # earlier chapter — as 公子
    )
    b = _p(
        "公子佗",
        state_id="sta:chen",
        social_category="royalty",  # later chapter — after 篡立
    )
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "strong"
    assert result["features"]["state_agreement"] == "same"
    assert result["features"]["social_category_agreement"] == "different"
    # 0.50 + 0.20 + 0 (clan one_null) + 0 (social diff waived) + 0 = 0.70
    assert abs(result["score"] - 0.70) < 1e-9


def test_diff_social_still_penalized_when_state_differs() -> None:
    """Regression guard: the social_category penalty must still apply when the
    waiver condition (strong + same state) is NOT satisfied. Otherwise two
    homonymous figures in different states would auto-merge on diff social.
    """
    a = _p(
        "公子元",
        state_id="sta:zheng",  # the 郑 公子元 from Ch.7
        social_category="noble",
    )
    b = _p(
        "公子元",
        state_id="sta:qi",  # a 齐 公子元 from Ch.8
        social_category="military",
    )
    result = person_match_score(a, b)
    assert result["features"]["state_agreement"] == "different"
    # 0.50 (strong) + 0 - 0.40 (state diff) + 0 (clan one_null) - 0.10 (social diff)
    # = 0.00 (clamped). Penalty fires; combined with state_diff = no merge.
    assert result["score"] == 0.0


def test_diff_social_still_penalized_with_partial_variant() -> None:
    """Regression guard: the waiver requires variant_overlap=strong specifically.
    A partial match should keep the -0.10 social-diff penalty.
    """
    a = _p(
        "A",
        variants=[{"variant": "shared", "kind": "别名"}],
        state_id="sta:jin",
        social_category="noble",
    )
    b = _p(
        "B",
        variants=[{"variant": "shared", "kind": "别名"}],
        state_id="sta:jin",
        social_category="royalty",
    )
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "partial"
    # 0.20 (partial) + 0.20 (state same) + 0 - 0.10 (social diff penalty still fires) = 0.30
    assert abs(result["score"] - 0.30) < 1e-9
