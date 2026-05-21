"""The canonical extraction schema is the single source of truth shared between
the Claude Code skill (.claude/skills/changjuan-extract/extraction-schema.yaml,
regenerated from this Python dict) and the Python validator."""

import jsonschema
import pytest

from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA, PROMPT_TEMPLATE_VERSION


def _valid_minimal():
    return {
        "persons": [
            {
                "id": "p1",
                "canonical_name": "重耳",
                "citation": {
                    "chunk_id": "chk:ch01-001",
                    "paragraph": 1,
                    "span": [0, 4],
                    "quote": "重耳",
                },
                "justifications": {"canonical_name": "重耳"},
            }
        ],
        "events": [],
        "places": [],
        "states": [],
        "relations": [],
    }


def test_minimal_valid_passes():
    jsonschema.validate(_valid_minimal(), EXTRACT_OUTPUT_SCHEMA)


def test_missing_top_level_required_fails():
    bad = _valid_minimal()
    del bad["events"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, EXTRACT_OUTPUT_SCHEMA)


def test_person_missing_citation_fails():
    bad = _valid_minimal()
    del bad["persons"][0]["citation"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, EXTRACT_OUTPUT_SCHEMA)


def test_event_with_date_inference_kind_validated():
    payload = _valid_minimal()
    payload["events"].append(
        {
            "id": "e1",
            "type": "战",
            "date": {
                "inference_kind": "explicit_reign_zhou",
                "year_bce": 771,
                "original": "周幽王十一年",
                "uncertainty": "point",
            },
            "citation": {
                "chunk_id": "chk:1",
                "paragraph": 5,
                "span": [0, 10],
                "quote": "周幽王十一年",
            },
            "justifications": {"type": "战"},
        }
    )
    jsonschema.validate(payload, EXTRACT_OUTPUT_SCHEMA)


def test_event_with_invalid_inference_kind_fails():
    payload = _valid_minimal()
    payload["events"].append(
        {
            "id": "e1",
            "type": "战",
            "date": {"inference_kind": "bogus", "original": "x", "uncertainty": "point"},
            "citation": {"chunk_id": "chk:1", "paragraph": 5, "span": [0, 5], "quote": "x"},
            "justifications": {"type": "战"},
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, EXTRACT_OUTPUT_SCHEMA)


def test_prompt_template_version_constant_exists():
    assert PROMPT_TEMPLATE_VERSION.startswith("v")


def test_person_accepts_valid_social_category():
    payload = _valid_minimal()
    payload["persons"][0]["social_category"] = "royalty"
    jsonschema.validate(payload, EXTRACT_OUTPUT_SCHEMA)


def test_person_rejects_invalid_social_category():
    payload = _valid_minimal()
    payload["persons"][0]["social_category"] = "wizard"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, EXTRACT_OUTPUT_SCHEMA)
