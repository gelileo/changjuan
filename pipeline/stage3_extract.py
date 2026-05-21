"""Stage 3 — Validate skill-produced extraction records and write candidate_* rows.

The validator is the contract the skill must satisfy. Records that violate
invariants are recorded in pipeline_runs.stats_json.invariant_violations and
excluded from the candidate write; the load continues with remaining records.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from pipeline.confidence import score_extraction_record
from pipeline.dates import resolve_relative_dates
from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA


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


def load_extraction(
    canonical_conn: sqlite3.Connection,
    *,
    corpus_conn: sqlite3.Connection,
    chapter_num: int,
    extraction_file: Path,
    prompt_version: str,
    pipeline_run_id: str,
) -> dict[str, Any]:
    """Validate the skill's YAML output and write candidate_* rows.

    Schema-validates the YAML payload, runs per-record invariants, resolves
    within-chunk relative dates, writes candidate_* rows for all five entity
    kinds and all six relation kinds.  Records that fail invariant checks are
    skipped; their violation messages are collected in stats["invariant_violations"].

    Returns a stats dict with per-kind written counts + an invariant_violations list.
    """
    payload: dict[str, Any] = yaml.safe_load(extraction_file.read_text(encoding="utf-8"))
    jsonschema.validate(payload, EXTRACT_OUTPUT_SCHEMA)

    # Build chunk lookup for this chapter
    chunks: dict[str, dict[str, Any]] = {
        row[0]: {"id": row[0], "text": row[1]}
        for row in corpus_conn.execute(
            "SELECT c.id, c.text FROM chunks c "
            "JOIN documents d ON c.document_id = d.id "
            "WHERE d.chapter_num = ?",
            (chapter_num,),
        ).fetchall()
    }

    declared_local_ids: set[str] = (
        {p["id"] for p in payload["persons"]}
        | {e["id"] for e in payload["events"]}
        | {pl["id"] for pl in payload["places"]}
        | {st["id"] for st in payload["states"]}
    )

    stats: dict[str, Any] = {
        "persons_written": 0,
        "events_written": 0,
        "places_written": 0,
        "states_written": 0,
        "relations_written": 0,
        "invariant_violations": [],
    }

    # Resolve within-chunk relative dates on events before we write them.
    payload["events"] = resolve_relative_dates(payload["events"], conn=canonical_conn)

    def _validate(kind: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for rec in records:
            chunk = chunks.get((rec.get("citation") or {}).get("chunk_id", ""))
            if chunk is None:
                stats["invariant_violations"].append(f"{kind} {rec.get('id')}: unknown chunk_id")
                continue
            try:
                validate_record(rec, chunk, declared_local_ids=declared_local_ids)
                kept.append(rec)
            except InvariantError as exc:
                stats["invariant_violations"].append(str(exc))
        return kept

    persons = _validate("person", payload["persons"])
    events = _validate("event", payload["events"])
    places = _validate("place", payload["places"])
    states = _validate("state", payload["states"])

    # Relations: validate citation chunk_id only (no per-field justifications)
    relations: list[dict[str, Any]] = []
    for r in payload["relations"]:
        if (r.get("citation") or {}).get("chunk_id") in chunks:
            relations.append(r)
        else:
            stats["invariant_violations"].append(f"relation/{r.get('kind')}: unknown chunk_id")

    # Build a lookup from chunk-local id → candidate db id (set after each write)
    local_to_cand: dict[str, str] = {}

    # ===== persons =====
    for p in persons:
        cand_id = f"cand:per:{pipeline_run_id}:{p['id']}"
        scoring = dict(p, _scalar_fields=["canonical_name", "gender", "state_id", "clan_name"])
        conf = score_extraction_record(scoring)
        birth_json = json.dumps(p["birth_date"]) if p.get("birth_date") else None
        death_json = json.dumps(p["death_date"]) if p.get("death_date") else None
        variants_json = json.dumps(p["variants"], ensure_ascii=False) if p.get("variants") else None
        canonical_conn.execute(
            "INSERT INTO candidate_persons "
            "(id, canonical_name, gender, birth_date_json, death_date_json, notes, "
            " state_id, clan_name, social_category, variants_json, "
            " confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cand_id,
                p["canonical_name"],
                p.get("gender"),
                birth_json,
                death_json,
                p.get("notes"),
                p.get("state_id"),
                p.get("clan_name"),
                p.get("social_category"),
                variants_json,
                conf,
                pipeline_run_id,
                p["citation"]["chunk_id"],
                p["citation"]["quote"],
            ),
        )
        local_to_cand[p["id"]] = cand_id
        stats["persons_written"] += 1

    # ===== events =====
    for e in events:
        cand_id = f"cand:evt:{pipeline_run_id}:{e['id']}"
        scoring = dict(e, _scalar_fields=["type", "outcome", "summary", "primary_place_id"])
        conf = score_extraction_record(scoring)
        date_json = json.dumps(e["date"]) if e.get("date") else None
        canonical_conn.execute(
            "INSERT INTO candidate_events "
            "(id, type, date_json, outcome, summary, primary_place_id, "
            " confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cand_id,
                e["type"],
                date_json,
                e.get("outcome"),
                e.get("summary"),
                e.get("primary_place_id"),
                conf,
                pipeline_run_id,
                e["citation"]["chunk_id"],
                e["citation"]["quote"],
            ),
        )
        local_to_cand[e["id"]] = cand_id
        stats["events_written"] += 1

    # ===== places =====
    for pl in places:
        cand_id = f"cand:pla:{pipeline_run_id}:{pl['id']}"
        scoring = dict(pl, _scalar_fields=["name", "type", "modern_equiv"])
        conf = score_extraction_record(scoring)
        canonical_conn.execute(
            "INSERT INTO candidate_places "
            "(id, name, type, lat, lon, coord_confidence, modern_equiv, "
            " confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cand_id,
                pl["name"],
                pl.get("type"),
                pl.get("lat"),
                pl.get("lon"),
                pl.get("coord_confidence"),
                pl.get("modern_equiv"),
                conf,
                pipeline_run_id,
                pl["citation"]["chunk_id"],
                pl["citation"]["quote"],
            ),
        )
        local_to_cand[pl["id"]] = cand_id
        stats["places_written"] += 1

    # ===== states =====
    for st in states:
        cand_id = f"cand:sta:{pipeline_run_id}:{st['id']}"
        scoring = dict(st, _scalar_fields=["name", "type", "ruling_clan"])
        conf = score_extraction_record(scoring)
        founded_json = json.dumps(st["founded_date"]) if st.get("founded_date") else None
        ended_json = json.dumps(st["ended_date"]) if st.get("ended_date") else None
        canonical_conn.execute(
            "INSERT INTO candidate_states "
            "(id, name, founded_date_json, ended_date_json, ruling_clan, type, "
            " confidence, pipeline_run_id, chunk_id, quote) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cand_id,
                st["name"],
                founded_json,
                ended_json,
                st.get("ruling_clan"),
                st.get("type"),
                conf,
                pipeline_run_id,
                st["citation"]["chunk_id"],
                st["citation"]["quote"],
            ),
        )
        local_to_cand[st["id"]] = cand_id
        stats["states_written"] += 1

    # ===== relations =====
    # Map chunk-local id → candidate db id; fall back to the raw value for
    # any id that was already canonical (contains ':').
    def _resolve_id(raw: str) -> str:
        return local_to_cand.get(raw, raw)

    for r in relations:
        kind = r["kind"]

        if kind == "event_participant":
            ev_cand = _resolve_id(r["event_id"])
            per_cand = _resolve_id(r["person_id"])
            canonical_conn.execute(
                "INSERT OR IGNORE INTO candidate_event_participants "
                "(candidate_event_id, candidate_person_id, role, role_detail, "
                " pipeline_run_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    ev_cand,
                    per_cand,
                    r.get("role", ""),
                    r.get("role_detail"),
                    pipeline_run_id,
                ),
            )

        elif kind == "event_place":
            ev_cand = _resolve_id(r["event_id"])
            pl_cand = _resolve_id(r["place_id"])
            canonical_conn.execute(
                "INSERT OR IGNORE INTO candidate_event_places "
                "(candidate_event_id, candidate_place_id, role, pipeline_run_id) "
                "VALUES (?, ?, ?, ?)",
                (
                    ev_cand,
                    pl_cand,
                    r.get("role", ""),
                    pipeline_run_id,
                ),
            )

        elif kind == "event_relation":
            from_cand = _resolve_id(r["from_event_id"])
            to_cand = _resolve_id(r["to_event_id"])
            canonical_conn.execute(
                "INSERT OR IGNORE INTO candidate_event_relations "
                "(from_candidate_event_id, to_candidate_event_id, kind, "
                " pipeline_run_id) "
                "VALUES (?, ?, ?, ?)",
                (
                    from_cand,
                    to_cand,
                    r.get("relation_kind", "related"),
                    pipeline_run_id,
                ),
            )

        elif kind == "person_relation":
            from_cand = _resolve_id(r["from_person_id"])
            to_cand = _resolve_id(r["to_person_id"])
            date_json = json.dumps(r["date"]) if r.get("date") else None
            canonical_conn.execute(
                "INSERT OR IGNORE INTO candidate_person_relations "
                "(from_candidate_person_id, to_candidate_person_id, kind, "
                " date_json, pipeline_run_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    from_cand,
                    to_cand,
                    r.get("relation_kind", ""),
                    date_json,
                    pipeline_run_id,
                ),
            )

        elif kind == "person_state":
            per_cand = _resolve_id(r["person_id"])
            st_cand = _resolve_id(r["state_id"])
            from_date_json = json.dumps(r["from_date"]) if r.get("from_date") else None
            to_date_json = json.dumps(r["to_date"]) if r.get("to_date") else None
            canonical_conn.execute(
                "INSERT OR IGNORE INTO candidate_person_states "
                "(candidate_person_id, candidate_state_id, role, "
                " from_date_json, to_date_json, pipeline_run_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    per_cand,
                    st_cand,
                    r.get("role", ""),
                    from_date_json,
                    to_date_json,
                    pipeline_run_id,
                ),
            )

        elif kind == "state_capital":
            # No candidate_state_capitals staging table in current schema.
            # Record the count but skip the DB write (matches load_candidate_state_capitals stub).
            pass

        stats["relations_written"] += 1

    # Record the pipeline_runs row
    canonical_conn.execute(
        "INSERT INTO pipeline_runs "
        "(id, stage, started_at, ended_at, prompt_version, model, "
        " scope_json, stats_json, stats_schema_version) "
        "VALUES (?, 'extract-load', datetime('now'), datetime('now'), "
        "        ?, 'claude-code', ?, ?, 1)",
        (
            pipeline_run_id,
            prompt_version,
            json.dumps({"chapter": chapter_num}),
            json.dumps(stats),
        ),
    )
    canonical_conn.commit()
    return stats
