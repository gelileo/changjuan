"""Golden YAML loader. Reads tests/golden/<chapter>/*.yaml and validates structure
+ cross-references. Schema is the canonical schema's surface form."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_VALID_INFERENCE_KINDS = {
    "explicit_reign_lu",
    "explicit_reign_zhou",
    "explicit_reign_other",
    "relative_to_prior_event",
    "era_only",
    "unknown",
}

_REQUIRED_PERSON_FIELDS = ("id", "canonical_name", "citations")
_REQUIRED_EVENT_FIELDS = ("id", "type", "citations")
_REQUIRED_PLACE_FIELDS = ("id", "name")
_REQUIRED_STATE_FIELDS = ("id", "name")
_REQUIRED_CITATION_FIELDS = ("id", "chunk_id", "paragraph", "span", "quote")


class GoldenLoadError(Exception):
    """Raised when a golden YAML set fails validation."""


def _load_yaml(path: Path) -> list[Any]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        raise GoldenLoadError(f"{path.name}: top level must be a list")
    return data


def _require_fields(record: dict[str, Any], fields: tuple[str, ...], where: str) -> None:
    for f in fields:
        if f not in record:
            raise GoldenLoadError(
                f"{where} ({record.get('id', '<no id>')}): missing required field '{f}'"
            )


def _validate_date(date: dict[str, Any], where: str) -> None:
    if not isinstance(date, dict):
        raise GoldenLoadError(f"{where}: date must be a dict")
    kind = date.get("inference_kind")
    if kind is None:
        raise GoldenLoadError(f"{where}: date missing inference_kind")
    if kind not in _VALID_INFERENCE_KINDS:
        raise GoldenLoadError(f"{where}: invalid inference_kind '{kind}'")


def _validate_anchors_no_cycle(events: list[dict[str, Any]]) -> None:
    by_id = {e["id"]: e for e in events}
    for start in events:
        seen: set[str] = set()
        node = start
        while True:
            date = node.get("date") or {}
            anchor_id = date.get("relative_anchor_event_id")
            if anchor_id is None:
                break
            if anchor_id in seen or anchor_id == start["id"]:
                raise GoldenLoadError(
                    f"event {start['id']}: relative-anchor cycle through {anchor_id}"
                )
            seen.add(anchor_id)
            next_node = by_id.get(anchor_id)
            if next_node is None:
                raise GoldenLoadError(
                    f"event {start['id']}: dangling relative_anchor_event_id '{anchor_id}'"
                )
            node = next_node


def load_golden(chapter_dir: Path) -> dict[str, Any]:
    """Load all YAML files under chapter_dir/, validate, return typed dict."""
    chapter_dir = Path(chapter_dir)
    if not chapter_dir.is_dir():
        raise GoldenLoadError(f"not a directory: {chapter_dir}")

    persons = _load_yaml(chapter_dir / "persons.yaml")
    events = _load_yaml(chapter_dir / "events.yaml")
    places = _load_yaml(chapter_dir / "places.yaml")
    states = _load_yaml(chapter_dir / "states.yaml")
    citations = _load_yaml(chapter_dir / "citations.yaml")
    relations = _load_yaml(chapter_dir / "relations.yaml")

    for c in citations:
        _require_fields(c, _REQUIRED_CITATION_FIELDS, "citations")
    citation_ids = {c["id"] for c in citations}

    for p in persons:
        _require_fields(p, _REQUIRED_PERSON_FIELDS, "persons")
        for cid in p["citations"]:
            if cid not in citation_ids:
                raise GoldenLoadError(f"person {p['id']}: dangling citation '{cid}'")

    for e in events:
        _require_fields(e, _REQUIRED_EVENT_FIELDS, "events")
        if "date" in e:
            _validate_date(e["date"], f"event {e['id']}")
        for cid in e["citations"]:
            if cid not in citation_ids:
                raise GoldenLoadError(f"event {e['id']}: dangling citation '{cid}'")

    for pl in places:
        _require_fields(pl, _REQUIRED_PLACE_FIELDS, "places")
    for st in states:
        _require_fields(st, _REQUIRED_STATE_FIELDS, "states")

    _validate_anchors_no_cycle(events)

    return {
        "persons": persons,
        "events": events,
        "places": places,
        "states": states,
        "citations": citations,
        "relations": relations,
    }
