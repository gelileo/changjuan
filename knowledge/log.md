# Build Log

Append-only chronological log of significant changes to this project. Each entry records what changed, why, and which articles were touched. Read sequentially, this log tells the story of the project's decisions.

## [2026-05-20] living-docs: seed first 3 north-star articles (greenfield)

Seeded the knowledge base with three thin "north star" articles capturing the load-bearing decisions made before any code is written. Source of truth for these decisions is `docs/superpowers/specs/2026-05-20-changjuan-design.md`; the articles distill the design spec into durable per-concept references that the same-task rule can attach to as code lands.

Articles created:

- `concepts/data-model/knowledge-graph.md` — the six-entity model (Person, State, Place, Event, Citation, Conflict) + structured Date + Person name variants + citation on every relation. `Family` deferred to `person_relations(kind="clan_member")`.
- `concepts/pipeline/architecture.md` — the 9-stage sequential ETL and the load-bearing principle: automation produces a complete usable graph without curation; curation is retrospective, never a gate.
- `concepts/verification/confidence-and-invariants.md` — confidence is a deterministic computed score (not LLM self-report); two-layer extraction invariant with honest framing of per-field-justification (gameable, generation-time nudge) vs. sampling QA (the real backstop).

Anchor questions: not re-asked. All anchors were resolved during the design-spec brainstorm earlier in the session — audience, source coupling, primary reader-view metaphor, map style, data strategy, MVP scope, tech stack — see `docs/superpowers/specs/2026-05-20-changjuan-design.md` §1 and Non-goals subsection.

Decisions still pending (deferred deliberately; see spec Non-goals & deliberate omissions):

- LLM provider/model choice (recommendation: Claude Sonnet for stages 3/5, Opus for stage 6).
- Reign-table source (recommendation: bundled JSON from 杨伯峻 chronology).
- 左传 / 史记 source edition (recommendation: ctext.org, archived at a known SHA).
- Place coordinates source (recommendation: CHGIS + fallback geocode).
- Golden-chapter selection (recommendation: Ch. 1 + Ch. ~40).
- Promotion of `Family` to a first-class entity (after golden-chapter pass tells us).

`affects:` globs are deliberately empty on all three articles — code does not yet exist. The same-task rule will attach globs as files land.

## [2026-05-20] living-docs: adopted methodology via installer

Ran `install.sh` from `mpklu/living-doc`. Greenfield templates installed:

- `CLAUDE.md` filled in with project-specific content (project description, file layout, article-mapping table tailored to the planned `pipeline/`, `curation/`, `corpora/`, `data/` boundaries).
- `knowledge/{index.md, log.md, concepts/, connections/}`, `schemas/article-frontmatter.schema.json`, `scripts/{drift-check, validate-articles}`, `actions/drift-check/*`, `.pre-commit-config.yaml`.
- `LIVING_DOCS_FIRST_PROMPT.md` consumed and to be deleted on commit.
