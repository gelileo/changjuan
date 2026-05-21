"""Canonical extraction-output JSON Schema.

Source of truth for both:
- the Python validator (pipeline/stage3_extract.py)
- the Claude Code skill's extraction-schema.yaml (regenerated via scripts/regen-extraction-schema)

If you change this file, also run scripts/regen-extraction-schema to update the YAML mirror.
The pre-commit hook enforces no diff between the two.
"""

from __future__ import annotations

PROMPT_TEMPLATE_VERSION = "v1"

_INFERENCE_KINDS: list[str] = [
    "explicit_reign_lu",
    "explicit_reign_zhou",
    "explicit_reign_other",
    "relative_to_prior_event",
    "era_only",
    "unknown",
]

_SOCIAL_CATEGORIES: list[str] = [
    "royalty",
    "noble",
    "official",
    "military",
    "religious",
    "clergy",
    "commoner",
    "servant",
    "foreign",
    "mythic",
    "unknown",
]

_CITATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["chunk_id", "paragraph", "span", "quote"],
    "additionalProperties": False,
    "properties": {
        "chunk_id": {"type": "string"},
        "paragraph": {"type": "integer", "minimum": 1},
        "span": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
        "quote": {"type": "string", "minLength": 1},
    },
}

_DATE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["inference_kind"],
    "additionalProperties": False,
    "properties": {
        "year_bce": {"type": ["integer", "null"]},
        "year_bce_end": {"type": ["integer", "null"]},
        "uncertainty": {"enum": ["point", "range", "circa"]},
        "original": {"type": "string"},
        "era": {"type": ["string", "null"]},
        "inference_kind": {"enum": _INFERENCE_KINDS},
        "relative_anchor_event_id": {"type": ["string", "null"]},
    },
}

_PERSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["id", "canonical_name", "citation", "justifications"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^p\d+$"},
        "canonical_name": {"type": "string", "minLength": 1},
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["variant", "kind"],
                "additionalProperties": False,
                "properties": {"variant": {"type": "string"}, "kind": {"type": "string"}},
            },
        },
        "gender": {"enum": ["male", "female", "unknown"]},
        "social_category": {"enum": _SOCIAL_CATEGORIES},
        "birth_date": _DATE_SCHEMA,
        "death_date": _DATE_SCHEMA,
        "state_id": {"type": ["string", "null"], "pattern": r"^(s\d+|sta:[\w\-]+)$"},
        "clan_name": {"type": ["string", "null"]},
        "citation": _CITATION_SCHEMA,
        "justifications": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}

_EVENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["id", "type", "citation", "justifications"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^e\d+$"},
        "type": {"type": "string", "minLength": 1},
        "date": _DATE_SCHEMA,
        "outcome": {"type": "string"},
        "summary": {"type": "string"},
        "primary_place_id": {"type": ["string", "null"], "pattern": r"^(pl\d+|pla:[\w\-]+)$"},
        "citation": _CITATION_SCHEMA,
        "justifications": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}

_PLACE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["id", "name", "citation", "justifications"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^pl\d+$"},
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string"},
        "lat": {"type": ["number", "null"]},
        "lon": {"type": ["number", "null"]},
        "coord_confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "modern_equiv": {"type": ["string", "null"]},
        "citation": _CITATION_SCHEMA,
        "justifications": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}

_STATE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["id", "name", "citation", "justifications"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^s\d+$"},
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string"},
        "ruling_clan": {"type": ["string", "null"]},
        "founded_date": _DATE_SCHEMA,
        "ended_date": _DATE_SCHEMA,
        "citation": _CITATION_SCHEMA,
        "justifications": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}

_RELATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["kind", "citation"],
    "additionalProperties": True,
    "properties": {
        "kind": {
            "enum": [
                "event_participant",
                "event_place",
                "event_relation",
                "person_relation",
                "person_state",
                "state_capital",
            ]
        },
        "citation": _CITATION_SCHEMA,
    },
}

EXTRACT_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["persons", "events", "places", "states", "relations"],
    "additionalProperties": False,
    "properties": {
        "persons": {"type": "array", "items": _PERSON_SCHEMA},
        "events": {"type": "array", "items": _EVENT_SCHEMA},
        "places": {"type": "array", "items": _PLACE_SCHEMA},
        "states": {"type": "array", "items": _STATE_SCHEMA},
        "relations": {"type": "array", "items": _RELATION_SCHEMA},
    },
}
