---
name: changjuan-extract-v2
description: Extract structured entities (persons, events, places, states, relations) from one chapter of 东周列国志 into a YAML file matching the canonical schema. Use when the user asks to extract chapter N with prompt version v2 (or re-extract chapter N with v2). v2 revises v1 based on the Ch.1 baseline analysis — see system-prompt.md §⓪ for the 7 revision rules.
---

# changjuan-extract — Stage 3 Extraction Skill

This skill performs Stage 3 (LLM extraction) of the changjuan pipeline. It reads
chunked corpus text for one chapter, extracts structured knowledge-graph candidates
following the system prompt, writes a YAML output file, then chains to the Python
loader as its final step.

## Pre-flight

Before running, verify the corpus is present and the schema is in sync:

```bash
uv run changjuan extract --chapter $CHAPTER
```

This pre-flight prints the copy-paste invocation to use and exits 1 if anything is
missing. Fix any reported issues before proceeding.

## Common gotchas (read once before writing any YAML)

These are the failure modes that surfaced repeatedly during the Ch.1–Ch.6 runs.
Each one is caught by `scripts/check-extraction` after the fact, but writing
the YAML with them in mind saves an iterate-fix cycle:

- **`justifications` values must be substrings of `citation.quote`, not of the
  whole chunk.** A summary justification that points to text *after* your
  quote will be rejected — pick a longer quote or shorter justification.
- **No paraphrasing inside `quote`.** Don't insert `……` to elide; don't drop
  trailing punctuation that's actually in the chunk; don't substitute simple
  quotes for the source's Chinese typographer's quotes.
- **Avoid bare `"<name>曰"` / `"<name>奏曰"` quotes.** Dialog tags repeat across
  the chunk and force `fill-spans` to ask you to disambiguate — pick the
  follow-on sentence instead, e.g. `"右宰丑曰：乱臣贼子"` or
  `"石碏乃使右宰丑往濮莅杀州吁"`.
- **`paragraph` is the absolute chapter paragraph number** — same indexing as
  the `[paragraph_start, paragraph_end]` range printed by `read-chapter` for
  the chunk, with the schema lower bound of 1.
- **Use natural type values** (`处死`, `战`, `朝议`, ...). The loader's
  collision guard handles same-type events at different places via `-2`, `-3`,
  ... id suffixes (commit `0b6afbe`); you don't need to invent unique types.

## Invocation

```
/changjuan-extract-v2 chapter:N
```

`N` is an integer (1–108). The output will be written to
`data/extractions/ch{N:02d}/extract-v2.yaml`.

## Steps

### 1. Load skill context

Read these files before extracting anything:
- `.claude/skills/changjuan-extract-v2/system-prompt.md` — extraction rules (Chinese)
- `.claude/skills/changjuan-extract-v2/extraction-schema.yaml` — canonical field/type reference
- `.claude/skills/changjuan-extract-v2/examples/ch01-excerpt.md` — fully worked example

### 2. Determine chapter number

Accept `chapter:N` from the invocation (first positional arg or `chapter:N` kwarg).
Convert to zero-padded two-digit form: `ch{N:02d}`.

### 3. Dump chunks for the chapter

```bash
./scripts/read-chapter $CHAPTER --print
```

This writes `data/readable/ch{N:02d}.md` (Markdown with one section per chunk,
chunk id + paragraph range as the heading, raw paragraph text in a fenced block)
and also prints to stdout. Read it once before starting extraction — it's the
single source of truth for `chunk_id`, paragraph ranges, and the exact NFC bytes
of every quote you'll pull.

If `read-chapter` reports "no chunks found", stop and report. The pre-flight
verb (`changjuan extract`) should have caught this — re-run it and investigate.

### 4. Extract entities per chunk

For **each chunk** (process in `paragraph_start` order):

Follow `system-prompt.md` to extract all persons, events, places, states, and
relations visible in that chunk's text.

Key mechanics:

- **Chunk-local ids**: `p1`, `p2`, … for persons; `e1`, `e2`, … for events;
  `pl1`, `pl2`, … for places; `s1`, `s2`, … for states. Reset the counter per
  chunk. Relations reference entities by these same local ids.
- **Citation block** (required on every record):
  ```yaml
  citation:
    chunk_id: "chk:dzl:1:0"   # exact chunk id from the DB query
    paragraph: 4               # absolute chapter-paragraph number (matches the
                               # chunk's [paragraph_start, paragraph_end] range
                               # as shown by read-chapter; min 1 per schema)
    quote: "宣王御驾亲征，败绩于千亩"  # verbatim substring of chunk.text
    span: [0, 0]               # leave as [0, 0] — fill-spans script computes this
  ```
  - `quote` must be a verbatim substring of `chunk.text` (NFC-normalized).
  - Shortest quote that attests the claim. Typical length: 5–30 characters.
  - Do NOT include trailing 。/！/，/" punctuation in the quote value.
  - Do NOT include Chinese typographer's quotes (`"`, `"`) that bracket the
    quote itself — they differ in Unicode codepoint from `"` and break substring
    matching.
