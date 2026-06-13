---
name: changjuan-extract-cast
description: Extract structured entities (persons, relations, events, groups, themes) from one chapter of a CAST-genre book (世情小说, e.g. 红楼梦, book_id hlm) into a YAML file matching the canonical schema. Use when the user asks to extract chapter N of a cast-profile book. Cast genre = huge cast + domestic relations + clans (四大家族) + social events + themes; NO historical chronology.
---

# changjuan-extract-cast — Stage 3 Extraction Skill (cast profile)

Stage 3 extraction for **cast-profile** books (世情小说). Reads chunked corpus text
for one chapter of `hlm` (红楼梦), extracts knowledge-graph candidates following the
cast system prompt, writes a YAML file, then loads it. Differs from the history
(东周列国志) skill: it mines **domestic relations + clans (groups) + themes**, and
emits **no historical dates** (cast has no `chronology` capability).

## Invocation

```
/changjuan-extract-cast chapter:N
```
`N` is an integer (1–120). Output → `data/books/hlm/extractions/ch{N:02d}/extract-cast.yaml`.

## Steps

### 1. Load skill context
Read before extracting:
- `.claude/skills/changjuan-extract-cast/system-prompt.md` — cast extraction rules (Chinese).
- `.claude/skills/changjuan-extract-cast/extraction-schema.yaml` — canonical field/type reference (top-level keys: `persons`, `events`, `places`, `groups`, `relations`, `themes`).

### 2. Dump chunks for the chapter
```bash
./scripts/read-chapter $CHAPTER --book-id hlm --print
```
Writes `data/books/hlm/readable/ch{N:02d}.md` (one section per chunk: chunk id + paragraph range heading + raw text). This is the single source of truth for `chunk_id`, paragraph ranges, and the exact NFC bytes of every quote.

### 3. Extract per chunk (process in `paragraph_start` order)
Follow `system-prompt.md`. **Local ids are unique across the WHOLE chapter YAML — do NOT reset them per chunk** (the loader keys candidates on `id`, so a reused id collides and the whole chapter fails to load):
`p1,p2…` persons · `e1,e2…` events · `pl1,pl2…` places · `s1,s2…` groups (clans). Keep a single running counter per kind across all chunks. The same real-world entity gets ONE record (earliest chunk) reused by id; never reuse an id for a different entity. Relations + theme occurrences reference these ids.

Every record needs a **citation** block + a **justifications** map:
```yaml
citation:
  chunk_id: "chk:hlm:1:0"   # exact chunk id from read-chapter
  paragraph: 4               # absolute chapter paragraph (matches read-chapter range; min 1)
  quote: "封氏情性贤淑，深明礼义"   # verbatim substring of chunk.text (NFC)
  span: [0, 0]               # leave [0,0] — fill-spans computes it
justifications:
  canonical_name: "封氏"
```
- `quote`: shortest verbatim substring (5–30 chars) attesting the claim. NO paraphrase, NO ellipsis `……`, NO Chinese typographer quotes `“”` bracketing it, NO trailing 。！，punctuation.
- Each populated scalar field needs a `justifications` entry that is a substring of `citation.quote`.

### 4. Accumulate output
One record per real-world entity (cite earliest chunk; ids unique within the file). Top-level keys: `persons`, `events`, `places`, `groups`, `relations`, `themes` (each a list; omit/empty-list any with no records).
```bash
mkdir -p data/books/hlm/extractions/ch$(printf "%02d" $CHAPTER)
# write data/books/hlm/extractions/ch$(printf "%02d" $CHAPTER)/extract-cast.yaml
```

### 5. Fill spans
```bash
./scripts/fill-spans --db data/books/hlm/corpus.sqlite data/books/hlm/extractions/ch$(printf "%02d" $CHAPTER)/extract-cast.yaml
```
Fix any "quote not found" (punctuation / full-width / quote-mark contamination) and re-run.

### 6. Pre-flight validation (read-only)
```bash
./scripts/check-extraction --db data/books/hlm/corpus.sqlite data/books/hlm/extractions/ch$(printf "%02d" $CHAPTER)/extract-cast.yaml
```
Fix everything it reports (justification not substring of quote; quote not verbatim; undeclared local-id reference; bad enum). Exit 0 = safe to load.

### 7. Load
```bash
uv run changjuan extract-load --book-id hlm \
  --chapter $CHAPTER \
  --extraction-file data/books/hlm/extractions/ch$(printf "%02d" $CHAPTER)/extract-cast.yaml \
  --prompt-version cast
```

### 8. Report
Per-kind counts (persons / relations / events / places / groups / themes); any zero-record chunks; loader `pipeline_run_id` + invariant-violations count.

## Constraints
- **No cross-chunk reasoning** — extract each chunk in isolation; the linker resolves cross-chunk identity.
- **No hallucinated quotes / fabricated justifications** — every quote is a verbatim chunk substring; every justification a substring of its quote.
- **No historical dates.** Cast books have no datable chronology. Do not invent dates; if a date field is unavoidable use `inference_kind: unknown`. Prefer omitting dates entirely.
- **`social_category` enum (11):** `royalty / noble / official / military / religious / clergy / commoner / servant / foreign / mythic / unknown`.
- **Span placeholders:** always `span: [0, 0]`; `fill-spans` is authoritative.
