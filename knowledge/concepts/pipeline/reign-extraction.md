---
title: Reign-Extraction Skill — Stage Pre-3 Reign-Table Production
type: concept
area: pipeline
updated: 2026-05-22
implemented: Phase 4 Task 3
status: thin
load_bearing: true
references:
  - concepts/data-model/dates-and-reigns.md
  - concepts/pipeline/extraction.md
affects:
  - .claude/skills/changjuan-extract-reigns/**
  - data/reigns/**
---

## What this is

`.claude/skills/changjuan-extract-reigns/` produces draft reign tables for Eastern-Zhou states. One state per invocation. Output is YAML at `/tmp/changjuan-reigns-<state>.yaml` that the user reviews and commits to `data/reigns/<state>.yaml`.

## Why a Claude Code skill (not a Python script)

Eastern-Zhou chronology is high-context historical knowledge that LLMs do well on. A Python parser of 史记 / 左传 would have to handle classical Chinese reading conventions, multiple naming forms per ruler, and edge cases like 曲沃 武公's complex succession. The skill leverages training knowledge plus standard reference materials. The user verifies before commit; reign data is load-bearing for every date computation.

## Pipeline position

Pre-stage-3: reign tables are inputs to `pipeline/dates.py::resolve_explicit_reign_other`, which fires during stage-3 extraction whenever the LLM emits a date with `inference_kind: explicit_reign_other`.

## Output schema

See `.claude/skills/changjuan-extract-reigns/system-prompt.md` for the full schema. Key fields: `state_id`, `state_name`, `sources[]`, `rulers[]` (each with `id`, `posthumous_name`, `given_name`, `reign_start_bce`, `reign_end_bce`, `sources`, `confidence`, `notes`). The schema is also documented in `concepts/data-model/dates-and-reigns.md`.

## Curation conventions

- One state per invocation, one commit per state. Makes review focused.
- The skill marks `confidence: low` on uncertain entries — review those first.
- The user is the source of truth for date corrections; the skill is a draft.

## What would invalidate this article

- The skill becomes deterministic (parses a structured corpus instead of using LLM knowledge).
- Reign data moves out of YAML files (e.g., into a single DB table).
- The system prompt's output schema changes.
