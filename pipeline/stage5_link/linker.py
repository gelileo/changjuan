"""Stage 5 (linker) orchestrator. Walks candidate_persons for a pipeline_run_id,
scores each against its candidate pool, and dispatches by threshold."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from pipeline import config
from pipeline.stage5_link.candidate_pool import _load_candidate, candidate_pool
from pipeline.stage5_link.scoring import person_match_score


def _denormalize_variants(conn: sqlite3.Connection, pipeline_run_id: str) -> None:
    """Populate candidate_person_variants from candidate_persons.variants_json
    for any candidate in this run that has variants_json but no structured rows yet.

    Phase 2's stage3_extract writes variants only to variants_json. The linker's
    candidate_pool reads from the structured table. This bridge runs idempotently
    at the start of every link pass.
    """
    rows = conn.execute(
        "SELECT id, variants_json FROM candidate_persons "
        "WHERE pipeline_run_id = ? AND variants_json IS NOT NULL AND variants_json != ''",
        (pipeline_run_id,),
    ).fetchall()
    for cand_id, raw in rows:
        try:
            variants = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(variants, list):
            continue
        # Skip if already denormalized.
        existing = conn.execute(
            "SELECT 1 FROM candidate_person_variants WHERE candidate_person_id = ? LIMIT 1",
            (cand_id,),
        ).fetchone()
        if existing is not None:
            continue
        for i, v in enumerate(variants):
            if not isinstance(v, dict):
                continue
            variant_str = v.get("variant")
            kind = v.get("kind", "别名")
            if not variant_str:
                continue
            conn.execute(
                "INSERT INTO candidate_person_variants (id, candidate_person_id, variant, kind) "
                "VALUES (?, ?, ?, ?)",
                (f"cv:{cand_id}:{i}", cand_id, variant_str, kind),
            )
    conn.commit()


def link_run(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    *,
    ignore_rejections: bool = False,
) -> dict[str, int]:
    """For each candidate_persons row in the run, find plausible match targets and
    dispatch by score:
      - score >= LINKER_AUTO_MERGE_THRESHOLD  → write match_target_id + audit_log
      - LINKER_QUEUE_THRESHOLD <= score < auto → write merge_candidates row
      - score < LINKER_QUEUE_THRESHOLD         → no action

    Phase 6: pairs previously dispositioned as rejected (rejected_merges) are
    skipped at the queue stage unless ignore_rejections=True.

    Returns stats: {candidates_processed, auto_merges, queued, skipped,
                    rejected_filter_skipped}.
    """
    from pipeline.stage5_link.fingerprint import candidate_fingerprint

    _denormalize_variants(conn, pipeline_run_id)

    stats: dict[str, int] = {
        "candidates_processed": 0,
        "auto_merges": 0,
        "queued": 0,
        "skipped": 0,
        "rejected_filter_skipped": 0,
    }

    rejected: set[tuple[str, str]] = set()
    if not ignore_rejections:
        rejected = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT canonical_id, candidate_fingerprint FROM rejected_merges"
            )
        }

    candidate_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM candidate_persons WHERE pipeline_run_id = ? ORDER BY id",
            (pipeline_run_id,),
        )
    ]

    # Track same-run siblings that were already matched as a target — skip them
    # to avoid double-matching (e.g. p1 matches p2, so p2 shouldn't also match p1).
    already_matched: set[str] = set()

    for cand_id in candidate_ids:
        stats["candidates_processed"] += 1

        if cand_id in already_matched:
            stats["skipped"] += 1
            continue

        me = _load_candidate(conn, cand_id)
        if me is None:
            stats["skipped"] += 1
            continue

        pool = candidate_pool(conn, cand_id, pipeline_run_id)
        if not pool:
            stats["skipped"] += 1
            continue

        best_target: dict[str, Any] | None = None
        best_score = 0.0
        best_features: dict[str, Any] = {}
        for target in pool:
            result = person_match_score(me, target)
            if result["score"] > best_score:
                best_score = result["score"]
                best_target = target
                best_features = result["features"]

        if best_target is None or best_score < config.LINKER_QUEUE_THRESHOLD:
            stats["skipped"] += 1
            continue

        if best_score >= config.LINKER_AUTO_MERGE_THRESHOLD:
            conn.execute(
                "UPDATE candidate_persons SET match_target_id = ? WHERE id = ?",
                (best_target["target_id"], cand_id),
            )
            conn.execute(
                "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
                "before_json, after_json, actor, at, pipeline_run_id) "
                "VALUES (?, 'candidate_persons', ?, 'match_target_id', 'set', "
                "?, ?, 'link@v1', datetime('now'), ?)",
                (
                    f"audit:{uuid.uuid4()}",
                    cand_id,
                    json.dumps({"value": None}),
                    json.dumps(
                        {
                            "value": best_target["target_id"],
                            "score": best_score,
                            "features": best_features,
                        },
                        ensure_ascii=False,
                    ),
                    pipeline_run_id,
                ),
            )
            stats["auto_merges"] += 1
            # If the target is a same-run candidate, mark it so we skip it later.
            if best_target.get("target_kind") == "candidate":
                already_matched.add(best_target["target_id"])
        else:
            # Queue case — apply Phase 6 reject-memory filter (canonical targets only).
            if best_target.get("target_kind") == "canonical":
                fp = candidate_fingerprint(
                    me["canonical_name"],
                    [v["variant"] for v in (me.get("variants") or [])],
                )
                if (best_target["target_id"], fp) in rejected:
                    stats["rejected_filter_skipped"] += 1
                    continue

            conn.execute(
                "INSERT INTO merge_candidates "
                "(id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, status) "
                "VALUES (?, 'person', ?, ?, ?, ?, 'open')",
                (
                    f"mc:{uuid.uuid4()}",
                    cand_id,
                    best_target["target_id"],
                    best_score,
                    json.dumps(
                        {"features": best_features, "score": best_score},
                        ensure_ascii=False,
                    ),
                ),
            )
            stats["queued"] += 1

    conn.commit()
    return stats
