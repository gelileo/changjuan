# HANDOFF — continue 东周列国志 ETL

Pick up the ETL exactly where Ch.94 ended. Self-contained — no prior conversation needed.

---

## Status snapshot (as of 2026-05-30, end of Ch.94)

| Metric | Value |
| --- | --- |
| Chapters loaded (v2) | **Ch.6–94** (Ch.1–5 are golden / pre-v2; do not re-extract) |
| `persons` | 1559 |
| `events` | 1859 |
| `places` | 610 |
| `states` | 78 |
| Open `merge_candidates` | 12 (query for current list — see Curator backlog) |
| Auto-merge rate (recent batches) | ~98% |
| Pipeline threshold | `LINKER_AUTO_MERGE_THRESHOLD=0.70`, `LINKER_QUEUE_THRESHOLD=0.40` |

Next chapter to extract: **Ch.95**. Target era end: Ch.108.

> Note: the export bundle `data/exports/changjuan-export-2026-05-v1/` was frozen mid-ETL (≈Ch.50-era counts) for the reader-app Phase-0 spike; it is NOT current. Re-freeze (`changjuan export <version>`) when the reader app needs up-to-date data.

---

## The procedure (per 4-chapter batch)

For each batch of 4 consecutive chapters:

### 1. Dispatch 4 parallel subagents (one per chapter)

Use the Agent tool with `subagent_type=general-purpose`. Each prompt follows the **subagent template** below. Send all 4 in a single message so they run in parallel.

Wall-clock: ~15–25 min per batch. Ch.49 was longest at ~28 min (densely populated chapter).

### 2. After all 4 return, sequentially load

```bash
for ch in 95 96 97 98; do  # adjust to current batch
    RUN_ID="run:phase6c-ch${ch}-$(date +%s)"
    echo "=== Ch.${ch} RUN_ID=${RUN_ID} ==="
    uv run changjuan extract-load --chapter $ch \
        --extraction-file data/extractions/ch${ch}/extract-v2.yaml \
        --prompt-version v2 --pipeline-run-id "$RUN_ID" 2>&1 | tail -3
    uv run changjuan link "$RUN_ID" 2>&1 | tail -1
    uv run changjuan load "$RUN_ID" 2>&1 | tail -1
    echo ""
done
uv run python -c "
import sqlite3
db = sqlite3.connect('data/changjuan.sqlite')
print(' persons:', db.execute('SELECT COUNT(*) FROM persons').fetchone()[0])
print(' events: ', db.execute('SELECT COUNT(*) FROM events').fetchone()[0])
print(' places: ', db.execute('SELECT COUNT(*) FROM places').fetchone()[0])
print(' states: ', db.execute('SELECT COUNT(*) FROM states').fetchone()[0])
print(' open mcs:', db.execute(\"SELECT COUNT(*) FROM merge_candidates WHERE status='open'\").fetchone()[0])
"
```

### 3. Inspect any queued candidates

```bash
uv run python -c "
import sqlite3, json
db = sqlite3.connect('data/changjuan.sqlite')
for r in db.execute(\"SELECT score, candidate_a_id, candidate_b_id, surface_features_json FROM merge_candidates WHERE status='open' ORDER BY score DESC\"):
    score, cand_id, canon_id, feats = r
    cand = db.execute('SELECT canonical_name, social_category, state_id FROM candidate_persons WHERE id=?', (cand_id,)).fetchone()
    canon = db.execute('SELECT canonical_name, social_category, state_id FROM persons WHERE id=?', (canon_id,)).fetchone()
    print(f'  score={score:.3f}: {cand} vs {canon}')
    print(f'    {json.loads(feats)[\"features\"]}')
"
```

Classify each: REAL MERGE (curator should accept) vs FALSE POSITIVE (curator should reject — usually `<state>+<title>` template collisions like 宋昭公↔宋殇公). Report to user, don't auto-merge.

### 4. Commit knowledge updates if any code changed

This batch loop doesn't touch code, so usually nothing to commit. If a Phase 7 patch lands mid-batch (e.g., schema fix), follow `CLAUDE.md` same-task rule (update `knowledge/concepts/*.md` + `knowledge/log.md`).

---

## Subagent template (copy verbatim, swap chapter number)

