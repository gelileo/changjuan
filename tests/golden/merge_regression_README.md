# Merge Regression Set Conventions

## Purpose

A small hand-curated set of person pairs used to validate `pipeline/stage5_link/` (the linker). Every pair has a known correct disposition (same or different person); the regression test (`tests/integration/test_link_regression.py`) ensures the linker's scoring formula reproduces every decision on every run.

## Source data

Pairs are drawn from:
- Spec §6 (founding spec) — names specific test cases (重耳/晋文公; different 公子重耳 across states).
- Real Eastern-Zhou historical figures with multiple known names (e.g., 管仲/管夷吾, 太子宜臼/周平王).
- Disambiguation cases the linker is expected to handle correctly (e.g., 召公奭 vs 召虎 — same lineage, ~200 years apart).

## Conventions

- **Same-person pairs** must score `>= LINKER_AUTO_MERGE_THRESHOLD` (0.75 in v1).
- **Different-person pairs** must score `< LINKER_AUTO_MERGE_THRESHOLD`. Some are expected to land in the queue (`>= LINKER_QUEUE_THRESHOLD`), others to be skipped entirely.
- Every pair MUST have:
  - `rationale`: one sentence explaining the curator's call.
  - `source`: where the pair came from (text citation, spec section, or rationale-of-construction).
  - `person_a` + `person_b`: both populated with the canonical Person fields.
- Records should reflect what extraction would naturally produce in the wild — don't pre-engineer fields to game the scorer.

## Curation targets

Aim for ≥5 same + ≥5 different, covering at minimum these failure-mode categories:

**Same pairs:**
1. **Cross-life-phase**: 重耳 → 晋文公 (noble exile → king).
2. **字 vs 本名**: 管仲 / 管夷吾.
3. **Short-form fold across chapters**: 重耳 / 公子重耳.
4. **Pre/post-coronation**: 太子宜臼 / 周平王.
5. **本名 vs 谥号**: 小白 / 齐桓公.

**Different pairs:**
1. **Same name, different states**: 公子重耳 (晋) vs 公子重耳 (卫).
2. **Same lineage, different historical figures**: 召公奭 (西周) vs 召虎 (周宣王朝).
3. **Same title, different eras**: 申侯 (西周) vs 申侯 (春秋).
4. **Different individuals with shared field structure**: 太子宜臼 vs 太子伯服.
5. **Different rulers, both 谥号 of same state**: 晋文公 vs 晋灵公.

## Decisions log

Append-only list of judgment calls made during curation.

- YYYY-MM-DD: <decision>
