# changjuan (长卷)

`changjuan` builds a structured knowledge graph of Eastern-Zhou history (春秋 + 战国) from the novel 《东周列国志》, cross-validated against canonical sources (左传, 史记). It exists as the tooling layer that will feed a future living-map / timeline UI ("unroll the scroll") for readers exploring the era. The tooling phase — this repo's current scope — is a Python ETL pipeline producing `data/changjuan.sqlite`, plus a Streamlit curation app for retrospective human review. The full design is in `docs/superpowers/specs/2026-05-20-changjuan-design.md`. Single-user, run locally.

## Methodology

This project follows the living-documentation methodology described at
https://github.com/mpklu/living-doc.
The first principle ("capture first, refine second") and the same-task
rule from that repository's `LIVING_DOCS_OVERVIEW.md` apply here.

## Source of Truth

The knowledge base in `knowledge/` is the source of truth for this project.
It must always mirror the code. Entry point: `knowledge/index.md`.
Compile log: `knowledge/log.md`.

### The rule

Every code change that alters behaviour, config, models, or architecture
must update the relevant `knowledge/concepts/*.md` article(s) in the same
task and append an entry to `knowledge/log.md`. Don't batch knowledge
updates for later.

**Failure mode this prevents.** Skipping the article update means it
goes stale before the next read. The next session will trust the stale
article and produce wrong work. The drift compounds. This is not
stylistic — it's load-bearing.

**Capture first, refine second:** when in doubt about whether a change is
documentation-relevant, write the update anyway. When in doubt about where
a new article belongs, pick the closest fit and write it. The user reviews
and refines. Missing context is unrecoverable; an imperfect article costs
minutes.

### Before any commit

The same-task rule is a *principle*; this checklist is the *procedure*.
Run through it before every commit:

1. List the files in this commit's diff.
2. For each: any article's `affects:` frontmatter glob match it? (Until
   the `affects:`-based mapping is in place, fall back to the
   article-mapping table below.) Open those articles.
3. Did this change alter behaviour, configuration, models, structure,
   or a documented decision?
4. If yes: stage the article update + a `log.md` entry **in this same
   commit**.
5. If no article exists for the touched code path: write a thin one
   now (~200 words). Don't open a follow-up issue; don't defer.
6. If the change is genuinely doc-irrelevant (typo, formatting,
   refactor with identical observable behaviour): the commit body
   must say so explicitly: `no knowledge impact: <reason>`.

### Red flags

These thoughts mean STOP and audit:

- "I'll update docs after this commit lands."
- "The article is roughly correct."
- "This is too small to document."
- "Let me ship and circle back."
- "The reviewer can flag it if it matters."

Each phrase rationalizes a skip that compounds. The cost of pausing
to update the article is minutes; the cost of stale documentation is
unbounded.

### What lives where

| Location | Contains | Authority |
| --- | --- | --- |
| `knowledge/concepts/` | Standalone reference articles, grouped by area | How each thing works and why |
| `knowledge/connections/` | Cross-concept articles | How the pieces fit together |
| `pipeline/` | Python ETL package (stages 1–9, prompts, schemas, cache) | What the pipeline does |
| `curation/` | Streamlit curation app | Retrospective human review UI |
| `corpora/` | Symlinks to sibling source-text repos (东周列国志, 左传, 史记) | Immutable source |
| `data/` | Generated SQLite stores + export bundles (gitignored except exports) | Pipeline output |
| `tests/` | Golden chapters, unit + integration tests | Testable behaviour |
| `docs/superpowers/specs/` | Design specs (the founding `2026-05-20-changjuan-design.md`) | Why this shape |
| `.env` | LLM API keys etc. (gitignored) | Local config |

### Article mapping — update these when the matching code changes

This table is populated from day one of greenfield. Add new rows as new modules / external integrations land.