```
Extract Chapter N of 东周列国志 into a structured YAML for the changjuan pipeline. Working dir: `/Users/kunlu/Projects/gelileo/unroll/changjuan`. One of 4 parallel chapter extractions; you handle only Ch.N.

## Steps
1. Read `.claude/skills/changjuan-extract-v2/system-prompt.md`.
2. Read `.claude/skills/changjuan-extract-v2/examples/ch01-excerpt.md`.
3. Read `.claude/skills/changjuan-extract-v2/extraction-schema.yaml`.
4. Run `./scripts/read-chapter N` → `data/readable/chNN.md`. Read it.
5. Write `data/extractions/chNN/extract-v2.yaml`.
6. Run `./scripts/fill-spans data/extractions/chNN/extract-v2.yaml` — iterate until 0 errors.
7. Run `./scripts/check-extraction data/extractions/chNN/extract-v2.yaml` — iterate until clean.
8. STOP. Parent runs extract-load / link / load.

## Mandatory gotchas
- **`justifications` substrings of `citation.quote`** (not chunk). #1 rework cause.
- **No paraphrasing in `quote`.** No `……`. Include Chinese smart-quote `"` verbatim when source has `<name>曰："…"`. Or pick non-dialog phrase.
- **Avoid bare `<name>曰`** — pick unique follow-on.
- **`paragraph`**: absolute chapter paragraph; schema min 1.
- **Natural type values** (`处死`, `战`, `朝议`). Loader collision guard handles same-type.
- **`citation.span` always `[0, 0]`**.
- **Date schema (CRITICAL)**: `additionalProperties: false` on date dicts rejects `state_id`/`ruler_ref`/`reign_year` AND validator's `_PHASE2_INFERENCE_KINDS` rejects `explicit_reign_other`. **Never use `explicit_reign_other`** — use `inference_kind: era_only` + `year_bce` + `original` for non-鲁/非-周 reign anchors.
- For `explicit_reign_zhou`/`explicit_reign_lu`: `year_bce` + `original`. One per year per chunk; subsequent same-year events use `relative_to_prior_event`.
- **Convention**: 周庄王元年=697, 周厘王元年=682, 周惠王元年=676, 周襄王元年=651, 周顷王元年=618, 周匡王元年=612, 周定王元年=606 BCE. (Add later 周 kings as needed — 周简王元年=585, 周灵王元年=571, 周景王元年=544, 周敬王元年=519.)
- Single-curly `'…'` vs double-curly `"…"` — different codepoints.

## CRITICAL — Cross-chapter linker variant hint
For returning rulers/notables, include prior canonical_name as variant to force `strong` overlap (auto-merge instead of `partial`-queued). The 本名 is the linker's primary handle. Always-include patterns for Ch.51+ era:
  - `晋灵公` → `{variant: 夷皋, kind: 本名}` + `{variant: 太子夷皋, kind: 别名}`
  - `晋成公` → `{variant: 黑臀, kind: 本名}` + `{variant: 公子黑臀, kind: 别名}`
  - `晋景公` → `{variant: 据, kind: 本名}` (Ch.~58+)
  - `晋厉公` → `{variant: 寿曼, kind: 本名}` (Ch.~58+)
  - `晋悼公` → `{variant: 周, kind: 本名}` + `{variant: 孙周, kind: 别名}` (Ch.~62+)
  - `楚庄王` → `{variant: 旅, kind: 本名}`
  - `楚共王` → `{variant: 审, kind: 本名}` (Ch.~58+)
  - `秦康公` → `{variant: 罂, kind: 本名}` + `{variant: 太子罂, kind: 别名}`
  - `秦共公` → `{variant: 稻, kind: 本名}`
  - `秦桓公` → `{variant: 荣, kind: 本名}` (Ch.~57+)
  - `齐惠公` → `{variant: 元, kind: 本名}` + `{variant: 公子元, kind: 别名}`
  - `齐顷公` → `{variant: 无野, kind: 本名}` (Ch.~52+)
  - `齐灵公` → `{variant: 环, kind: 本名}` (Ch.~57+)
  - `宋文公` → `{variant: 鲍, kind: 本名}` + `{variant: 公子鲍, kind: 别名}`
  - `宋共公` → `{variant: 瑕, kind: 本名}` (Ch.~57+)
  - `郑穆公` → `{variant: 兰, kind: 本名}` + `{variant: 公子兰, kind: 别名}`
  - `郑灵公` → `{variant: 夷, kind: 本名}` (Ch.~52+)
  - `郑襄公` → `{variant: 坚, kind: 本名}` (Ch.~52+)
  - `卫穆公` → `{variant: 速, kind: 本名}` (if applicable)
  - `鲁宣公` → `{variant: 倭, kind: 本名}` + `{variant: 公子倭, kind: 别名}`
  - `赵盾` → `{variant: 盾, kind: 本名}` + `{variant: 赵宣子, kind: 谥号}`
  - `士会` → `{variant: 会, kind: 本名}` + `{variant: 随会, kind: 别名}` + `{variant: 范会, kind: 别名}` + `{variant: 武子, kind: 谥号}`
  - `荀林父` → `{variant: 林父, kind: 本名}` + `{variant: 中行桓子, kind: 别名}`
  - `郤缺` → `{variant: 缺, kind: 本名}` + `{variant: 冀缺, kind: 别名}`
  - Rule of thumb: 谥号-form canonical_name → ALSO include 本名 + state/title-prefixed 别名 (公子X / 太子X / 王子X) when the prior canonical used those forms.

## Scope
~25–35 persons, ~15–22 events, ~5–10 places, ~5–10 states, ~50–100 relations. Skip background-only mentions (those only appearing in 朝代综述 / not on-stage).

## Cross-chapter awareness
canonical_name + full `variants[]`. Linker auto-merges via name+state+social_category.

