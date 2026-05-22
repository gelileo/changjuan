"""Precision/Recall harness for golden vs. extracted candidates.

Matchers resolve cross-entity ID references (state_id, primary_place_id, event_id,
person_id, place_id) to entity *names* before comparing, because the golden uses
canonical-style ids ('sta:zhou', 'pla:qian-mu', etc.) while skill output uses
chunk-local ids ('s1', 'pl1', etc.). Name-based comparison bridges the two.

Phase-2 matcher (event): event requires type + (year ±1 OR place); strict-on-all-three
is too brittle for stage-3 candidates before linker consolidation. A slightly off
primary_place_id when type+year clearly match should not count as a wholly-different
event, and vice-versa. See Task 29 iteration, Path C.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _name_lookup(records: list[dict[str, Any]], name_field: str = "name") -> dict[str, str | None]:
    """Build {id: name} for a list of records that carry both."""
    return {r["id"]: r.get(name_field) for r in records if "id" in r}


def _person_name_lookup(persons: list[dict[str, Any]]) -> dict[str, str | None]:
    """Persons use canonical_name not name."""
    return {p["id"]: p.get("canonical_name") for p in persons if "id" in p}


def _event_name_lookup(events: list[dict[str, Any]]) -> dict[str, str | None]:
    """Events don't have a 'name' — use type as the stable identifier for
    relation-target comparison (sufficient for event_participant / event_place)."""
    return {e["id"]: e.get("type") for e in events if "id" in e}


def _resolve(id_value: str | None, lookup: dict[str, str | None]) -> str | None:
    """Translate an id → name via lookup. Returns the value unchanged if not in
    the lookup (e.g. already a canonical id, or chunk-local id whose target
    record is missing)."""
    if id_value is None:
        return None
    return lookup.get(id_value, id_value)


def _person_match_factory(
    state_lookup_g: dict[str, str | None],
    state_lookup_c: dict[str, str | None],
) -> Callable[[dict[str, Any], dict[str, Any]], bool]:
    def matcher(g: dict[str, Any], c: dict[str, Any]) -> bool:
        g_names = {g.get("canonical_name")} | {v.get("variant") for v in g.get("variants", [])}
        c_names = {c.get("canonical_name")} | {v.get("variant") for v in c.get("variants", [])}
        if not (g_names & c_names):
            return False
        g_state = _resolve(g.get("state_id"), state_lookup_g)
        c_state = _resolve(c.get("state_id"), state_lookup_c)
        if not (g_state == c_state or g_state is None or c_state is None):
            return False
        g_cat = g.get("social_category")
        c_cat = c.get("social_category")
        if g_cat is not None and c_cat is not None and g_cat != c_cat:
            return False
        return True

    return matcher


def _event_match_factory(
    place_lookup_g: dict[str, str | None],
    place_lookup_c: dict[str, str | None],
) -> Callable[[dict[str, Any], dict[str, Any]], bool]:
    def matcher(g: dict[str, Any], c: dict[str, Any]) -> bool:
        if g.get("type") != c.get("type"):
            return False
        g_place = _resolve(g.get("primary_place_id"), place_lookup_g)
        c_place = _resolve(c.get("primary_place_id"), place_lookup_c)
        place_match = g_place == c_place

        g_year = (g.get("date") or {}).get("year_bce")
        c_year = (c.get("date") or {}).get("year_bce")
        if g_year is not None and c_year is not None:
            year_match = abs(int(g_year) - int(c_year)) <= 1
        elif g_year is None and c_year is None:
            year_match = True
        else:
            year_match = False

        # type matched; need at least one of place / year to match.
        return place_match or year_match

    return matcher


def _place_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    return g.get("name") == c.get("name")


def _state_match(g: dict[str, Any], c: dict[str, Any]) -> bool:
    return g.get("name") == c.get("name")


def _relation_match_factory(
    person_g: dict[str, str | None],
    person_c: dict[str, str | None],
    event_g: dict[str, str | None],
    event_c: dict[str, str | None],
    place_g: dict[str, str | None],
    place_c: dict[str, str | None],
    state_g: dict[str, str | None],
    state_c: dict[str, str | None],
) -> Callable[[dict[str, Any], dict[str, Any]], bool]:
    """Match relations by (kind, resolved-name-tuple). All id-valued fields are
    resolved through their respective lookups before comparison."""

    def matcher(g: dict[str, Any], c: dict[str, Any]) -> bool:
        if g.get("kind") != c.get("kind"):
            return False
        kind = g["kind"]
        if kind == "event_participant":
            return (
                _resolve(g.get("event_id"), event_g) == _resolve(c.get("event_id"), event_c)
                and _resolve(g.get("person_id"), person_g) == _resolve(c.get("person_id"), person_c)
                and g.get("role") == c.get("role")
            )
        if kind == "event_place":
            return (
                _resolve(g.get("event_id"), event_g) == _resolve(c.get("event_id"), event_c)
                and _resolve(g.get("place_id"), place_g) == _resolve(c.get("place_id"), place_c)
                and g.get("role") == c.get("role")
            )
        if kind == "person_relation":
            return (
                _resolve(g.get("from_person_id"), person_g)
                == _resolve(c.get("from_person_id"), person_c)
                and _resolve(g.get("to_person_id"), person_g)
                == _resolve(c.get("to_person_id"), person_c)
                and (
                    g.get("kind_detail") == c.get("kind_detail")
                    or g.get("subkind") == c.get("subkind")
                    or g.get("role") == c.get("role")
                )
            )
        if kind == "person_state":
            return (
                _resolve(g.get("person_id"), person_g) == _resolve(c.get("person_id"), person_c)
                and _resolve(g.get("state_id"), state_g) == _resolve(c.get("state_id"), state_c)
                and g.get("role") == c.get("role")
            )
        if kind == "state_capital":
            return _resolve(g.get("state_id"), state_g) == _resolve(
                c.get("state_id"), state_c
            ) and _resolve(g.get("place_id"), place_g) == _resolve(c.get("place_id"), place_c)
        if kind == "event_relation":
            return (
                _resolve(g.get("from_event_id"), event_g)
                == _resolve(c.get("from_event_id"), event_c)
                and _resolve(g.get("to_event_id"), event_g)
                == _resolve(c.get("to_event_id"), event_c)
                and (
                    g.get("kind_detail") == c.get("kind_detail")
                    or g.get("subkind") == c.get("subkind")
                )
            )
        return False

    return matcher


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
    # Build name-lookups for both sides
    person_g = _person_name_lookup(golden["persons"])
    person_c = _person_name_lookup(candidates["persons"])
    state_g = _name_lookup(golden["states"])
    state_c = _name_lookup(candidates["states"])
    place_g = _name_lookup(golden["places"])
    place_c = _name_lookup(candidates["places"])
    event_g = _event_name_lookup(golden["events"])
    event_c = _event_name_lookup(candidates["events"])

    person_matcher = _person_match_factory(state_g, state_c)
    event_matcher = _event_match_factory(place_g, place_c)
    relation_matcher = _relation_match_factory(
        person_g,
        person_c,
        event_g,
        event_c,
        place_g,
        place_c,
        state_g,
        state_c,
    )

    return {
        "per_entity_type": {
            "person": _score(golden["persons"], candidates["persons"], person_matcher),
            "event": _score(golden["events"], candidates["events"], event_matcher),
            "place": _score(golden["places"], candidates["places"], _place_match),
            "state": _score(golden["states"], candidates["states"], _state_match),
            "relation": _score(golden["relations"], candidates["relations"], relation_matcher),
        },
    }