- **Justifications map** (required on every record):
  For each scalar field you populate, add an entry in `justifications` whose
  value is a non-empty substring of `citation.quote` supporting that field.
  Example:
  ```yaml
  justifications:
    canonical_name: "千亩"
    type: "败绩"
  ```
  The loader rejects records with empty justifications or justifications not
  present in the citation quote.

### 5. Accumulate output

Collect all per-chunk records into a single output YAML with top-level keys
`persons`, `events`, `places`, `states`, `relations` — each a list.

Ids must be **unique within the output file**. If the same real-world entity
appears in multiple chunks, emit **one record** for it (citing the earliest
chunk where it appears) and do not duplicate.

Create the output directory and write the file:

```bash
mkdir -p data/extractions/ch$(printf "%02d" $CHAPTER)
# write the YAML to:
# data/extractions/ch$(printf "%02d" $CHAPTER)/extract-v2.yaml
```

### 6. Fill span offsets

```bash
./scripts/fill-spans data/extractions/ch$(printf "%02d" $CHAPTER)/extract-v2.yaml
```

This script reads each record's `citation.chunk_id` and `citation.quote` from
`data/corpus.sqlite`, finds the quote as a substring of `chunk.text`, and writes
the real `[start, end]` byte offsets into `span`. If a quote appears more than
once in the chunk text, the script will prompt for disambiguation.

If `fill-spans` reports "quote not found" for any record, fix the `quote` value
in the YAML (check for punctuation mismatch, full-width vs. half-width, or
Chinese quote-mark contamination) and re-run.

### 6.5. Pre-flight validation (read-only)

```bash
./scripts/check-extraction data/extractions/ch$(printf "%02d" $CHAPTER)/extract-v2.yaml
```

Runs the same JSON-schema + five per-record invariant checks as `extract-load`
but without touching the DB, so iterating on quote/justification fixes is
fast. Catches the common Ch.6-class mistakes:

- justification value not a substring of `citation.quote`
- `citation.quote` not a verbatim substring of the chunk (e.g. you added a
  paraphrase, an ellipsis `……`, or a stray Chinese typographer's quote)
- chunk-local id reference (`primary_place_id: pl9`) not declared anywhere
- `inference_kind` outside the allowlist

Fix everything it reports before moving on. Exit code 0 means safe to load.

### 7. Load into the database

```bash
uv run changjuan extract-load \
  --chapter $CHAPTER \
  --extraction-file data/extractions/ch$(printf "%02d" $CHAPTER)/extract-v2.yaml \
  --prompt-version v2
```

The loader runs schema validation, the four static invariants, and writes
`candidate_*` rows plus a `pipeline_runs` row. Review any reported invariant
violations — they indicate records that were skipped.

### 8. Report

Print a summary:
- Per-kind counts: persons N / events N / places N / states N / relations N.
- Any chunks that produced zero records (struggled-chunks list).
- Loader output: pipeline_run_id, invariant_violations count.

## Constraints

- **No cross-chunk reasoning.** Each chunk is extracted in isolation. Do not
  refer to information from a previous chunk when deciding what to record in
  the current chunk. (The linker stage handles cross-chunk identity resolution.)
- **No hallucinated quotes.** Every `citation.quote` must be a verbatim
  substring of its chunk's text. If you cannot find a clean supporting quote,
  write a shorter one — never paraphrase.
- **No fabricated justifications.** Every value in `justifications` must be a
  non-empty substring of the same record's `citation.quote`.
- **`inference_kind` allowlist (Phase 4):** `explicit_reign_lu`,
  `explicit_reign_zhou`, `explicit_reign_other`, `relative_to_prior_event`,
  `era_only`, `unknown`. The `explicit_reign_other` kind is now resolvable
  (Phase 4 Task 2 implemented the resolver); use it when the chunk anchors a
  date to a non-鲁/周 reign (e.g. "晋文公七年", "齐桓公九年"). The Date dict
  must carry `state_id` (e.g., `sta:jin`), `ruler_ref` (the literal reign name
  used, e.g. "晋文公" or "重耳"), and `reign_year` (1-indexed integer). See
  `concepts/data-model/dates-and-reigns.md` for the resolution rules and the
  states with reign tables (data/reigns/sta_*.yaml).
- **`social_category` enum (11 values):**
  `royalty / noble / official / military / religious / clergy / commoner /
  servant / foreign / mythic / unknown`.
- **Span placeholders:** always write `span: [0, 0]`; never attempt to compute
  character offsets by hand. The `fill-spans` script is authoritative.