## Report (~200 words)
Counts, YAML path, unresolved errors, date anchors used, schema/prompt mismatches.
```

---

## Variant-hint cheat sheet — keep growing

When the linker queues a `partial` overlap, it usually means the next chapter's subagent missed a variant. Append to the template above. The current best-yields from Ch.6–50:

- All 谥号-form canonicals (X公, X王) should carry 本名 (single char) + state/title-prefixed 别名.
- Officials: 谥号 (武子, 文子, 宣子, 成子, 桓子) + 本名 + 字 (子犯, 子鱼, 子产).
- Recurring 字 patterns: 子+X for many. Always check if prior chapter used the 字.

---

## Curator backlog (12 open mcs as of Ch.94)

User will merge/reject these in the Streamlit app. Don't auto-merge from the agent — surface them and wait. The list is no longer enumerated here (it churns every batch); query the current open queue:

```bash
uv run python -c "
import sqlite3, json
db = sqlite3.connect('data/changjuan.sqlite')
for r in db.execute(\"SELECT score, candidate_a_id, candidate_b_id, surface_features_json FROM merge_candidates WHERE status='open' ORDER BY score DESC\"):
    score, cand_id, canon_id, feats = r
    cand = db.execute('SELECT canonical_name, social_category, state_id FROM candidate_persons WHERE id=?', (cand_id,)).fetchone()
    canon = db.execute('SELECT canonical_name, social_category, state_id FROM persons WHERE id=?', (canon_id,)).fetchone()
    print(f'  {score:.3f}: {cand} vs {canon}')
    print(f'    {json.loads(feats)[\"features\"]}')
"
```

Recurring false-positive pattern to watch: `<state>+<title>` template collisions between different rulers (e.g. 宋昭公↔宋殇公, 晋文公↔晋惠公) — same state + social_category + shared template chars, different person. Curator should reject these (Phase 7 candidate: a personal-name-char gate in the linker).

---

## Known Phase 7 issues (DEFERRED — do not fix during ETL)

These surfaced during ETL but are out of scope until ETL completes. If a subagent or the user asks, just note them.

1. **Date schema/prompt mismatch**: `extract_output.py` `additionalProperties: false` on date dicts rejects `state_id`/`ruler_ref`/`reign_year` despite system-prompt §7.1 instructing the LLM to include them. Workaround: `era_only` always.
2. **Stale `_PHASE2_INFERENCE_KINDS` allowlist** in `validate_record` rejects `explicit_reign_other` despite schema allowing it. Workaround: use `era_only` for non-鲁/非-周 reign anchors.
3. **Template-collision false positives** in linker: `<state>+<title>` canonicals (晋文公↔晋惠公, 宋昭公↔宋殇公) score `partial` due to shared chars. Needs a "personal-name char must match" gate.
4. **Cross-chapter naming-variant auto-fold** patterns: `公子X` ↔ `<state>子X`, `太子+本名` ↔ `<state>+本名` — currently relies on variant-hint discipline in subagent prompts.
5. **Duplicate canonicals stranded by queue+load race**: e.g. `per:宋庄公` (Ch.8). Audit when ETL completes.
6. **73+ open conflicts** in canonical (deferred until Phase 7 conflict UI).

---

## Safety / process constraints

- **Never** push to remote unless user explicitly asks.
- **Never** force-push, reset --hard, or skip pre-commit hooks (`--no-verify`).
- **Only** commit when user asks. The batch loop does NOT commit by default (YAMLs go into `data/extractions/` which is gitignored except for v1 baseline).
- Before risky DB cleanup: snapshot `data/changjuan.sqlite` to a `.bak` file. **Always** `rm -f data/changjuan.sqlite-{shm,wal}` before restoring from `.bak` (WAL overlay can corrupt restored state).
- Subagent session/rate limits hit occasionally — if a subagent writes the YAML but doesn't finish validation, run `./scripts/fill-spans` + `./scripts/check-extraction` manually as recovery (parent context).

---

## Bibliography of related docs (read on demand)

- `CLAUDE.md` — project guardrails, same-task rule for knowledge updates.
- `docs/superpowers/specs/2026-05-20-changjuan-design.md` — original design spec.
- `knowledge/concepts/pipeline/extraction.md` — stage 3 internals + pre-flight helpers.
- `knowledge/concepts/pipeline/linking.md` — scoring formula + promotion-waiver.
- `knowledge/concepts/pipeline/load-and-merge.md` — stage 7 internals + collision guard.
- `.claude/skills/changjuan-extract-v2/SKILL.md` — the per-chapter workflow used by humans.
- `.claude/skills/changjuan-extract-v2/system-prompt.md` — the §⓪ 7 revision rules.

---

## Resume / parallel-session bootstrap

To resume this session: `claude --dangerously-skip-permissions --resume ffa9b518-be3e-4b06-81c8-9958bc0b5347` (from `changjuan/`).

To start a clean parallel ETL session: `cd changjuan/` and paste:

> Read `HANDOFF-ETL.md`. Continue ETL from Ch.95. Run one 4-chapter batch (Ch.95–98), report counts and any queued candidates, then stop and wait for me to say "onward".
