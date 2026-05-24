"""Person matcher scoring formula. Pure function over two Person records.

Returns {"score": float in [0, 1], "features": dict of dimension classifications}.

Hard veto: variant_overlap == "none" → score 0.0 regardless of other signals.
Otherwise: weighted sum clamped to [0, 1].
"""

from __future__ import annotations

from typing import Any

# Temporal proximity bounds (years apart, BCE):
#   conflict triggers when one person's death is strictly MORE than this many years
#   before the other's birth.
_TEMPORAL_CONFLICT_GAP_YEARS = 150
# era proximity check — beyond this, the closest_gap branch downgrades to conflict.
_TEMPORAL_ERA_OVERLAP_YEARS = 200


def _variants_set(person: dict[str, Any]) -> set[str]:
    """Set of all name strings: canonical_name + all variant strings."""
    names: set[str] = set()
    canon = person.get("canonical_name")
    if canon:
        names.add(canon)
    for v in person.get("variants") or []:
        if isinstance(v, dict):
            variant = v.get("variant")
            if variant:
                names.add(variant)
    return names


def _classify_variant_overlap(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Return 'strong', 'partial', or 'none'."""
    a_canon = a.get("canonical_name")
    b_canon = b.get("canonical_name")
    a_variants = _variants_set(a)
    b_variants = _variants_set(b)

    # Strong: either canonical is in the other's variants[] OR the canonicals are identical.
    a_variant_names = {v.get("variant") for v in (a.get("variants") or []) if isinstance(v, dict)}
    b_variant_names = {v.get("variant") for v in (b.get("variants") or []) if isinstance(v, dict)}
    if a_canon and a_canon in b_variant_names:
        return "strong"
    if b_canon and b_canon in a_variant_names:
        return "strong"
    if a_canon and b_canon and a_canon == b_canon:
        return "strong"

    # Partial: any other name overlap
    if a_variants & b_variants:
        return "partial"
    return "none"


def _classify_field_agreement(a: dict[str, Any], b: dict[str, Any], field: str) -> str:
    """Return 'same', 'one_null', or 'different'."""
    av = a.get(field)
    bv = b.get(field)
    if av is None or bv is None:
        return "one_null"
    return "same" if av == bv else "different"


def _classify_temporal_proximity(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Return 'compatible', 'unknown', or 'conflict'.

    Conflict: one person's death is more than _TEMPORAL_CONFLICT_GAP_YEARS BEFORE
    the other's birth. BCE years count backward, so 'before' means HIGHER year_bce.

    Compatible: dates fall within _TEMPORAL_ERA_OVERLAP_YEARS of each other.
    """

    def _extract_years(rec: dict[str, Any]) -> list[int]:
        result: list[int] = []
        for key in ("birth_date", "death_date"):
            d = rec.get(key)
            if isinstance(d, dict):
                yr = d.get("year_bce")
                if isinstance(yr, int):
                    result.append(yr)
        return result

    a_years = _extract_years(a)
    b_years = _extract_years(b)

    if not a_years or not b_years:
        return "unknown"

    # Death-before-birth conflict checks.
    a_death = a.get("death_date") or {}
    b_birth = b.get("birth_date") or {}
    a_death_yr = a_death.get("year_bce") if isinstance(a_death, dict) else None
    b_birth_yr = b_birth.get("year_bce") if isinstance(b_birth, dict) else None
    if isinstance(a_death_yr, int) and isinstance(b_birth_yr, int):
        if a_death_yr - b_birth_yr > _TEMPORAL_CONFLICT_GAP_YEARS:
            return "conflict"
    b_death = b.get("death_date") or {}
    a_birth = a.get("birth_date") or {}
    b_death_yr = b_death.get("year_bce") if isinstance(b_death, dict) else None
    a_birth_yr = a_birth.get("year_bce") if isinstance(a_birth, dict) else None
    if isinstance(b_death_yr, int) and isinstance(a_birth_yr, int):
        if b_death_yr - a_birth_yr > _TEMPORAL_CONFLICT_GAP_YEARS:
            return "conflict"

    # General era proximity.
    closest_gap = min(abs(ay - by) for ay in a_years for by in b_years)
    if closest_gap > _TEMPORAL_ERA_OVERLAP_YEARS:
        return "conflict"
    return "compatible"


def person_match_score(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Score the likelihood that Person records a and b refer to the same person.

    Returns {"score": float [0,1], "features": {variant_overlap, state_agreement,
    clan_agreement, social_category_agreement, temporal_proximity}}.
    """
    features: dict[str, str] = {
        "variant_overlap": _classify_variant_overlap(a, b),
        "state_agreement": _classify_field_agreement(a, b, "state_id"),
        "clan_agreement": _classify_field_agreement(a, b, "clan_name"),
        "social_category_agreement": _classify_field_agreement(a, b, "social_category"),
        "temporal_proximity": _classify_temporal_proximity(a, b),
    }

    # Hard veto
    if features["variant_overlap"] == "none":
        return {"score": 0.0, "features": features}

    score = 0.0
    # Positive contributions
    if features["variant_overlap"] == "strong":
        score += 0.50
    elif features["variant_overlap"] == "partial":
        score += 0.20
    if features["state_agreement"] == "same":
        score += 0.20
    if features["clan_agreement"] == "same":
        score += 0.10
    if features["social_category_agreement"] == "same":
        score += 0.10
    if features["temporal_proximity"] == "compatible":
        score += 0.10

    # Negative contributions
    if features["state_agreement"] == "different":
        score -= 0.40
    if features["temporal_proximity"] == "conflict":
        score -= 0.30
    if features["clan_agreement"] == "different":
        score -= 0.20
    if features["social_category_agreement"] == "different":
        # Waiver: when name match is strong AND state agrees, a different
        # social_category usually tracks role evolution (公子 → 君,
        # 大夫 → 正卿, etc.) rather than identity mismatch. Skip the penalty
        # in that regime. Surfaced by Ch.6-10 walks (4 of 5 queued candidates
        # fit this pattern). The penalty still fires whenever the waiver
        # condition is not met — partial variants and cross-state name
        # collisions remain penalized.
        if not (features["variant_overlap"] == "strong" and features["state_agreement"] == "same"):
            score -= 0.10

    # Round to avoid float accumulation errors, then clamp to [0, 1]
    score = round(score, 10)
    score = max(0.0, min(1.0, score))

    return {"score": score, "features": features}