| When you change... | Update this article |
| --- | --- |
| `pipeline/schemas/*.sql` | `concepts/data-model/knowledge-graph.md` |
| `pipeline/**/date*.py` or `pipeline/**/reign*.py` or `pipeline/**/dates.py` | `concepts/data-model/dates-and-reigns.md` |
| Pipeline stages 1–9 boundaries, inputs/outputs, or invariants | `concepts/pipeline/architecture.md` |
| `pipeline/**/stage3*.py` or `pipeline/**/prompts/**` or `pipeline/schemas/extract_output.py` or `.claude/skills/changjuan-extract*/**` or `pipeline/confidence.py` | `concepts/pipeline/extraction.md` |
| `pipeline/**/stage5*.py` or `pipeline/**/link*.py` | `concepts/pipeline/linking.md` |
| `pipeline/**/stage6*.py` or `pipeline/**/cross_canon*.py` | `concepts/pipeline/cross-canon.md` |
| `pipeline/**/stage7*.py` or `pipeline/**/load*.py` | `concepts/pipeline/load-and-merge.md` |
| `pipeline/**/stage9*.py` or `pipeline/**/export*.py` | `concepts/pipeline/export-contract.md` |
| `pipeline/**/confidence*.py` or `pipeline/**/scoring*.py` | `concepts/verification/confidence.md` |
| `pipeline/**/invariant*.py` or `pipeline/**/justif*.py` | `concepts/verification/extraction-invariants.md` |
| `curation/**/*.py` | `concepts/curation/streamlit-app.md` |
| `pipeline/**/incremental*.py` or `pipeline/**/reextract*.py` | `concepts/pipeline/incremental.md` |
| `corpora/**` or `pipeline/**/ingest*.py` | `concepts/corpora/{corpus}.md` |
| `pipeline/**/stats*.py` or `pipeline/**/metrics*.py` | `concepts/verification/stats-schema.md` |
| `.env` or `pipeline/config.py` | `concepts/runtime/configuration.md` |
| `pipeline/**/__main__.py` or `pipeline/**/cli*.py` | `concepts/runtime/cli.md` |
| `tests/**/*.py` | `concepts/verification/testing.md` |

### When the agent encounters code without a matching article

Write the first thin article in the same task. Place as:

- `concepts/{area}/{topic-kebab-case}.md` for an internal concept.
- `concepts/corpora/{corpus}.md` for a source-text integration.
- `connections/{topic}.md` for a cross-cutting article describing how multiple existing concepts interact.

Capture the **why** — context, constraints, alternatives ruled out — not
just the post-change state of the code. Add a row to the article-mapping
table above. Note the addition in `log.md`.

### How to catch drift

After finishing implementation, ask: "does anything in `knowledge/` now
contradict what I just built?" Check signatures, field lists, config
tables, folder structure, and env var names. **Real data beats the article**
— if a field the article says is required turns out to be absent in real
payloads, update the article to match reality, not the other way around.
Add a compile entry to `knowledge/log.md` listing the articles touched.

## Project Structure

See Appendix A of `docs/superpowers/specs/2026-05-20-changjuan-design.md`. In brief:

```
changjuan/
├── corpora/                 # symlinks to sibling source-text repos
├── pipeline/                # Python ETL package (stages 1–9)
├── curation/                # Streamlit retrospective-review app
├── data/                    # generated SQLite + export bundles
├── tests/                   # golden chapters, unit, integration
├── knowledge/               # living docs (this methodology's source of truth)
└── docs/superpowers/specs/  # design specs
```

## Key Commands

```bash
# Pipeline (eventual CLI; see concepts/runtime/cli.md once implemented)
changjuan ingest                     # stages 1-2: corpora -> corpus.sqlite
changjuan extract --chapters 1..5    # stages 3-4: candidates
changjuan link                       # stage 5: dedup
changjuan canon-check --with-canon-check   # stage 6: cross-canon (opt-in)
changjuan load                       # stage 7: candidates -> canonical
changjuan export                     # stage 9: freeze bundle
changjuan re-extract --chapter N --prompt-version M

# Curation
streamlit run curation/app.py

# Tests + drift
pytest
scripts/drift-check
scripts/validate-articles
pre-commit install
```
