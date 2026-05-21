---
title: changjuan CLI commands
type: concept
area: runtime
updated: 2026-05-21
status: current
load_bearing: false
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/dates-and-reigns.md
affects:
  - pipeline/cli.py
  - tests/unit/test_resolve_relative_date_cli.py
---

## What this is

The `changjuan` command is a typer-based CLI exposing one subcommand per pipeline stage that has a stable user-facing surface. Phase 1 wires `ingest`, `chunk`, `load`, `export`. Phase 2 adds `extract-load`, `list-unresolved-dates`, and `resolve-relative-date` — the first a thin wrapper around stage-3 extraction; the latter two the curator triage surface for cross-chunk relative-date anchoring.

## Subcommands

### Pipeline stages

- **`changjuan ingest [--repo-root PATH]`** — Stage 1: reads the dongzhoulieguozhi JSON from `corpora/dongzhoulieguozhi/json/东周列国志.json` and inserts one row per chapter into `corpus.sqlite`. Exits 1 with a clear message if the corpus file is absent.
- **`changjuan chunk [--repo-root PATH]`** — Stage 2: splits all unchunked documents into paragraph-aware overlapping chunks and writes them to `corpus.sqlite`.
- **`changjuan extract-load --chapter N --extraction-file PATH --prompt-version V [--pipeline-run-id ID] [--repo-root PATH]`** — Stage 3: validates a skill-produced extraction YAML file, runs all extraction invariants per record, and writes passing records to `candidate_persons`, `candidate_events`, `candidate_places`, `candidate_states`, and `candidate_relations`. Auto-generates a `pipeline_run_id` (format: `run:extract-ch<chapter>-<prompt_version>-<timestamp>`) if `--pipeline-run-id` not supplied. Returns per-entity-kind counts and lists up to 10 invariant violations (or count if >10). Invariant failures prevent a record from being written but do not cause the command to exit non-zero.
- **`changjuan load <pipeline_run_id> [--repo-root PATH]`** — Stage 7: promotes all five entity-kind candidates matching the given `pipeline_run_id` into canonical entities with field-level merge semantics (curated-never-overwritten, higher-confidence-wins, Conflict on disagreement). Load order: places + states first (other entity types reference them via foreign keys), then persons, events, and finally all six relation kinds. Returns counts for each entity kind loaded.
- **`changjuan export <version> [--repo-root PATH]`** — Stage 9: freezes a versioned export bundle at `data/exports/changjuan-export-<version>/`, containing `manifest.json` and a `candidate_*`-stripped SQLite snapshot.

### Curator triage verbs (Phase 2)

- **`changjuan list-unresolved-dates [--repo-root PATH] [--chapter N]`** — Lists all canonical `events` whose `date_json` has `inference_kind = 'relative_to_prior_event'`, `year_bce = null`, and no `relative_anchor_event_id`. These are relative-date references whose anchor event lived in a prior extraction chunk and could not be resolved automatically. Output is tab-separated `event_id\toriginal_text`, one row per unresolved event. Exits 0 with a "(no unresolved relative dates)" message when none remain.

- **`changjuan resolve-relative-date --event-id ID --anchor-event-id ID [--offset N] [--repo-root PATH] [--actor LABEL]`** — Manually resolves a cross-chunk relative date by:
  1. Setting `relative_anchor_event_id` in the event's `date_json` to the supplied anchor.
  2. Calling `resolve_relative_dates` to recompute `year_bce` from the anchor's resolved year plus the token offset (or `--offset` when the original text is not a known token like 明年/次年).
  3. Persisting the updated `date_json` to `events`.
  4. Writing an `audit_log` entry with `change_kind = 'curator_override'` and `actor` defaulting to `curator:default`.

  Exits 1 with a clear error if the event or anchor is not found, the anchor has no resolved `year_bce`, or the offset cannot be determined.

  The `--offset` flag is calendar-years-later (positive = forward in time). For BCE arithmetic: `year_bce_result = anchor_year_bce - offset`.

## Why this shape, not the alternatives

A single `changjuan run` mega-command was considered and rejected — it would hide the cost profile of each stage and make resumption harder. Separate subcommands match the stage-checkpointed pipeline model directly: each stage runs independently, each can be re-run without re-executing earlier stages, and the user can inspect intermediate outputs between stages.

The `list-unresolved-dates` / `resolve-relative-date` pair is deliberately not automatic: the skill explicitly does not attempt cross-chunk anchoring because the correct anchor requires curator judgment. The CLI surfaces the triage work; `audit_log` entries make every resolution reversible and attributable.

## Design commitments

- All commands take `--repo-root` to allow non-cwd execution (testing, multiple checkouts).
- `load` takes a required `pipeline_run_id` positional — promotion is always scoped to a specific extraction batch.
- `export` takes a required `version` positional — export bundles are always versioned at the bundle dirname.
- `resolve-relative-date` always writes an `audit_log` entry — resolutions are auditable even if the curator corrects a previous resolution.

## What would invalidate this article

- A stage acquiring more than one user-facing verb (e.g., separate `link` and `link-rescue`).
- The pipeline becoming agentic (one command, no stages).
- Automatic cross-chunk anchoring being added (would retire the curator verbs or demote them to override-only).
