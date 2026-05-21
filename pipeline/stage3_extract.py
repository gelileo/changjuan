"""Stage 3 — Validate skill-produced extraction records and (in Task 22) write candidate_* rows.

The validator is the contract the skill must satisfy. Records that violate
invariants are recorded in pipeline_runs.stats_json.invariant_violations and
excluded from the candidate write; the load continues with remaining records.
"""

from __future__ import annotations

import unicodedata
from typing import Any


class InvariantError(Exception):
    """Raised when an extracted record fails a stage-3 invariant."""


# Phase 2 only — explicit_reign_other is deferred (#4)
_PHASE2_INFERENCE_KINDS = frozenset(
    {
        "explicit_reign_lu",
        "explicit_reign_zhou",
        "relative_to_prior_event",
        "era_only",
        "unknown",
    }
)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def validate_record(
    record: dict[str, Any],
    chunk: dict[str, Any],
    *,
    declared_local_ids: set[str],
) -> None:
    """Apply the four static invariants to a single record. Raises on first violation.

    Invariants:
      1. Verbatim-quote: citation.quote is a substring (NFC-normalized) of chunk.text.
      2. Per-field justification: every scalar field's justification_quote is non-empty
         and substring of citation.quote (NFC-normalized).
      3. Chunk-id matches: citation.chunk_id == chunk.id.
      4. Date inference_kind allowlist: only Phase 2 kinds accepted (rejects
         explicit_reign_other and any unknown enum value).
      5. Chunk-local id resolution: cross-record FKs like primary_place_id / state_id
         that look like chunk-local ids (no ':' colon) must be in declared_local_ids.
    """
    citation = record.get("citation") or {}
    if citation.get("chunk_id") != chunk.get("id"):
        raise InvariantError(
            f"record {record.get('id')}: citation.chunk_id "
            f"'{citation.get('chunk_id')}' != target chunk '{chunk.get('id')}'"
        )

    quote = citation.get("quote", "")
    if not quote:
        raise InvariantError(f"record {record.get('id')}: citation.quote is empty")
    if _nfc(quote) not in _nfc(chunk.get("text", "")):
        raise InvariantError(
            f"record {record.get('id')}: verbatim-quote invariant failed "
            f"(quote not substring of chunk)"
        )

    justifications = record.get("justifications") or {}
    for field, j in justifications.items():
        if not j:
            raise InvariantError(f"record {record.get('id')}: justification for '{field}' is empty")
        if _nfc(j) not in _nfc(quote):
            raise InvariantError(
                f"record {record.get('id')}: justification for '{field}' "
                f"not substring of citation.quote"
            )

    # Date inference_kind allowlist (event.date, person.birth_date, person.death_date, etc.)
    for date_field in ("date", "birth_date", "death_date", "founded_date", "ended_date"):
        d = record.get(date_field)
        if isinstance(d, dict) and "inference_kind" in d:
            if d["inference_kind"] not in _PHASE2_INFERENCE_KINDS:
                raise InvariantError(
                    f"record {record.get('id')}: {date_field}.inference_kind "
                    f"'{d['inference_kind']}' not in Phase 2 allowlist"
                )

    # Chunk-local id integrity (e.g., primary_place_id='pl3' must be declared somewhere)
    for ref_field in ("primary_place_id", "state_id"):
        ref = record.get(ref_field)
        if ref is None:
            continue
        # Chunk-local ids look like 'p\d+', 'e\d+', 'pl\d+', 's\d+' (no colon).
        # Canonical ids contain ':'.
        if ":" not in str(ref) and ref not in declared_local_ids:
            raise InvariantError(
                f"record {record.get('id')}: {ref_field} '{ref}' " f"not in declared local ids"
            )
