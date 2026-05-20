---
title: changjuan CLI commands
type: concept
area: runtime
updated: 2026-05-20
status: thin
load_bearing: false
references:
  - concepts/pipeline/architecture.md
affects:
  - pipeline/cli.py
---

## What this is

The `changjuan` command is a typer-based CLI exposing one subcommand per pipeline stage that has a stable user-facing surface. Phase 1 wires `ingest`, `chunk`, `load`, `export`. Stages without a CLI verb (3 extract, 5 link, 6 canon-check) get one as their phase plans land.

## Subcommands

- **`changjuan ingest [--repo-root PATH]`** — Stage 1: reads the dongzhoulieguozhi JSON from `corpora/dongzhoulieguozhi/json/东周列国志.json` and inserts one row per chapter into `corpus.sqlite`. Exits 1 with a clear message if the corpus file is absent.
- **`changjuan chunk [--repo-root PATH]`** — Stage 2: splits all unchunked documents into paragraph-aware overlapping chunks and writes them to `corpus.sqlite`.
- **`changjuan load <pipeline_run_id> [--repo-root PATH]`** — Stage 7: promotes `candidate_persons` rows matching the given `pipeline_run_id` into canonical `persons` with field-level merge semantics (curated-never-overwritten, higher-confidence-wins, Conflict on disagreement).
- **`changjuan export <version> [--repo-root PATH]`** — Stage 9: freezes a versioned export bundle at `data/exports/changjuan-export-<version>/`, containing `manifest.json` and a `candidate_*`-stripped SQLite snapshot.

## Why this shape, not the alternatives

A single `changjuan run` mega-command was considered and rejected — it would hide the cost profile of each stage and make resumption harder. Separate subcommands match the stage-checkpointed pipeline model directly: each stage runs independently, each can be re-run without re-executing earlier stages, and the user can inspect intermediate outputs between stages.

## Design commitments

- All commands take `--repo-root` to allow non-cwd execution (testing, multiple checkouts).
- `load` takes a required `pipeline_run_id` positional — promotion is always scoped to a specific extraction batch.
- `export` takes a required `version` positional — export bundles are always versioned at the bundle dirname.

## What would invalidate this article

- A stage acquiring more than one user-facing verb (e.g., separate `link` and `link-rescue`).
- The pipeline becoming agentic (one command, no stages).
