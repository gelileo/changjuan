"""changjuan CLI — typer-based entry point.

Exposes one subcommand per pipeline stage that has a stable user-facing surface.
Phase 1 wires ingest / chunk / load / export.
Phase 2 adds list-unresolved-dates / resolve-relative-date for cross-chunk anchoring.
"""

from __future__ import annotations

import json as _json
import uuid as _uuid
from datetime import UTC, datetime
from pathlib import Path

import structlog
import typer

from pipeline.config import Config
from pipeline.dates import RelativeResolveError, resolve_relative_dates
from pipeline.db import apply_schema, connect, open_canonical_db, open_corpus_db
from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi
from pipeline.stage2_chunk import chunk_documents
from pipeline.stage3_extract import load_extraction
from pipeline.stage7_load import (
    load_candidate_events,
    load_candidate_persons,
    load_candidate_places,
    load_candidate_relations,
    load_candidate_states,
)
from pipeline.stage9_export import export_bundle

app = typer.Typer(help="changjuan — Eastern-Zhou knowledge graph pipeline.")
log = structlog.get_logger()


def _cfg(repo_root: Path | None) -> Config:
    return Config(repo_root=repo_root) if repo_root else Config()


@app.command()
def ingest(
    repo_root: Path | None = typer.Option(None, help="Override the repo root."),
) -> None:
    """Stage 1: read source corpora into corpus.sqlite."""
    cfg = _cfg(repo_root)
    src = cfg.corpora_dir / "dongzhoulieguozhi" / "json" / "东周列国志.json"
    if not src.exists():
        typer.echo(f"no corpora found at {src}", err=True)
        raise typer.Exit(code=1)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = ingest_dongzhoulieguozhi(conn, cfg)
    typer.echo(f"ingested {n} chapters into {cfg.corpus_db}")


