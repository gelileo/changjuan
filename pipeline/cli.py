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
