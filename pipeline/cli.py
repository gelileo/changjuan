"""changjuan CLI — typer-based entry point.

Exposes one subcommand per pipeline stage that has a stable user-facing surface.
Phase 1 wires ingest / chunk / load / export.
"""

from __future__ import annotations

from pathlib import Path

import structlog
import typer

from pipeline.config import Config
from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA, CORPUS_SCHEMA
from pipeline.stage1_ingest import ingest_dongzhoulieguozhi
from pipeline.stage2_chunk import chunk_documents
from pipeline.stage7_load import load_candidate_persons
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
        n = load_candidate_persons(conn, pipeline_run_id=pipeline_run_id)
    typer.echo(f"loaded {n} candidate_persons rows under pipeline_run_id={pipeline_run_id}")


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
