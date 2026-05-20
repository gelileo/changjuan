---
title: Knowledge graph — entities, relations, citations
type: concept
area: data-model
updated: 2026-05-20
status: thin
load_bearing: true
references:
  - concepts/pipeline/architecture.md
  - concepts/verification/confidence-and-invariants.md
affects:
  - pipeline/schemas/corpus_schema.sql
---

## What this is

The output of `changjuan` is a typed knowledge graph of Eastern-Zhou history, built from 《东周列国志》 and validated against 《左传》 / 《史记》. Six entity types — **Person, State, Place, Event, Citation, Conflict** — connected by typed relations (`event_participants`, `person_relations` including `clan_member`, `person_states`, `event_places`, `state_capitals`, …). A `Family` entity was considered and deferred; clan/lineage facts ride on `Person.clan_name` + `person_relations(kind="clan_member")` until the data demands promotion. Every entity and every relation carries at least one **citation** (a verbatim quote span in a source corpus), a deterministic-computed **confidence** score, and full **audit history**. Dates are structured values (`year_bce`, `uncertainty`, `original`, `era`, `inference_kind`), never primitives. Name variants are first-class on Person — `重耳`, `晋文公`, `公子重耳` resolve to one id.

## Why this shape, not the alternatives

A flat events table would be cheap but useless for the eventual map UI — readers can't traverse "where was 重耳 in 645 BCE?" without a Person-with-trajectory model. A document-oriented store (one JSON per chapter) would make linking across chapters impossible — and almost every interesting fact in this corpus is cross-chapter. The relational schema costs upfront complexity but enables every reader question we want to answer later.

## What would invalidate this article

- A class of historical fact in the source that doesn't fit one of {Person, State, Place, Event, person_relation, Citation, Conflict}. (Family entity sits in the promotion-path queue; promotion is not invalidation.)
- A "fact" in the canonical store without a citation.
- A date whose uncertainty cannot be represented.
- Two records that should be the same id but cannot be merged because the model lacks a variant kind, role, or relation `kind`.

## First commitments (true once code lands)

- SQLite schema in `pipeline/schemas/sql/` and loader in `pipeline/stage7_load.py`. Tables enumerated in the design spec §5.
- Person identity rule: `canonical_name` + `variants[]` with `kind ∈ {本名, 字, 谥号, 封号, 别名}`.
- Every relation row carries its own `citation_id`, `confidence`, `provenance` — not just entities.
- Date type: `{year_bce, uncertainty (point|range|circa), year_bce_end?, original, era, inference_kind}`.
- Stable IDs are human-readable slugs (`per:jin-wen-gong`, `evt:cheng-pu-zhi-zhan-632bce`), seeded from curated `canonical_name`.
