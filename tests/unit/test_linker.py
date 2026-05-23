"""link_run orchestrator — walks candidate_persons, scores against pool, dispatches by threshold."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline import config
from pipeline.db import open_canonical_db
from pipeline.stage5_link.linker import link_run


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_state(c: sqlite3.Connection, state_id: str) -> None:
    """Insert the state row if needed (for FK satisfaction)."""
    c.execute(
        "INSERT OR IGNORE INTO states (id, name, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, 'auto', 0.9, 'run:setup')",
        (state_id, state_id),
    )
    c.commit()


def _seed_canonical(
    c: sqlite3.Connection,
    *,
    person_id: str,
    name: str,
    state_id: str | None = None,
    social_category: str | None = None,
    variants: list[tuple[str, str]] | None = None,
) -> None:
    if state_id is not None:
        _seed_state(c, state_id)
    c.execute(
        "INSERT INTO persons "
        "(id, canonical_name, state_id, social_category, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, ?, 'auto', 0.9, 'run:setup')",
        (person_id, name, state_id, social_category),
    )
    for v, k in variants or []:
        c.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind) VALUES (?, ?, ?, ?)",
            (f"pv:{person_id}:{v}", person_id, v, k),
        )
    c.commit()


def _seed_candidate(
    c: sqlite3.Connection,
    *,
    run_id: str,
    cand_id: str,
    name: str,
    state_id: str | None = None,
    social_category: str | None = None,
    clan_name: str | None = None,
    variants: list[tuple[str, str]] | None = None,
) -> None:
    if state_id is not None:
        _seed_state(c, state_id)
    variants_json = (
        json.dumps([{"variant": v, "kind": k} for v, k in (variants or [])], ensure_ascii=False)
        if variants
        else None
    )
    c.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, state_id, social_category, clan_name, variants_json, "
        " chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, 'chk:t', '', 0.9, ?)",
        (cand_id, name, state_id, social_category, clan_name, variants_json, run_id),
    )
    c.commit()


def test_auto_merge_writes_match_target_id_and_audit(conn: sqlite3.Connection) -> None:
    """Strong variant + state same + social same → score ≥ 0.75 → auto-merge."""
    _seed_canonical(
        conn,
        person_id="per:jin-wen-gong",
        name="晋文公",
        state_id="sta:jin",
        social_category="royalty",
        variants=[("重耳", "本名"), ("文公", "谥号")],
    )
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",
        state_id="sta:jin",
        social_category="royalty",
    )

    stats = link_run(conn, "run:1")
    assert stats["auto_merges"] == 1
    assert stats["queued"] == 0

    row = conn.execute(
        "SELECT match_target_id FROM candidate_persons WHERE id='cand:per:run:1:p1'"
    ).fetchone()
    assert row[0] == "per:jin-wen-gong"

    audit = conn.execute(
        "SELECT actor FROM audit_log WHERE entity_id='cand:per:run:1:p1'"
    ).fetchall()
    assert any(r[0] == "link@v1" for r in audit)


def test_queue_writes_merge_candidates_row(conn: sqlite3.Connection) -> None:
    """Mid-score (strong variant + state one_null, no social) lands in queue.

    Score: strong(+0.50) + state one_null(±0) = 0.50, which is in [0.40, 0.75).
    """
    _seed_canonical(
        conn,
        person_id="per:zhong-er-jin",
        name="重耳",
        # No state_id: produces state one_null (no bonus, no penalty)
        variants=[("公子重耳", "别名")],
    )
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",
        state_id="sta:wei",
        variants=[("公子重耳", "别名")],
    )

    stats = link_run(conn, "run:1")
    assert stats["auto_merges"] == 0
    assert stats["queued"] == 1

    mc = conn.execute(
        "SELECT score, surface_features_json FROM merge_candidates WHERE kind='person'"
    ).fetchall()
    assert len(mc) == 1
    assert mc[0][0] >= config.LINKER_QUEUE_THRESHOLD
    assert mc[0][0] < config.LINKER_AUTO_MERGE_THRESHOLD


def test_skip_leaves_no_trace(conn: sqlite3.Connection) -> None:
    """No variant overlap → hard veto → no action."""
    _seed_canonical(conn, person_id="per:other", name="仲山甫")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")

    stats = link_run(conn, "run:1")
    assert stats["skipped"] == 1
    assert stats["auto_merges"] == 0
    assert stats["queued"] == 0


def test_cross_run_chain_resolution(conn: sqlite3.Connection) -> None:
    """When a candidate's best match is a same-run sibling candidate, match_target_id
    points at that sibling (Stage 7's chain helper resolves at load time).

    Score: strong(+0.50) + state_same(+0.20) + social_same(+0.10) = 0.80 >= 0.75 → auto-merge.
    """
    _seed_state(conn, "sta:jin")
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",
        state_id="sta:jin",
        social_category="royalty",
        variants=[("公子重耳", "别名")],
    )
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p2",
        name="公子重耳",
        state_id="sta:jin",
        social_category="royalty",
        variants=[("重耳", "本名")],
    )

    stats = link_run(conn, "run:1")
    matched = conn.execute(
        "SELECT id, match_target_id FROM candidate_persons WHERE pipeline_run_id='run:1' "
        "AND match_target_id IS NOT NULL"
    ).fetchall()
    assert len(matched) == 1
    matched_id, target = matched[0]
    assert target in ("cand:per:run:1:p1", "cand:per:run:1:p2")
    assert target != matched_id

    # Stats reconciliation: 2 processed = 1 auto_merge + 1 sibling-skip
    assert stats["candidates_processed"] == 2
    assert stats["auto_merges"] == 1
    assert stats["skipped"] == 1
    assert stats["queued"] == 0
    assert stats["candidates_processed"] == (
        stats["auto_merges"] + stats["queued"] + stats["skipped"]
    )


def test_returns_stats_dict(conn: sqlite3.Connection) -> None:
    stats = link_run(conn, "run:empty")
    assert set(stats.keys()) == {
        "candidates_processed",
        "auto_merges",
        "queued",
        "skipped",
        "rejected_filter_skipped",
        "already_open_skipped",
    }


def test_variants_denormalized_from_variants_json(conn: sqlite3.Connection) -> None:
    """link_run denormalizes variants_json → candidate_person_variants on entry."""
    _seed_canonical(
        conn,
        person_id="per:jin-wen-gong",
        name="晋文公",
        state_id="sta:jin",
        variants=[("重耳", "本名")],
    )
    # Seed candidate with variants only in variants_json (mimics Phase 2 stage 3 output).
    _seed_candidate(
        conn,
        run_id="run:1",
        cand_id="cand:per:run:1:p1",
        name="重耳",
        state_id="sta:jin",
        variants=[("公子重耳", "别名")],
    )

    link_run(conn, "run:1")

    # After link_run, the structured table should have the variant rows.
    cnt = conn.execute(
        "SELECT COUNT(*) FROM candidate_person_variants "
        "WHERE candidate_person_id='cand:per:run:1:p1'"
    ).fetchone()[0]
    assert cnt == 1