@app.command()
def chunk(
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 2: split documents into overlapping paragraph-aware chunks."""
    cfg = _cfg(repo_root)
    with connect(cfg.corpus_db) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        n = chunk_documents(conn, cfg)
    typer.echo(f"wrote {n} chunks into {cfg.corpus_db}")


@app.command()
def load(
    pipeline_run_id: str = typer.Argument(
        ..., help="Pipeline run id to promote (matches candidate_persons.pipeline_run_id)."
    ),
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 7: promote candidates → canonical with field-level merge."""
    cfg = _cfg(repo_root)
    with connect(cfg.canonical_db) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        # Order matters: places + states first (events + relations reference them via FK).
        n_places = load_candidate_places(conn, pipeline_run_id=pipeline_run_id)
        n_states = load_candidate_states(conn, pipeline_run_id=pipeline_run_id)
        n_persons = load_candidate_persons(conn, pipeline_run_id=pipeline_run_id)
        n_events = load_candidate_events(conn, pipeline_run_id=pipeline_run_id)
        n_rels = load_candidate_relations(conn, pipeline_run_id=pipeline_run_id)
    typer.echo(
        f"loaded: places={n_places} states={n_states} persons={n_persons} "
        f"events={n_events} relations={n_rels} (run={pipeline_run_id})"
    )


@app.command()
def export(
    version: str = typer.Argument(..., help="Export bundle version label (e.g., 2026-05-v1)."),
    repo_root: Path | None = typer.Option(None),
) -> None:
    """Stage 9: freeze a versioned export bundle."""
    cfg = _cfg(repo_root)
    out_dir = cfg.exports_dir / f"changjuan-export-{version}"
    export_bundle(cfg.canonical_db, out_dir, version=version, corpus_db=cfg.corpus_db)
    typer.echo(f"export bundle written to {out_dir}")


@app.command(name="list-unresolved-dates")
def list_unresolved_dates_cmd(
    chapter: int | None = typer.Option(None, "--chapter", help="Filter to a specific chapter"),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """List canonical events with relative_to_prior_event dates that have null year_bce
    and no explicit anchor. The curator triages these via `resolve-relative-date`."""
    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    rows = canonical.execute(
        """
        SELECT id, json_extract(date_json, '$.original'),
               json_extract(date_json, '$.relative_anchor_event_id'),
               json_extract(date_json, '$.year_bce')
        FROM events
        WHERE json_extract(date_json, '$.inference_kind') = 'relative_to_prior_event'
          AND json_extract(date_json, '$.year_bce') IS NULL
          AND json_extract(date_json, '$.relative_anchor_event_id') IS NULL
        ORDER BY id
        """
    ).fetchall()
    if not rows:
        typer.echo("(no unresolved relative dates)")
        return
    for eid, original, _anchor, _year in rows:
        typer.echo(f"{eid}\t{original}")


@app.command(name="resolve-relative-date")
def resolve_relative_date_cmd(
    event_id: str = typer.Option(..., "--event-id"),
    anchor_event_id: str = typer.Option(..., "--anchor-event-id"),
    offset: int | None = typer.Option(
        None,
        "--offset",
        help="Calendar-years-later when original is not a known token (e.g. 5 for 其后五年)",
    ),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
    actor: str = typer.Option("curator:default", "--actor", help="Recorded in audit_log"),
) -> None:
    """Set relative_anchor_event_id on `event_id`'s date_json, recompute year_bce,
    and write an audit_log entry."""
    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")

    row = canonical.execute("SELECT date_json FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        typer.echo(f"event {event_id} not found", err=True)
        raise typer.Exit(code=1)
    before = _json.loads(row[0])

    anchor_row = canonical.execute(
        "SELECT json_extract(date_json, '$.year_bce') FROM events WHERE id = ?",
        (anchor_event_id,),
    ).fetchone()
    if anchor_row is None:
        typer.echo(f"anchor event {anchor_event_id} not found", err=True)
        raise typer.Exit(code=1)
    if anchor_row[0] is None:
        typer.echo(f"anchor event {anchor_event_id} has no resolved year_bce", err=True)
        raise typer.Exit(code=1)

    after = dict(before)
    after["relative_anchor_event_id"] = anchor_event_id
    record: dict[str, object] = {"id": event_id, "date": after}
    try:
        resolve_relative_dates([record], conn=canonical, offset_override=offset)
    except RelativeResolveError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    canonical.execute(
        "UPDATE events SET date_json = ? WHERE id = ?",
        (_json.dumps(after), event_id),
    )
    canonical.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) "
        "VALUES (?, 'event', ?, 'date_json', 'curator_override', ?, ?, ?, datetime('now'))",
        (
            str(_uuid.uuid4()),
            event_id,
            _json.dumps({"value": before, "confidence": None}),
            _json.dumps({"value": after, "confidence": None}),
            actor,
        ),
    )
    canonical.commit()
    typer.echo(f"resolved {event_id}: year_bce = {after.get('year_bce')}")


@app.command(name="re-extract")
def re_extract_cmd(
    chapter: int = typer.Option(..., "--chapter"),
    prompt_version: str = typer.Option(..., "--prompt-version"),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Re-load an existing extraction YAML as a new pipeline_run, or instruct the user
    to invoke the corresponding skill in Claude Code first."""
    from datetime import UTC
    from datetime import datetime as _datetime

    extraction_file = (
        repo_root / "data" / "extractions" / f"ch{chapter:02d}" / f"extract-{prompt_version}.yaml"
    )
    if not extraction_file.exists():
        skill_dir = "changjuan-extract" + (f"-{prompt_version}" if prompt_version != "v1" else "")
        typer.echo(
            f"Extraction file not found: {extraction_file}\n\n"
            f"Skill `.claude/skills/{skill_dir}/` has not been run for chapter {chapter}.\n"
            f"Invoke in Claude Code first:\n"
            f"  /{skill_dir} chapter:{chapter}\n"
        )
        raise typer.Exit(code=1)

    ts = _datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_id = f"run:re-extract-ch{chapter}-{prompt_version}-{ts}"
    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    corpus = open_corpus_db(repo_root / "data" / "corpus.sqlite")
    stats = load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=chapter,
        extraction_file=extraction_file,
        prompt_version=prompt_version,
        pipeline_run_id=run_id,
    )
    typer.echo(
        f"re-extracted as {run_id}: persons={stats['persons_written']} "
        f"events={stats['events_written']} places={stats['places_written']} "
        f"states={stats['states_written']} relations={stats['relations_written']}"
    )
    if stats["invariant_violations"]:
        typer.echo(f"invariant violations: {len(stats['invariant_violations'])}")


@app.command()
def extract(
    chapter: int = typer.Option(..., "--chapter"),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Pre-flight check for stage 3. Does NOT call an LLM.

    Verifies: corpus exists, target chapter has chunks (>1, post _PARA_SEP fix),
    latest changjuan-extract skill directory exists, extraction-schema.yaml is in
    sync with the Python schema. Prints copy-paste skill invocation if green.
    """
    import sqlite3

    import yaml

    from pipeline.schemas.extract_output import EXTRACT_OUTPUT_SCHEMA

    checks: list[tuple[str, bool]] = []
    corpus_path = repo_root / "data" / "corpus.sqlite"
    checks.append(("corpus.sqlite exists", corpus_path.exists()))

    if corpus_path.exists():
        c = sqlite3.connect(corpus_path)
        n = c.execute(
            "SELECT COUNT(*) FROM chunks c JOIN documents d ON c.document_id = d.id "
            "WHERE d.chapter_num = ?",
            (chapter,),
        ).fetchone()[0]
        checks.append((f"chapter {chapter} has chunks (>1)", n > 1))
    else:
        checks.append((f"chapter {chapter} has chunks (>1)", False))

    skill_dirs = sorted((repo_root / ".claude" / "skills").glob("changjuan-extract*"))
    checks.append(("at least one .claude/skills/changjuan-extract*/ exists", bool(skill_dirs)))

    latest = skill_dirs[-1] if skill_dirs else None
    if latest:
        for required in ("SKILL.md", "system-prompt.md", "extraction-schema.yaml"):
            checks.append((f"{latest.name}/{required} exists", (latest / required).exists()))
        schema_yaml = latest / "extraction-schema.yaml"
        if schema_yaml.exists():
            on_disk = yaml.safe_load(schema_yaml.read_text(encoding="utf-8"))
            checks.append(
                ("extraction-schema.yaml matches Python schema", on_disk == EXTRACT_OUTPUT_SCHEMA)
            )

    all_pass = all(ok for _, ok in checks)
    for label, ok in checks:
        typer.echo(f"  {'✓' if ok else '✗'} {label}")

    if all_pass and latest is not None:
        prompt_version = latest.name.removeprefix("changjuan-extract").lstrip("-") or "v1"
        typer.echo("\nReady. Invoke in Claude Code:")
        typer.echo(f"  /{latest.name} chapter:{chapter}")
        typer.echo("Then run:")
        typer.echo(
            f"  uv run changjuan extract-load --chapter {chapter} "
            f"--extraction-file data/extractions/ch{chapter:02d}/extract-{prompt_version}.yaml "
            f"--prompt-version {prompt_version}"
        )
    else:
        raise typer.Exit(code=1)


@app.command(name="golden-eval")
def golden_eval_cmd(
    chapter: int = typer.Option(..., "--chapter"),
    pipeline_run_id: str | None = typer.Option(
        None,
        "--pipeline-run-id",
        help="Defaults to latest extract-load run for this chapter",
    ),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Run golden P/R against the latest extraction in candidate_* tables and gate
    on pipeline.config.GOLDEN_PR_THRESHOLDS."""
    import json as _json_inner
    import sys

    sys.path.insert(0, str(repo_root))  # ensure tests/golden is importable
    from pipeline import config
    from tests.golden.loader import load_golden
    from tests.golden.precision_recall import compute_pr

    golden_dir = repo_root / "tests" / "golden" / f"ch{chapter:02d}"
    golden = load_golden(golden_dir)
    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")

    if pipeline_run_id is None:
        row = canonical.execute(
            "SELECT id FROM pipeline_runs "
            "WHERE stage='extract-load' AND json_extract(scope_json, '$.chapter') = ? "
            "ORDER BY started_at DESC LIMIT 1",
            (chapter,),
        ).fetchone()
        if row is None:
            typer.echo(
                f"no extract-load run found for chapter {chapter}; "
                f"run `changjuan extract-load --chapter {chapter} ...` first",
                err=True,
            )
            raise typer.Exit(code=1)
        pipeline_run_id = row[0]

    # ===== persons =====
    # id column carries the full candidate id (e.g. 'cand:per:run:xxx:p1').
    # Extract the chunk-local suffix so name-lookup keys align with the
    # cross-entity id values stored in state_id / relation fields ('p1', 's1', etc.).
    persons = []
    for row in canonical.execute(
        "SELECT id, canonical_name, state_id, social_category FROM candidate_persons "
        "WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        chunk_local_id = row[0].split(":")[-1]  # 'cand:per:run:xxx:p1' → 'p1'
        persons.append(
            {
                "id": chunk_local_id,
                "canonical_name": row[1],
                "state_id": row[2],
                "social_category": row[3],
                "variants": [],  # candidate_person_variants is a Phase-3 expansion
            }
        )

    # ===== events =====
    events = []
    for row in canonical.execute(
        "SELECT id, type, date_json, primary_place_id FROM candidate_events "
        "WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        chunk_local_id = row[0].split(":")[-1]  # 'cand:evt:run:xxx:e1' → 'e1'
        date = _json_inner.loads(row[2]) if row[2] else {}
        events.append(
            {
                "id": chunk_local_id,
                "type": row[1],
                "date": {"year_bce": date.get("year_bce")} if date else {},
                "primary_place_id": row[3],
            }
        )

    # ===== places =====
    places = []
    for row in canonical.execute(
        "SELECT id, name FROM candidate_places WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        chunk_local_id = row[0].split(":")[-1]  # 'cand:pla:run:xxx:pl1' → 'pl1'
        places.append({"id": chunk_local_id, "name": row[1]})

    # ===== states =====
    states = []
    for row in canonical.execute(
        "SELECT id, name FROM candidate_states WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        chunk_local_id = row[0].split(":")[-1]  # 'cand:sta:run:xxx:s1' → 's1'
        states.append({"id": chunk_local_id, "name": row[1]})

    # ===== relations =====
    # Relation tables store full 'cand:*' ids in their FK columns.
    # Extract the chunk-local suffix so they align with the id keys in the
    # persons/events/places/states lookup maps built above.
    def _cl(full_id: str | None) -> str | None:
        """chunk-local id: 'cand:per:run:xxx:p1' → 'p1'; None → None."""
        return full_id.split(":")[-1] if full_id else None

    relations: list[dict[str, object]] = []
    for row in canonical.execute(
        "SELECT candidate_event_id, candidate_person_id, role FROM candidate_event_participants "
        "WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        relations.append(
            {
                "kind": "event_participant",
                "event_id": _cl(row[0]),
                "person_id": _cl(row[1]),
                "role": row[2],
            }
        )
    # candidate_event_places: event_id + place_id + role
    for row in canonical.execute(
        "SELECT candidate_event_id, candidate_place_id, role FROM candidate_event_places "
        "WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        relations.append(
            {
                "kind": "event_place",
                "event_id": _cl(row[0]),
                "place_id": _cl(row[1]),
                "role": row[2],
            }
        )
    # candidate_event_relations: from + to + kind
    for row in canonical.execute(
        "SELECT from_candidate_event_id, to_candidate_event_id, kind "
        "FROM candidate_event_relations WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        relations.append({"kind": row[2], "from_event_id": _cl(row[0]), "to_event_id": _cl(row[1])})
    # candidate_person_relations: from + to + kind
    for row in canonical.execute(
        "SELECT from_candidate_person_id, to_candidate_person_id, kind "
        "FROM candidate_person_relations WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        relations.append(
            {"kind": row[2], "from_person_id": _cl(row[0]), "to_person_id": _cl(row[1])}
        )
    # candidate_person_states: person_id + state_id + role
    for row in canonical.execute(
        "SELECT candidate_person_id, candidate_state_id, role FROM candidate_person_states "
        "WHERE pipeline_run_id = ?",
        (pipeline_run_id,),
    ):
        relations.append(
            {
                "kind": "person_state",
                "person_id": _cl(row[0]),
                "state_id": _cl(row[1]),
                "role": row[2],
            }
        )
    # state_capital has no candidate_* table (Task 19 stub — omitted)

    candidates = {
        "persons": persons,
        "events": events,
        "places": places,
        "states": states,
        "relations": relations,
    }

    report = compute_pr(golden, candidates)
    failed = 0
    for kind, scores in report["per_entity_type"].items():
        target = config.GOLDEN_PR_THRESHOLDS.get(kind, {})
        p_ok = scores["precision"] >= target.get("precision", 0)
        r_ok = scores["recall"] >= target.get("recall", 0)
        if not (p_ok and r_ok):
            failed += 1
        typer.echo(
            f"{kind:10s}  precision={scores['precision']:.2f}{' ✓' if p_ok else ' ✗'}"
            f"  recall={scores['recall']:.2f}{' ✓' if r_ok else ' ✗'}"
            f"  (tp={scores['tp']} fp={scores['fp']} fn={scores['fn']})"
        )
    if failed:
        raise typer.Exit(code=1)


@app.command(name="qa-sample")
def qa_sample_cmd(
    pipeline_run_id: str = typer.Argument(..., help="Pipeline run id to sample."),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Print the deterministic 5% sample of scalar facts for pipeline_run_id as YAML."""
    import yaml as _yaml

    from pipeline.qa_sampling import select_sample

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")

    facts: list[dict[str, object]] = []

    # Try candidate_facts first; if not populated, fall back to candidate_* tables.
    candidate_facts_exists = canonical.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_facts'"
    ).fetchone()

    if candidate_facts_exists:
        for row in canonical.execute(
            "SELECT subject_kind, subject_candidate_id, field, value_json, justification_quote "
            "FROM candidate_facts WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ):
            facts.append(
                {
                    "pipeline_run_id": pipeline_run_id,
                    "record_kind": row[0],
                    "record_id": row[1],
                    "field": row[2],
                    "value": row[3],
                    "quote": row[4],
                }
            )

    if not facts:
        # Fallback: enumerate scalar facts directly from candidate_* tables.
        for row in canonical.execute(
            "SELECT id, canonical_name, gender, social_category, quote "
            "FROM candidate_persons WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ):
            cand_id, canonical_name, gender, social_category, quote = row
            for field, value in [
                ("canonical_name", canonical_name),
                ("gender", gender),
                ("social_category", social_category),
            ]:
                if value is not None:
                    facts.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "record_kind": "person",
                            "record_id": cand_id,
                            "field": field,
                            "value": value,
                            "quote": quote,
                        }
                    )

        for row in canonical.execute(
            "SELECT id, type, outcome, summary, quote "
            "FROM candidate_events WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ):
            cand_id, etype, outcome, summary, quote = row
            for field, value in [
                ("type", etype),
                ("outcome", outcome),
                ("summary", summary),
            ]:
                if value is not None:
                    facts.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "record_kind": "event",
                            "record_id": cand_id,
                            "field": field,
                            "value": value,
                            "quote": quote,
                        }
                    )

        for row in canonical.execute(
            "SELECT id, name, type, modern_equiv, quote "
            "FROM candidate_places WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ):
            cand_id, name, ptype, modern_equiv, quote = row
            for field, value in [
                ("name", name),
                ("type", ptype),
                ("modern_equiv", modern_equiv),
            ]:
                if value is not None:
                    facts.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "record_kind": "place",
                            "record_id": cand_id,
                            "field": field,
                            "value": value,
                            "quote": quote,
                        }
                    )

        for row in canonical.execute(
            "SELECT id, name, type, ruling_clan, quote "
            "FROM candidate_states WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        ):
            cand_id, name, stype, ruling_clan, quote = row
            for field, value in [
                ("name", name),
                ("type", stype),
                ("ruling_clan", ruling_clan),
            ]:
                if value is not None:
                    facts.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "record_kind": "state",
                            "record_id": cand_id,
                            "field": field,
                            "value": value,
                            "quote": quote,
                        }
                    )

    sample = select_sample(facts)
    typer.echo(_yaml.safe_dump(sample, allow_unicode=True, sort_keys=False))


