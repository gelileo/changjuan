"""Stage 3 invariants: verbatim-quote, per-field justification substring,
chunk-local id resolution, citation chunk_id FK, inference_kind allowlist."""

from __future__ import annotations

from typing import Any

import pytest

from pipeline.stage3_extract import InvariantError, validate_record


def _chunk(text: str = "重耳奔狄") -> dict[str, Any]:
    return {"id": "chk:ch01-001", "text": text}


def _person_record(
    quote: str = "重耳", justifications: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "id": "p1",
        "canonical_name": "重耳",
        "citation": {"chunk_id": "chk:ch01-001", "paragraph": 1, "span": [0, 2], "quote": quote},
        "justifications": justifications or {"canonical_name": "重耳"},
    }


def test_verbatim_quote_passes_when_substring() -> None:
    validate_record(_person_record(), _chunk(), declared_local_ids={"p1"})


def test_verbatim_quote_fails_when_not_substring() -> None:
    rec = _person_record(quote="不存在")
    with pytest.raises(InvariantError, match="verbatim"):
        validate_record(rec, _chunk(), declared_local_ids={"p1"})


def test_justification_must_be_non_empty() -> None:
    rec = _person_record(quote="重耳", justifications={"canonical_name": ""})
    with pytest.raises(InvariantError, match="justification"):
        validate_record(rec, _chunk(), declared_local_ids={"p1"})


def test_justification_must_be_substring_of_quote() -> None:
    rec = _person_record(quote="重耳", justifications={"canonical_name": "晋文公"})
    with pytest.raises(InvariantError, match="justification"):
        validate_record(rec, _chunk(), declared_local_ids={"p1"})


def test_chunk_id_mismatch_fails() -> None:
    rec = _person_record()
    rec["citation"]["chunk_id"] = "chk:other"
    with pytest.raises(InvariantError, match="chunk_id"):
        validate_record(rec, _chunk(), declared_local_ids={"p1"})
