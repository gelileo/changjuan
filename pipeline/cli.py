"""changjuan CLI — typer-based entry point.

Exposes one subcommand per pipeline stage that has a stable user-facing surface.
Phase 1 wires ingest / chunk / load / export.
Phase 2 adds list-unresolved-dates / resolve-relative-date for cross-chunk anchoring.
"""

from __future__ import annotations

import json as _json
import uuid as _uuid
from pathlib import Path

import structlog
import typer

from pipeline.config import Config
from pipeline.dates import RelativeResolveError, resolve_relative_dates
from pipeline.db import apply_schema, connect, open_canonical_db
from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi
from pipeline.stage2_chunk import chunk_documents
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
    export_bundle(cfg.canonical_db, out_dir, version=version)
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