@app.command(name="qa-load")
def qa_load_cmd(
    run_id: str = typer.Option(..., "--run-id"),
    qa_file: Path = typer.Option(..., "--qa-file", exists=True),
    verifier_model: str = typer.Option("claude-opus-4-7", "--verifier-model"),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Load verifier verdicts into qa_samples; update pipeline_runs.stats_json."""
    import json as _json_inner
    import uuid as _uuid3

    import yaml as _yaml

    from pipeline import config

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    verdicts: list[dict[str, object]] = _yaml.safe_load(qa_file.read_text(encoding="utf-8"))
    yes = no = partial = 0
    for v in verdicts:
        canonical.execute(
            "INSERT INTO qa_samples (id, pipeline_run_id, record_kind, record_id, field, "
            "verdict, verifier_model, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                str(_uuid3.uuid4()),
                run_id,
                v["record_kind"],
                v["record_id"],
                v["field"],
                v["verdict"],
                verifier_model,
            ),
        )
        if v["verdict"] == "yes":
            yes += 1
        elif v["verdict"] == "no":
            no += 1
        elif v["verdict"] == "partial":
            partial += 1

    total = yes + no + partial
    mismatch_rate = (no + 0.5 * partial) / total if total else 0.0

    row = canonical.execute(
        "SELECT stats_json FROM pipeline_runs WHERE id = ?", (run_id,)
    ).fetchone()
    stats: dict[str, object] = _json_inner.loads(row[0]) if row and row[0] else {}
    stats["claim_defensible_sample"] = {
        "sample_size": total,
        "yes": yes,
        "partial": partial,
        "no": no,
        "mismatch_rate": mismatch_rate,
    }
    if mismatch_rate > config.QA_MISMATCH_THRESHOLD:
        breached: list[str] = stats.setdefault("thresholds_breached", [])  # type: ignore[assignment]
        if "claim_defensible_mismatch_rate" not in breached:
            breached.append("claim_defensible_mismatch_rate")
    canonical.execute(
        "UPDATE pipeline_runs SET stats_json = ? WHERE id = ?",
        (_json_inner.dumps(stats), run_id),
    )
    canonical.commit()
    typer.echo(
        f"qa-load: sampled={total} yes={yes} partial={partial} no={no} "
        f"mismatch_rate={mismatch_rate:.3f}"
    )


@app.command()
def link(
    pipeline_run_id: str = typer.Argument(
        ..., help="Pipeline run id to link (matches candidate_persons.pipeline_run_id)."
    ),
    ignore_rejections: bool = typer.Option(
        False,
        "--ignore-rejections",
        help=(
            "Re-emit pairs previously dispositioned as rejected. Use when "
            "the curator wants to revisit prior rejections (Phase 6)."
        ),
    ),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Run Stage 5 (linker) for the given pipeline_run_id.

    Walks candidate_persons, scores against the canonical + same-run pool, and
    dispatches by threshold: auto-merge writes match_target_id + audit_log;
    mid-score writes a merge_candidates row; low-score skips. See
    concepts/pipeline/linking.md for the full picture.

    Phase 6: by default, pairs previously rejected by the curator (rejected_merges
    table) are filtered out at the queue stage. --ignore-rejections bypasses
    that filter.
    """
    from pipeline.stage5_link import link_run

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    stats = link_run(canonical, pipeline_run_id, ignore_rejections=ignore_rejections)
    rejected_skipped = stats.get("rejected_filter_skipped", 0)
    suffix = " (ignore-rejections=ON)" if ignore_rejections else ""
    typer.echo(
        f"link {pipeline_run_id}: processed={stats['candidates_processed']} "
        f"auto-merged={stats['auto_merges']} queued={stats['queued']} "
        f"skipped={stats['skipped']} rejected-filter-skipped={rejected_skipped}" + suffix
    )


@app.command(name="extract-load")
def extract_load_cmd(
    chapter: int = typer.Option(..., "--chapter"),
    extraction_file: Path = typer.Option(..., "--extraction-file", exists=True),
    prompt_version: str = typer.Option(..., "--prompt-version"),
    pipeline_run_id: str | None = typer.Option(None, "--pipeline-run-id"),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Validate + load a skill-produced extraction YAML into candidate_* tables."""
    if pipeline_run_id is None:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        pipeline_run_id = f"run:extract-ch{chapter}-{prompt_version}-{ts}"

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    corpus = open_corpus_db(repo_root / "data" / "corpus.sqlite")
    stats = load_extraction(
        canonical,
        corpus_conn=corpus,
        chapter_num=chapter,
        extraction_file=extraction_file,
        prompt_version=prompt_version,
        pipeline_run_id=pipeline_run_id,
    )
    typer.echo(f"pipeline_run_id: {pipeline_run_id}")
    typer.echo(
        f"written: persons={stats['persons_written']} events={stats['events_written']} "
        f"places={stats['places_written']} states={stats['states_written']} "
        f"relations={stats['relations_written']}"
    )
    if stats["invariant_violations"]:
        typer.echo(f"invariant violations: {len(stats['invariant_violations'])}")
        for v in stats["invariant_violations"][:10]:
            typer.echo(f"  - {v}")
        if len(stats["invariant_violations"]) > 10:
            typer.echo(f"  ... and {len(stats['invariant_violations']) - 10} more")


@app.command()
def curator() -> None:
    """Launch the Streamlit curator UI."""
    import os

    project_root = Path(__file__).resolve().parent.parent
    app_path = project_root / "curation" / "app.py"
    if not app_path.exists():
        typer.echo(f"curation app not found at {app_path}", err=True)
        raise typer.Exit(1)
    os.execvp("streamlit", ["streamlit", "run", str(app_path)])
