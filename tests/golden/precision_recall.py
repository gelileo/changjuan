"""Precision/Recall harness for golden vs. extracted candidates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _person_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    g_names = {g.get("canonical_name")} | {v.get("variant") for v in g.get("variants", [])}
    c_names = {c.get("canonical_name")} | {v.get("variant") for v in c.get("variants", [])}
    if not (g_names & c_names):
        return False
    g_state = g.get("state_id")
    c_state = c.get("state_id")
    if not (g_state == c_state or g_state is None or c_state is None):
        return False
    # social_category: when both have it set, they must agree
    g_cat = g.get("social_category")
    c_cat = c.get("social_category")
    if g_cat is not None and c_cat is not None and g_cat != c_cat:
        return False
    return True


def _event_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    if g.get("type") != c.get("type"):
        return False
    if g.get("primary_place_id") != c.get("primary_place_id"):
        return False
    g_year = (g.get("date") or {}).get("year_bce")
    c_year = (c.get("date") or {}).get("year_bce")
    if g_year is None and c_year is None:
        return True
    if g_year is None or c_year is None:
        return False
    return bool(abs(int(g_year) - int(c_year)) <= 1)


def _place_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    return g.get("name") == c.get("name")


def _state_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    return g.get("name") == c.get("name")


def _relation_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    keys = (
        "kind",
        "event_id",
        "person_id",
        "place_id",
        "from_person_id",
        "to_person_id",
        "state_id",
        "role",
    )
    return all(g.get(k) == c.get(k) for k in keys)


def _score(
    golden: list[dict[str, Any]],
    cands: list[dict[str, Any]],
    matcher: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    tp = 0
    matched_cands: set[int] = set()
    for g in golden:
        for idx, c in enumerate(cands):
            if idx in matched_cands:
                continue
            if matcher(g, c):
                tp += 1
                matched_cands.add(idx)
                break
    fp = len(cands) - len(matched_cands)
    fn = len(golden) - tp
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn}


def compute_pr(golden: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    return {
        "per_entity_type": {
            "person": _score(golden["persons"], candidates["persons"], _person_match),
            "event": _score(golden["events"], candidates["events"], _event_match),
            "place": _score(golden["places"], candidates["places"], _place_match),
            "state": _score(golden["states"], candidates["states"], _state_match),
            "relation": _score(golden["relations"], candidates["relations"], _relation_match),
        },
    }
