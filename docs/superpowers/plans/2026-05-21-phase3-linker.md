# changjuan Phase 3 — Stage 5 (Link & Dedup) for Persons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Stage 5 (deterministic surface-feature linker) for Person entities. New `pipeline/stage5_link/` package + `changjuan link` CLI verb between `extract-load` and `load`. Stage 7's loader gains a `match_target_id` honor + canonical-name fallback. Validated against a hand-curated merge regression set (~10 pairs).

**Architecture:** Score-based dispatch: variant overlap + state agreement + clan + social_category + temporal proximity → weighted score → auto-merge (≥ 0.75) writes `match_target_id` + audit; queue (≥ 0.40) writes `merge_candidates`; skip (< 0.40) leaves no trace. Hard veto on no-variant-overlap. No LLM judge (deferred to Phase 4). Persons only (other entity kinds use existing stage-7 name-match).

**Tech Stack:** Python 3.14, `uv`, SQLite (stdlib), pytest, typer, structlog, pyyaml, jsonschema. **No anthropic SDK is added.** Pre-commit (ruff, ruff-format, mypy strict, drift-check, regen-extraction-schema) all must remain clean.

---

## Before you start

1. **Verify Phase 2 baseline.** Run `./scripts/phase2-prep.sh` and confirm it reports 16+ pass / acceptable warns / 0 fail. If failures, fix those first.
2. **Read the spec.** `docs/superpowers/specs/2026-05-21-phase3-linker-design.md` is the source of truth. This plan operationalizes that spec; where they conflict, the spec governs and the plan should be updated.
3. **Pre-commit binary on PATH.** Pre-commit lives in `.venv/bin/`. The git hook calls `pre-commit` bare. Use `uv tool install pre-commit` (one-time) OR prefix every commit with `PATH=".venv/bin:$PATH"`.

---

## Definition of done (Phase 3)

- `candidate_persons.match_target_id` (TEXT, nullable, no FK) added to `canonical_schema.sql`.
- `pipeline/stage5_link/` package shipped: `scoring.py` (pure-function scorer), `candidate_pool.py` (relevance pre-filter), `linker.py` (orchestrator), `__init__.py` re-exports `link_run` + `person_match_score`.
- `pipeline/cli.py` has `link <pipeline_run_id>` verb.
- `pipeline/stage7_load/persons.py` honors `match_target_id` with canonical-name fallback + missing-target warning + cross-run chain resolution.
- `pipeline/config.py` has `LINKER_AUTO_MERGE_THRESHOLD = 0.75` + `LINKER_QUEUE_THRESHOLD = 0.40` + comment block documenting v1 calibration.
- `tests/golden/merge_regression.yaml` exists with ≥5 same-person + ≥5 different-person pairs; loader validates structure.
- All unit tests + regression test + Ch.1 link-then-load integration test green.
- `@pytest.mark.regression` test passes: every same-pair scores ≥ 0.75; every different-pair scores < 0.75.
- `@pytest.mark.golden` test passes: `link` then `load` on Ch.1's v2 candidates → exactly 13 canonical persons.
- New article `concepts/pipeline/linking.md` + updates to `knowledge-graph.md`, `load-and-merge.md`, `runtime/cli.md`, `CLAUDE.md`.
- `scripts/phase3-prep.sh` reports green.
- Phase 2's full acceptance still passes.

---

## File structure (what Phase 3 creates or modifies)

```text
changjuan/
├── pipeline/
│   ├── schemas/
│   │   └── canonical_schema.sql       # MODIFY: add candidate_persons.match_target_id column
│   ├── config.py                      # MODIFY: add LINKER_AUTO_MERGE_THRESHOLD + LINKER_QUEUE_THRESHOLD
│   ├── cli.py                         # MODIFY: add `link` verb
│   ├── stage5_link/                   # NEW package
│   │   ├── __init__.py                # NEW: re-exports link_run, person_match_score
│   │   ├── scoring.py                 # NEW: person_match_score(a, b)
│   │   ├── candidate_pool.py          # NEW: candidate_pool(conn, candidate_id, run_id)
│   │   └── linker.py                  # NEW: link_run(conn, pipeline_run_id)
│   └── stage7_load/
│       └── persons.py                 # MODIFY: honor match_target_id + cross-run chain helper
├── tests/
│   ├── golden/
│   │   ├── merge_regression.yaml      # NEW (hand-curated by you)
│   │   ├── merge_regression_README.md # NEW: curation conventions + sources
│   │   └── regression_loader.py       # NEW: parser + validator
│   ├── unit/
│   │   ├── test_scoring.py            # NEW
│   │   ├── test_candidate_pool.py     # NEW
│   │   ├── test_linker.py             # NEW
│   │   ├── test_link_cli.py           # NEW
│   │   ├── test_stage7_match_target.py# NEW
│   │   └── test_regression_loader.py  # NEW
│   └── integration/
│       ├── test_link_regression.py    # NEW @pytest.mark.regression
│       └── test_link_ch01.py          # NEW @pytest.mark.golden
├── scripts/
│   └── phase3-prep.sh                 # NEW
├── knowledge/
│   ├── concepts/
│   │   ├── pipeline/
│   │   │   ├── linking.md             # NEW
│   │   │   └── load-and-merge.md      # MODIFY
│   │   ├── data-model/
│   │   │   └── knowledge-graph.md     # MODIFY
│   │   └── runtime/
│   │       └── cli.md                 # MODIFY
│   ├── index.md                       # MODIFY: add linking.md row
│   └── log.md                         # MODIFY across most tasks
├── CLAUDE.md                          # MODIFY: add stage5_link mapping row
└── pyproject.toml                     # MODIFY: register `regression` pytest marker
```

---

## Task index

**Step 1 — Schema addition** (Tasks 1)
1. Add `match_target_id TEXT` column + update knowledge-graph.md

**Step 2 — Regression set infrastructure** (Tasks 2-3)
2. Scaffold `tests/golden/merge_regression.yaml` + README
3. Implement `tests/golden/regression_loader.py` + tests

**Step 3 — Curate the regression set** (Task 4)
4. Hand-curate ≥5 same + ≥5 different person pairs *(human task)*

**Step 4 — Person scoring formula** (Tasks 5-6)
5. Add `LINKER_*` thresholds to `pipeline/config.py`
6. Implement `pipeline/stage5_link/scoring.py` + unit tests

**Step 5 — Candidate pool + linker orchestrator** (Tasks 7-8)
7. Implement `pipeline/stage5_link/candidate_pool.py` + unit tests
8. Implement `pipeline/stage5_link/linker.py::link_run` + unit tests + `__init__.py`

**Step 6 — CLI verb + stage-7 integration** (Tasks 9-11)
9. Add `changjuan link` CLI verb + tests
10. Modify `pipeline/stage7_load/persons.py` to honor `match_target_id` + cross-run chain helper
11. Update `concepts/runtime/cli.md` + `concepts/pipeline/load-and-merge.md`

**Step 7 — Knowledge article + regression test** (Tasks 12-13)
12. Create `concepts/pipeline/linking.md` + update CLAUDE.md mapping table + knowledge/index.md
13. Add `@pytest.mark.regression` integration test against the curated regression set

**Step 8 — Phase 3 acceptance** (Tasks 14-16)
14. Add `@pytest.mark.golden` integration test `test_link_ch01.py`
15. Create `scripts/phase3-prep.sh`
16. Phase 3 acceptance check + Phase 3 complete log entry

---

## Task 1 — Add `match_target_id` column

**Files:**
- Modify: `pipeline/schemas/canonical_schema.sql`
- Modify: `knowledge/concepts/data-model/knowledge-graph.md`
- Modify: `knowledge/log.md`

- [ ] **Step 1.1: Add the column to the schema**

In `pipeline/schemas/canonical_schema.sql`, find the `CREATE TABLE candidate_persons (...)` block. Add `match_target_id TEXT` (nullable, no default, no FK) as a new column. Insert near the end of the column list, before any constraints. Position is not strictly important since SQLite allows any column ordering — pick a sensible spot (after `clan_name`, before `confidence`, OR at the very end before the closing paren — pick what reads naturally).

Reference example (adapt to whatever the existing column list actually looks like):

```sql
CREATE TABLE IF NOT EXISTS candidate_persons (
    id                  TEXT PRIMARY KEY,
    canonical_name      TEXT NOT NULL,
    gender              TEXT,
    social_category     TEXT,
    state_id            TEXT,
    clan_name           TEXT,
    match_target_id     TEXT,                                      -- NEW: Phase 3 stage-5 linker hint
    confidence          REAL,
    chunk_id            TEXT,
    quote               TEXT,
    pipeline_run_id     TEXT NOT NULL,
    -- ... other columns ...
);
```

**Don't** add a foreign-key constraint — per spec §6 ("anti-patterns to resist"), match_target_id may point at a same-run candidate id that hasn't been promoted to canonical yet; an FK would reject.

- [ ] **Step 1.2: Drop + recreate the canonical DB**

Phase 1 was greenfield and Phase 2 has only test/CI data in `data/changjuan.sqlite`. The schema is recreated via `CREATE TABLE IF NOT EXISTS` on each `open_canonical_db` call, but **existing tables aren't altered**. Either:

A. Drop the existing DB so it recreates with the new column:
```bash
rm -f data/changjuan.sqlite
```

B. Or `ALTER TABLE` it manually:
```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('data/changjuan.sqlite')
c.execute('ALTER TABLE candidate_persons ADD COLUMN match_target_id TEXT')
c.commit()
print('column added')
"
```

Option B preserves the v2 extraction's candidate rows; option A is cleaner but loses the v2 baseline (you'd need to re-run extract-load against the fixture to repopulate). For Phase 3 development, option B is preferred — the v2 candidates are useful for the Ch.1 link test (Task 14).

After the migration, verify the column exists:

```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('data/changjuan.sqlite')
cols = [r[1] for r in c.execute('PRAGMA table_info(candidate_persons)')]
print('match_target_id present:', 'match_target_id' in cols)
"
```

Expected: `match_target_id present: True`.

- [ ] **Step 1.3: Update `knowledge-graph.md`**

Open `knowledge/concepts/data-model/knowledge-graph.md`. Find the section on the Person entity or the candidate-tables description. Add a paragraph:

```markdown
### `candidate_persons.match_target_id` (Phase 3)

A nullable text column on `candidate_persons` populated by Stage 5 (the linker, `pipeline/stage5_link/`). When set, it points at the canonical Person id (or, in cross-run cases, another candidate id within the same run) that Stage 7 should merge this candidate into. When null, Stage 7 falls back to its existing canonical_name-match logic. No FK constraint — the target may be a sibling candidate not yet promoted to canonical; the resolution chain runs at load time. The full lifecycle + scoring formula is documented in `concepts/pipeline/linking.md`.
```

Update the article's `affects:` glob to include `pipeline/stage5_link/**` if not already covered elsewhere.

- [ ] **Step 1.4: Run the test suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: all Phase 2 tests still green. The schema addition is backward-compatible (column is nullable; existing code that doesn't reference it keeps working).

- [ ] **Step 1.5: Knowledge-log entry + commit**

Append to `knowledge/log.md`:

```markdown
## [2026-MM-DD] schema: add candidate_persons.match_target_id (Phase 3 Task 1)

Added a nullable TEXT column `match_target_id` to `candidate_persons` in
`pipeline/schemas/canonical_schema.sql`. Stage 5 (the new linker, lands
across Phase 3 Tasks 5-8) populates this column with the canonical Person
id to merge into; Stage 7 honors it with canonical-name fallback (Task 10).
No FK constraint — value may be a same-run sibling candidate id that's
not yet promoted to canonical; resolution chain runs at load time.

Articles touched: concepts/data-model/knowledge-graph.md (new
match_target_id paragraph + affects glob).
```

```bash
git add pipeline/schemas/canonical_schema.sql \
        knowledge/concepts/data-model/knowledge-graph.md \
        knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
schema: add candidate_persons.match_target_id (Phase 3 Task 1)

Nullable TEXT column populated by the new Stage 5 linker (lands in
Phase 3 Tasks 5-8). Stage 7 honors it with canonical-name fallback;
no FK constraint because the target may be a sibling candidate not yet
promoted to canonical.

Articles touched: concepts/data-model/knowledge-graph.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Scaffold `tests/golden/merge_regression.yaml` + README

**Files:**
- Create: `tests/golden/merge_regression.yaml`
- Create: `tests/golden/merge_regression_README.md`
- Modify: `knowledge/log.md`

- [ ] **Step 2.1: Create the YAML skeleton**

Create `tests/golden/merge_regression.yaml`:

```yaml
# Merge Regression Set — Phase 3 Stage 5 (linker) validation
#
# Two top-level lists of person pairs. The linker's @pytest.mark.regression
# test (tests/integration/test_link_regression.py) asserts:
#   - every same_person_pairs entry scores >= LINKER_AUTO_MERGE_THRESHOLD
#   - every different_person_pairs entry scores < LINKER_AUTO_MERGE_THRESHOLD
#
# Each pair carries:
#   rationale  — one-sentence explanation (why this pair is same / different)
#   source     — citation (chapter or external text, e.g., "《史记·晋世家》")
#   person_a   — full Person record (canonical_name, variants[], state_id, ...)
#   person_b   — full Person record (same shape)
#
# Person record shape mirrors the canonical schema. Fields:
#   canonical_name  (required)
#   variants        (optional list of {variant, kind})
#   state_id        (optional, e.g., "sta:jin")
#   social_category (optional, enum: royalty / noble / official / military /
#                    religious / clergy / commoner / servant / foreign / mythic / unknown)
#   clan_name       (optional)
#   birth_date      (optional, structured Date dict)
#   death_date      (optional, structured Date dict)

same_person_pairs: []

different_person_pairs: []
```

Empty lists are valid — the loader handles empty input. Task 4 (human curation) populates them.

- [ ] **Step 2.2: Create the README**

Create `tests/golden/merge_regression_README.md`:

```markdown
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
```

- [ ] **Step 2.3: Verify YAML parses**

```bash
uv run python -c "
import yaml
data = yaml.safe_load(open('tests/golden/merge_regression.yaml').read())
print(f'same: {len(data[\"same_person_pairs\"])} | different: {len(data[\"different_person_pairs\"])}')
"
```

Expected: `same: 0 | different: 0`.

- [ ] **Step 2.4: Commit**

Append to `knowledge/log.md`:

```markdown
## [2026-MM-DD] golden: scaffold merge_regression.yaml + README (Phase 3 Task 2)

Created `tests/golden/merge_regression.yaml` (empty lists) + curation
conventions in `tests/golden/merge_regression_README.md`. Phase 3 Stage 5
(linker) validates against this set; the @pytest.mark.regression test
(Task 13) asserts every entry scores in the expected bucket.

Articles touched: none (scaffold + conventions doc only).
```

```bash
git add tests/golden/merge_regression.yaml tests/golden/merge_regression_README.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
golden: scaffold merge_regression.yaml + README (Phase 3 Task 2)

Empty lists; curation conventions documented. Phase 3 Task 4 populates
with ≥5 same + ≥5 different person pairs.

no knowledge impact: scaffold + conventions doc only.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — Implement `tests/golden/regression_loader.py` + tests

**Files:**
- Create: `tests/golden/regression_loader.py`
- Create: `tests/unit/test_regression_loader.py`
- Modify: `knowledge/log.md`

- [ ] **Step 3.1: Failing tests**

Create `tests/unit/test_regression_loader.py`:

```python
"""Merge regression set loader — validates YAML structure + cross-references."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.golden.regression_loader import RegressionLoadError, load_regression_set


def _write(p: Path, data: dict) -> None:
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def reg_dir(tmp_path: Path) -> Path:
    """Returns the directory in which the regression YAML should live."""
    return tmp_path


def _minimal_pair(name_a: str = "甲", name_b: str = "乙") -> dict:
    return {
        "rationale": "test",
        "source": "synthetic",
        "person_a": {"canonical_name": name_a},
        "person_b": {"canonical_name": name_b},
    }


def test_loads_empty_set(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {"same_person_pairs": [], "different_person_pairs": []})
    regset = load_regression_set(f)
    assert regset["same_person_pairs"] == []
    assert regset["different_person_pairs"] == []


def test_loads_populated_set(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {
        "same_person_pairs": [_minimal_pair("重耳", "晋文公")],
        "different_person_pairs": [_minimal_pair("重耳", "重耳")],
    })
    regset = load_regression_set(f)
    assert len(regset["same_person_pairs"]) == 1
    assert regset["same_person_pairs"][0]["person_a"]["canonical_name"] == "重耳"
    assert len(regset["different_person_pairs"]) == 1


def test_rejects_missing_top_level_key(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {"same_person_pairs": []})  # missing different_person_pairs
    with pytest.raises(RegressionLoadError, match="different_person_pairs"):
        load_regression_set(f)


def test_rejects_pair_missing_required_field(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {
        "same_person_pairs": [{
            # missing rationale, source
            "person_a": {"canonical_name": "甲"},
            "person_b": {"canonical_name": "乙"},
        }],
        "different_person_pairs": [],
    })
    with pytest.raises(RegressionLoadError, match="rationale|source"):
        load_regression_set(f)


def test_rejects_pair_missing_person(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {
        "same_person_pairs": [{
            "rationale": "x", "source": "y",
            "person_a": {"canonical_name": "甲"},
            # missing person_b
        }],
        "different_person_pairs": [],
    })
    with pytest.raises(RegressionLoadError, match="person_b"):
        load_regression_set(f)


def test_rejects_person_missing_canonical_name(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {
        "same_person_pairs": [{
            "rationale": "x", "source": "y",
            "person_a": {"state_id": "sta:jin"},  # missing canonical_name
            "person_b": {"canonical_name": "乙"},
        }],
        "different_person_pairs": [],
    })
    with pytest.raises(RegressionLoadError, match="canonical_name"):
        load_regression_set(f)


def test_rejects_invalid_social_category(reg_dir: Path) -> None:
    f = reg_dir / "merge_regression.yaml"
    _write(f, {
        "same_person_pairs": [{
            "rationale": "x", "source": "y",
            "person_a": {"canonical_name": "甲", "social_category": "wizard"},
            "person_b": {"canonical_name": "乙"},
        }],
        "different_person_pairs": [],
    })
    with pytest.raises(RegressionLoadError, match="social_category"):
        load_regression_set(f)
```

- [ ] **Step 3.2: Run — must fail (ImportError)**

```bash
uv run pytest tests/unit/test_regression_loader.py -v
```

Expected: ImportError on `from tests.golden.regression_loader import ...`.

- [ ] **Step 3.3: Implement the loader**

Create `tests/golden/regression_loader.py`:

```python
"""Merge regression set loader. Validates structure + cross-references."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_VALID_SOCIAL_CATEGORIES = frozenset({
    "royalty", "noble", "official", "military", "religious",
    "clergy", "commoner", "servant", "foreign", "mythic", "unknown",
})

_REQUIRED_TOP_KEYS = ("same_person_pairs", "different_person_pairs")
_REQUIRED_PAIR_FIELDS = ("rationale", "source", "person_a", "person_b")


class RegressionLoadError(Exception):
    """Raised when the merge regression YAML fails validation."""


def _validate_person(person: dict, where: str) -> None:
    if not isinstance(person, dict):
        raise RegressionLoadError(f"{where}: person record must be a dict")
    if not person.get("canonical_name"):
        raise RegressionLoadError(f"{where}: missing or empty canonical_name")
    cat = person.get("social_category")
    if cat is not None and cat not in _VALID_SOCIAL_CATEGORIES:
        raise RegressionLoadError(
            f"{where}: invalid social_category '{cat}' "
            f"(must be one of {sorted(_VALID_SOCIAL_CATEGORIES)})"
        )


def _validate_pair(pair: dict, where: str) -> None:
    if not isinstance(pair, dict):
        raise RegressionLoadError(f"{where}: pair must be a dict")
    for f in _REQUIRED_PAIR_FIELDS:
        if f not in pair:
            raise RegressionLoadError(f"{where}: missing required field '{f}'")
    _validate_person(pair["person_a"], f"{where}.person_a")
    _validate_person(pair["person_b"], f"{where}.person_b")


def load_regression_set(path: Path) -> dict[str, Any]:
    """Load + validate the merge regression set YAML. Raises on schema violations."""
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RegressionLoadError(f"{path.name}: top level must be a dict")

    for key in _REQUIRED_TOP_KEYS:
        if key not in data:
            raise RegressionLoadError(f"{path.name}: missing required key '{key}'")
        if not isinstance(data[key], list):
            raise RegressionLoadError(f"{path.name}: '{key}' must be a list")

    for i, pair in enumerate(data["same_person_pairs"]):
        _validate_pair(pair, f"same_person_pairs[{i}]")
    for i, pair in enumerate(data["different_person_pairs"]):
        _validate_pair(pair, f"different_person_pairs[{i}]")

    return data
```

Add type annotations as needed for mypy strict.

- [ ] **Step 3.4: Run tests — must pass**

```bash
uv run pytest tests/unit/test_regression_loader.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 3.5: Validate the real regression YAML (currently empty) loads**

```bash
uv run python -c "
from pathlib import Path
from tests.golden.regression_loader import load_regression_set
data = load_regression_set(Path('tests/golden/merge_regression.yaml'))
print(f'loaded: same={len(data[\"same_person_pairs\"])} different={len(data[\"different_person_pairs\"])}')
"
```

Expected: `loaded: same=0 different=0`.

- [ ] **Step 3.6: Commit**

Append to `knowledge/log.md`. Drift-check may flag `tests/**/*.py` → testing.md; touch the article if needed.

```bash
git add tests/golden/regression_loader.py tests/unit/test_regression_loader.py knowledge/log.md
# Add knowledge/concepts/verification/testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(golden): regression_loader.py validates merge regression YAML structure

Validates top-level shape, required pair fields (rationale/source/person_a/
person_b), required person fields (canonical_name), and social_category
enum membership. Raises RegressionLoadError on any violation. Seven tests
cover happy path + each failure mode.

no knowledge impact: test infrastructure; covered by README in
tests/golden/merge_regression_README.md (Phase 3 Task 2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Hand-curate the regression set *(human task)*

**This is a human task.** The implementer cannot do this — it requires domain judgment about Eastern-Zhou historical figures + the curator's understanding of how the linker should behave.

**Files (populated by hand):**
- `tests/golden/merge_regression.yaml` — replace the empty lists with ≥5 same + ≥5 different person pairs.

**Procedure:**

- [ ] **Step 4.1: Read the curation conventions**

```bash
cat tests/golden/merge_regression_README.md
```

Refresh on the curation targets + conventions before adding pairs.

- [ ] **Step 4.2: Add the suggested 10 pairs**

Edit `tests/golden/merge_regression.yaml`. For each pair listed in the README's curation targets, fill in the YAML. Sample (drawn from spec §3):

```yaml
same_person_pairs:
  - rationale: 重耳 (公子) and 晋文公 are the same person across his exile and ruler phases
    source: 《史记·晋世家》/《左传·僖公二十三年》
    person_a:
      canonical_name: 重耳
      variants:
        - { variant: 公子重耳, kind: 别名 }
      state_id: sta:jin
      social_category: noble
      clan_name: 姬
      death_date: { year_bce: 628, uncertainty: point, inference_kind: explicit_reign_other }
    person_b:
      canonical_name: 晋文公
      variants:
        - { variant: 重耳, kind: 本名 }
        - { variant: 文公, kind: 谥号 }
      state_id: sta:jin
      social_category: royalty
      clan_name: 姬
      death_date: { year_bce: 628, uncertainty: point, inference_kind: explicit_reign_other }
  # ... add 4 more same-person pairs ...

different_person_pairs:
  - rationale: 公子重耳 of 晋 (the famous one) vs. unrelated 公子重耳 mentioned in 卫 chronicles
    source: spec §6 — "different 公子重耳 across states"
    person_a:
      canonical_name: 重耳
      variants:
        - { variant: 公子重耳, kind: 别名 }
      state_id: sta:jin
      social_category: noble
      clan_name: 姬
    person_b:
      canonical_name: 重耳
      variants:
        - { variant: 公子重耳, kind: 别名 }
      state_id: sta:wei
      social_category: noble
  # ... add 4 more different-person pairs ...
```

Reference the README's curation targets list (Task 2 wrote it). For each entry, include the rationale + source + the fields the linker cares about (`canonical_name`, `variants`, `state_id`, `social_category`, `clan_name`, `birth_date`/`death_date` when known).

Use `inference_kind: explicit_reign_other` for non-鲁/周 reign dates. The Phase 2 allowlist rejected this kind for stage 3, but the regression-set context is metadata-only (these dates aren't being pushed through the stage 3 validator); the loader doesn't enforce the Phase 2 allowlist.

- [ ] **Step 4.3: Validate**

```bash
uv run python -c "
from pathlib import Path
from tests.golden.regression_loader import load_regression_set
data = load_regression_set(Path('tests/golden/merge_regression.yaml'))
print(f'same: {len(data[\"same_person_pairs\"])} | different: {len(data[\"different_person_pairs\"])}')
for p in data['same_person_pairs']:
    print(f'  SAME: {p[\"person_a\"][\"canonical_name\"]} ↔ {p[\"person_b\"][\"canonical_name\"]} ({p[\"rationale\"]})')
for p in data['different_person_pairs']:
    print(f'  DIFF: {p[\"person_a\"][\"canonical_name\"]} vs {p[\"person_b\"][\"canonical_name\"]} ({p[\"rationale\"]})')
"
```

Expected: `same: ≥5 | different: ≥5` plus a per-pair summary. If `RegressionLoadError` is raised, fix the YAML and re-run.

- [ ] **Step 4.4: Append entries to the README's decisions log**

For each substantive judgment call made during curation (e.g., "I categorized 召虎 as official rather than military despite his 大宗伯 role having military responsibilities"), append a line to the README's decisions log:

```markdown
- YYYY-MM-DD: 召虎's social_category is `official`, not `military`. His 大宗伯 title is primarily ritual/administrative; military command appears only in 周宣王 era's specific 征伐 sequences. The classification matches Ch.1's golden treatment of 召虎.
```

- [ ] **Step 4.5: Commit**

Append to `knowledge/log.md`:

```markdown
## [2026-MM-DD] golden: hand-curated merge regression set (Phase 3 Task 4)

Filled in `tests/golden/merge_regression.yaml`: <N> same-person pairs
+ <N> different-person pairs. Curation per the README's targets:
covers cross-life-phase folding (重耳/晋文公), 字↔本名 (管仲/管夷吾),
short-form folds, pre/post-coronation (太子宜臼/周平王), 本名/谥号
(小白/齐桓公) + the FP risk cases (same name different states; same
lineage different eras; different rulers same state).

Decisions log entries appended to README.

Articles touched: none (regression data + conventions doc).
```

```bash
git add tests/golden/merge_regression.yaml tests/golden/merge_regression_README.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(golden): hand-curated merge regression set (Phase 3 Task 4)

≥5 same + ≥5 different person pairs covering the spec §6 + spec §3
failure modes the linker must handle correctly. Decisions log entries
appended for each substantive judgment call.

no knowledge impact: regression data + README updates.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Add `LINKER_*` thresholds to `pipeline/config.py`

**Files:**
- Modify: `pipeline/config.py`
- Modify: `tests/unit/test_config.py`
- Modify: `knowledge/concepts/runtime/configuration.md`
- Modify: `knowledge/log.md`

- [ ] **Step 5.1: Failing test**

Append to `tests/unit/test_config.py`:

```python
def test_phase3_linker_thresholds_exist() -> None:
    from pipeline import config

    assert 0 < config.LINKER_AUTO_MERGE_THRESHOLD <= 1
    assert 0 < config.LINKER_QUEUE_THRESHOLD < config.LINKER_AUTO_MERGE_THRESHOLD
```

- [ ] **Step 5.2: Run — must fail (AttributeError on `LINKER_*`)**

```bash
uv run pytest tests/unit/test_config.py::test_phase3_linker_thresholds_exist -v
```

- [ ] **Step 5.3: Add the constants**

Append to `pipeline/config.py` (preserve all existing content):

```python
# Phase 3 — Stage 5 (linker) thresholds
#
# Dispatch logic in pipeline/stage5_link/linker.py::link_run:
#   score >= LINKER_AUTO_MERGE_THRESHOLD → auto-merge (writes match_target_id)
#   LINKER_QUEUE_THRESHOLD <= score < auto → queue (writes merge_candidates row)
#   score < LINKER_QUEUE_THRESHOLD       → skip (candidate creates new canonical at load)
#
# Recalibration history:
#   - 2026-MM-DD (initial, Phase 3 Task 5): auto=0.75, queue=0.40.
#     Why auto=0.75: strong variant (+0.50) + state agreement (+0.20) = 0.70,
#     just under threshold; ≥1 additional positive (+0.10) bumps to 0.80 = auto-merge.
#     Why queue=0.40: partial variant (+0.20) + state agreement (+0.20) = 0.40
#     exactly at threshold = minimum to land in the queue for human review.
LINKER_AUTO_MERGE_THRESHOLD: float = 0.75
LINKER_QUEUE_THRESHOLD: float = 0.40
```

- [ ] **Step 5.4: Run + update article**

```bash
uv run pytest tests/unit/test_config.py -v
uv run pytest -q
```

Expected: all green.

Open `knowledge/concepts/runtime/configuration.md`. Find the constants list (Phase 2 added `GOLDEN_PR_THRESHOLDS` etc.). Add an entry for `LINKER_AUTO_MERGE_THRESHOLD` + `LINKER_QUEUE_THRESHOLD` describing their roles and the recalibration policy. Update the `affects:` glob if needed.

- [ ] **Step 5.5: Commit**

Append knowledge log entry. Commit:

```bash
git add pipeline/config.py tests/unit/test_config.py \
        knowledge/concepts/runtime/configuration.md knowledge/log.md
# Add tests/unit/test_config.py if drift-check requires testing.md update
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(config): Phase 3 linker thresholds (auto=0.75, queue=0.40)

Initial v1 calibration documented in the config.py comment block. Stage 5
linker (lands in Tasks 7-8) dispatches by these thresholds.

Articles touched: concepts/runtime/configuration.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — Implement `pipeline/stage5_link/scoring.py` + unit tests

**Files:**
- Create: `pipeline/stage5_link/__init__.py` (skeleton — will be extended in Task 8)
- Create: `pipeline/stage5_link/scoring.py`
- Create: `tests/unit/test_scoring.py`
- Modify: `knowledge/log.md`

- [ ] **Step 6.1: Failing tests**

Create `tests/unit/test_scoring.py`:

```python
"""Person matcher scoring formula — pure function over two Person records."""

from __future__ import annotations

from pipeline.stage5_link.scoring import person_match_score


def _p(name: str, **fields) -> dict:
    """Minimal Person record builder."""
    rec: dict = {"canonical_name": name}
    rec.update(fields)
    return rec


def test_hard_veto_when_no_variant_overlap() -> None:
    a = _p("重耳", state_id="sta:jin", clan_name="姬", social_category="noble")
    b = _p("管仲", state_id="sta:jin", clan_name="姬", social_category="noble")
    result = person_match_score(a, b)
    assert result["score"] == 0.0
    assert result["features"]["variant_overlap"] == "none"


def test_strong_variant_overlap_canonical_in_other_variants() -> None:
    """Canonical name of A appears in B's variants[] → strong variant overlap."""
    a = _p("重耳")
    b = _p("晋文公", variants=[{"variant": "重耳", "kind": "本名"}])
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "strong"
    assert result["score"] == 0.50  # only strong variant contributes; no other signals


def test_partial_variant_overlap_non_canonical_match() -> None:
    """Non-canonical variants match → partial overlap."""
    a = _p("X", variants=[{"variant": "shared_alias", "kind": "别名"}])
    b = _p("Y", variants=[{"variant": "shared_alias", "kind": "别名"}])
    result = person_match_score(a, b)
    assert result["features"]["variant_overlap"] == "partial"
    assert result["score"] == 0.20


def test_full_perfect_match() -> None:
    """Strong variant + state same + clan same + category same + temporal compatible."""
    a = _p("重耳",
           variants=[{"variant": "公子重耳", "kind": "别名"}],
           state_id="sta:jin", clan_name="姬", social_category="noble",
           death_date={"year_bce": 628, "uncertainty": "point",
                       "inference_kind": "explicit_reign_other"})
    b = _p("公子重耳",
           variants=[{"variant": "重耳", "kind": "本名"}],
           state_id="sta:jin", clan_name="姬", social_category="noble",
           death_date={"year_bce": 628, "uncertainty": "point",
                       "inference_kind": "explicit_reign_other"})
    result = person_match_score(a, b)
    assert result["score"] == 1.00  # clamped
    assert result["features"]["state_agreement"] == "same"
    assert result["features"]["clan_agreement"] == "same"
    assert result["features"]["social_category_agreement"] == "same"
    assert result["features"]["temporal_proximity"] == "compatible"


def test_state_disagreement_subtracts() -> None:
    a = _p("重耳", variants=[{"variant": "公子重耳", "kind": "别名"}], state_id="sta:jin")
    b = _p("公子重耳", state_id="sta:wei")  # different state
    result = person_match_score(a, b)
    assert result["features"]["state_agreement"] == "different"
    # +0.50 (strong variant) - 0.40 (state diff) = 0.10
    assert abs(result["score"] - 0.10) < 1e-9


def test_clan_disagreement_subtracts() -> None:
    a = _p("X", variants=[{"variant": "shared", "kind": "别名"}],
           state_id="sta:jin", clan_name="姬")
    b = _p("Y", variants=[{"variant": "shared", "kind": "别名"}],
           state_id="sta:jin", clan_name="姚")  # different clan
    result = person_match_score(a, b)
    assert result["features"]["clan_agreement"] == "different"
    # +0.20 (partial variant) + 0.20 (state) - 0.20 (clan diff) = 0.20
    assert abs(result["score"] - 0.20) < 1e-9


def test_temporal_conflict_subtracts() -> None:
    """Dates ~200 years apart trigger temporal_proximity = conflict."""
    a = _p("X", variants=[{"variant": "shared", "kind": "别名"}],
           death_date={"year_bce": 950, "uncertainty": "point", "inference_kind": "era_only"})
    b = _p("Y", variants=[{"variant": "shared", "kind": "别名"}],
           birth_date={"year_bce": 700, "uncertainty": "point", "inference_kind": "era_only"})
    result = person_match_score(a, b)
    assert result["features"]["temporal_proximity"] == "conflict"
    # +0.50 (strong) - 0.30 (temporal conflict) = 0.20
    assert abs(result["score"] - 0.20) < 1e-9


def test_one_null_does_not_penalize() -> None:
    """When state_id missing on one side, no penalty (insufficient evidence)."""
    a = _p("X", variants=[{"variant": "shared", "kind": "别名"}], state_id="sta:jin")
    b = _p("Y", variants=[{"variant": "shared", "kind": "别名"}])  # no state_id
    result = person_match_score(a, b)
    assert result["features"]["state_agreement"] == "one_null"
    assert abs(result["score"] - 0.20) < 1e-9  # just the partial variant


def test_score_clamps_to_zero() -> None:
    """Heavy negative contributions should clamp at 0, not go negative."""
    a = _p("X", variants=[{"variant": "shared", "kind": "别名"}],
           state_id="sta:jin", clan_name="姬", social_category="noble",
           death_date={"year_bce": 950, "uncertainty": "point", "inference_kind": "era_only"})
    b = _p("Y", variants=[{"variant": "shared", "kind": "别名"}],
           state_id="sta:wei", clan_name="姚", social_category="royalty",
           birth_date={"year_bce": 700, "uncertainty": "point", "inference_kind": "era_only"})
    result = person_match_score(a, b)
    # +0.20 - 0.40 - 0.20 - 0.10 - 0.30 = -0.80 → clamp to 0.0
    assert result["score"] == 0.0


def test_score_clamps_to_one() -> None:
    """If formula ever exceeds 1.0 (it shouldn't currently, but defensive), clamp to 1.0."""
    # All positive contributions: 0.50 + 0.20 + 0.10 + 0.10 + 0.10 = 1.00
    a = _p("重耳", variants=[{"variant": "公子重耳", "kind": "别名"}],
           state_id="sta:jin", clan_name="姬", social_category="noble",
           death_date={"year_bce": 628, "uncertainty": "point",
                       "inference_kind": "explicit_reign_other"})
    b = _p("公子重耳", variants=[{"variant": "重耳", "kind": "本名"}],
           state_id="sta:jin", clan_name="姬", social_category="noble",
           death_date={"year_bce": 628, "uncertainty": "point",
                       "inference_kind": "explicit_reign_other"})
    result = person_match_score(a, b)
    assert result["score"] == 1.0
```

- [ ] **Step 6.2: Run — must fail (module missing)**

```bash
uv run pytest tests/unit/test_scoring.py -v
```

- [ ] **Step 6.3: Implement scoring.py**

Create `pipeline/stage5_link/__init__.py`:

```python
"""Stage 5 — Link & Dedup for Person entities (Phase 3).

Package layout:
  scoring.py       — pure-function scorer: person_match_score(a, b) → {score, features}
  candidate_pool.py — relevance pre-filter for the linker
  linker.py        — link_run(conn, pipeline_run_id) orchestrator
"""

from pipeline.stage5_link.scoring import person_match_score

__all__ = ["person_match_score"]
```

Create `pipeline/stage5_link/scoring.py`:

```python
"""Person matcher scoring formula. Pure function over two Person records.

Returns {"score": float in [0, 1], "features": dict of dimension classifications}.

Hard veto: variant_overlap == "none" → score 0.0 regardless of other signals.
Otherwise: weighted sum (see comments) clamped to [0, 1].
"""

from __future__ import annotations

from typing import Any


_TEMPORAL_CONFLICT_GAP_YEARS = 150  # death_a more than this many years before birth_b → conflict
_TEMPORAL_ERA_OVERLAP_YEARS = 200   # within this range = compatible


def _variants_set(person: dict) -> set[str]:
    """Set of all name strings: canonical_name + all variant strings."""
    names = {person.get("canonical_name")}
    for v in person.get("variants", []) or []:
        if isinstance(v, dict) and v.get("variant"):
            names.add(v["variant"])
    return {n for n in names if n}


def _classify_variant_overlap(a: dict, b: dict) -> str:
    """Return 'strong', 'partial', or 'none'."""
    a_canon = a.get("canonical_name")
    b_canon = b.get("canonical_name")
    a_variants = _variants_set(a)
    b_variants = _variants_set(b)

    # Strong: either canonical is in the OTHER's variants[] (i.e., the canonical
    # of one side is a recognized variant of the other side).
    a_variant_names = {v.get("variant") for v in a.get("variants", []) or []
                       if isinstance(v, dict)}
    b_variant_names = {v.get("variant") for v in b.get("variants", []) or []
                       if isinstance(v, dict)}
    if a_canon and a_canon in b_variant_names:
        return "strong"
    if b_canon and b_canon in a_variant_names:
        return "strong"
    if a_canon and b_canon and a_canon == b_canon:
        return "strong"

    # Partial: any other name overlap
    if a_variants & b_variants:
        return "partial"
    return "none"


def _classify_field_agreement(a: dict, b: dict, field: str) -> str:
    """Return 'same', 'one_null', or 'different'."""
    av = a.get(field)
    bv = b.get(field)
    if av is None and bv is None:
        return "one_null"
    if av is None or bv is None:
        return "one_null"
    return "same" if av == bv else "different"


def _classify_temporal_proximity(a: dict, b: dict) -> str:
    """Return 'compatible', 'unknown', or 'conflict'.

    Conflict: death_a is more than _TEMPORAL_CONFLICT_GAP_YEARS BEFORE birth_b
    (or vice versa). BCE years count backward, so 'before' means HIGHER year_bce.

    Compatible: dates fall within _TEMPORAL_ERA_OVERLAP_YEARS of each other.
    """
    a_dates = [a.get("birth_date"), a.get("death_date")]
    b_dates = [b.get("birth_date"), b.get("death_date")]
    a_years = [d.get("year_bce") for d in a_dates if isinstance(d, dict) and d.get("year_bce")]
    b_years = [d.get("year_bce") for d in b_dates if isinstance(d, dict) and d.get("year_bce")]

    if not a_years or not b_years:
        return "unknown"

    # Check for incompatible gap. "a died long before b was born" or vice versa.
    a_death = a.get("death_date", {}) or {}
    b_birth = b.get("birth_date", {}) or {}
    if a_death.get("year_bce") and b_birth.get("year_bce"):
        if a_death["year_bce"] - b_birth["year_bce"] > _TEMPORAL_CONFLICT_GAP_YEARS:
            return "conflict"
    b_death = b.get("death_date", {}) or {}
    a_birth = a.get("birth_date", {}) or {}
    if b_death.get("year_bce") and a_birth.get("year_bce"):
        if b_death["year_bce"] - a_birth["year_bce"] > _TEMPORAL_CONFLICT_GAP_YEARS:
            return "conflict"

    # General era proximity check: if any date pair is within era_overlap_years, compatible.
    closest_gap = min(abs(ay - by) for ay in a_years for by in b_years)
    if closest_gap > _TEMPORAL_ERA_OVERLAP_YEARS:
        return "conflict"
    return "compatible"


def person_match_score(a: dict, b: dict) -> dict[str, Any]:
    """Score the likelihood that Person records a and b refer to the same person.

    Returns {"score": float [0,1], "features": {variant_overlap, state_agreement,
    clan_agreement, social_category_agreement, temporal_proximity, ...}}.
    """
    features = {
        "variant_overlap":            _classify_variant_overlap(a, b),
        "state_agreement":            _classify_field_agreement(a, b, "state_id"),
        "clan_agreement":             _classify_field_agreement(a, b, "clan_name"),
        "social_category_agreement":  _classify_field_agreement(a, b, "social_category"),
        "temporal_proximity":         _classify_temporal_proximity(a, b),
    }

    # Hard veto
    if features["variant_overlap"] == "none":
        return {"score": 0.0, "features": features}

    score = 0.0
    # Positive contributions
    if features["variant_overlap"] == "strong":
        score += 0.50
    elif features["variant_overlap"] == "partial":
        score += 0.20
    if features["state_agreement"] == "same":
        score += 0.20
    if features["clan_agreement"] == "same":
        score += 0.10
    if features["social_category_agreement"] == "same":
        score += 0.10
    if features["temporal_proximity"] == "compatible":
        score += 0.10

    # Negative contributions
    if features["state_agreement"] == "different":
        score -= 0.40
    if features["temporal_proximity"] == "conflict":
        score -= 0.30
    if features["clan_agreement"] == "different":
        score -= 0.20
    if features["social_category_agreement"] == "different":
        score -= 0.10

    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))

    return {"score": score, "features": features}
```

Add type annotations as needed for mypy strict. The `dict` returns may need to be `dict[str, Any]` per the project's pattern.

- [ ] **Step 6.4: Run tests — must all pass**

```bash
uv run pytest tests/unit/test_scoring.py -v
uv run pytest -q
```

Expected: all 10 scoring tests pass + all prior tests still green.

- [ ] **Step 6.5: Commit**

Append knowledge log entry. Drift-check may flag `pipeline/stage5_link/**` → no article exists yet (lands in Task 12); use `no knowledge impact:` body line.

```bash
git add pipeline/stage5_link/ tests/unit/test_scoring.py knowledge/log.md
# Plus knowledge/concepts/verification/testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage5): person_match_score scoring formula (Phase 3 Task 6)

Pure-function scorer. Hard-veto on no-variant-overlap; weighted sum
otherwise, clamped to [0, 1]. Feature dimensions: variant_overlap,
state_agreement, clan_agreement, social_category_agreement,
temporal_proximity. Ten unit tests cover hard-veto + every positive +
every negative + clamping (both directions).

no knowledge impact: pipeline/stage5_link/** glob has no article yet;
concepts/pipeline/linking.md lands in Task 12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — Implement `pipeline/stage5_link/candidate_pool.py` + unit tests

**Files:**
- Create: `pipeline/stage5_link/candidate_pool.py`
- Create: `tests/unit/test_candidate_pool.py`
- Modify: `knowledge/log.md`

- [ ] **Step 7.1: Failing tests**

Create `tests/unit/test_candidate_pool.py`:

```python
"""candidate_pool — relevance pre-filter for the Stage 5 linker."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage5_link.candidate_pool import candidate_pool


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_candidate(conn: sqlite3.Connection, *, run_id: str, cand_id: str,
                    name: str, state_id: str | None = None,
                    variants: list[str] | None = None) -> None:
    conn.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, state_id, chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'chk:t', '', 0.9, ?)",
        (cand_id, name, state_id, run_id),
    )
    for v in variants or []:
        conn.execute(
            "INSERT INTO candidate_person_variants (id, candidate_person_id, variant, kind) "
            "VALUES (?, ?, ?, ?)",
            (f"{cand_id}-v-{v}", cand_id, v, "别名"),
        )
    conn.commit()


def _seed_canonical(conn: sqlite3.Connection, *, person_id: str, name: str,
                    state_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO persons (id, canonical_name, state_id, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'auto', 0.9, 'run:test')",
        (person_id, name, state_id),
    )
    conn.commit()


def test_pool_includes_canonical_with_shared_canonical_name(conn: sqlite3.Connection) -> None:
    _seed_canonical(conn, person_id="per:zhong-er", name="重耳", state_id="sta:jin")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳", state_id="sta:jin")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert any(p["canonical_name"] == "重耳" for p in pool)
    assert any(p["target_kind"] == "canonical" for p in pool)


def test_pool_includes_same_run_sibling_with_overlap(conn: sqlite3.Connection) -> None:
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p2", name="重耳")  # sibling
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert any(p["target_kind"] == "candidate" for p in pool)


def test_pool_excludes_self(conn: sqlite3.Connection) -> None:
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert all(p.get("target_id") != "cand:per:run:1:p1" for p in pool)


def test_pool_excludes_other_run_candidates(conn: sqlite3.Connection) -> None:
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    _seed_candidate(conn, run_id="run:OTHER", cand_id="cand:per:run:OTHER:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert all(p["target_id"] != "cand:per:run:OTHER:p1" for p in pool)


def test_pool_excludes_no_overlap_canonical(conn: sqlite3.Connection) -> None:
    _seed_canonical(conn, person_id="per:zhong-shan-fu", name="仲山甫")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert all(p["canonical_name"] != "仲山甫" for p in pool)


def test_pool_includes_variant_match(conn: sqlite3.Connection) -> None:
    _seed_canonical(conn, person_id="per:jin-wen-gong", name="晋文公")
    # Seed a person_variants row linking 晋文公 to variant "重耳"
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) "
        "VALUES ('pv:1', 'per:jin-wen-gong', '重耳', '本名')"
    )
    conn.commit()
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳")
    pool = candidate_pool(conn, "cand:per:run:1:p1", "run:1")
    assert any(p["canonical_name"] == "晋文公" for p in pool)
```

- [ ] **Step 7.2: Run — must fail**

```bash
uv run pytest tests/unit/test_candidate_pool.py -v
```

- [ ] **Step 7.3: Implement candidate_pool.py**

Create `pipeline/stage5_link/candidate_pool.py`:

```python
"""Relevance pre-filter for the Stage 5 linker.

Avoids O(N²) by filtering plausible match targets via SQL name-overlap queries
before any scoring happens. Names that share no characters won't appear; the
scorer never sees them.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _load_candidate(conn: sqlite3.Connection, candidate_id: str) -> dict[str, Any] | None:
    """Load the candidate Person + its variants."""
    row = conn.execute(
        "SELECT id, canonical_name, state_id, social_category, clan_name, "
        "       birth_date_json, death_date_json "
        "FROM candidate_persons WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    variants = [
        {"variant": vr[0], "kind": vr[1]}
        for vr in conn.execute(
            "SELECT variant, kind FROM candidate_person_variants WHERE candidate_person_id = ?",
            (candidate_id,),
        )
    ]
    return _row_to_dict(row, variants, target_kind="self")


def _row_to_dict(row, variants: list, target_kind: str) -> dict[str, Any]:
    import json
    return {
        "target_id":       row[0],
        "target_kind":     target_kind,
        "canonical_name":  row[1],
        "state_id":        row[2],
        "social_category": row[3],
        "clan_name":       row[4],
        "birth_date":      json.loads(row[5]) if row[5] else None,
        "death_date":      json.loads(row[6]) if row[6] else None,
        "variants":        variants,
    }


def _canonical_row_to_dict(row, variants: list) -> dict[str, Any]:
    return _row_to_dict(row, variants, target_kind="canonical")


def _candidate_row_to_dict(row, variants: list) -> dict[str, Any]:
    return _row_to_dict(row, variants, target_kind="candidate")


def candidate_pool(
    conn: sqlite3.Connection,
    candidate_id: str,
    pipeline_run_id: str,
) -> list[dict[str, Any]]:
    """Return plausible match targets for the given candidate id.

    Filters: name-overlap on canonical_name or any variant. Excludes self,
    excludes candidates from other pipeline_run_ids.
    """
    me = _load_candidate(conn, candidate_id)
    if me is None:
        return []

    # Collect all my name strings for the SQL overlap query.
    my_names: set[str] = set()
    if me.get("canonical_name"):
        my_names.add(me["canonical_name"])
    for v in me.get("variants", []):
        if v.get("variant"):
            my_names.add(v["variant"])

    if not my_names:
        return []

    # Build placeholders for IN clause
    placeholders = ",".join("?" * len(my_names))
    names_tuple = tuple(my_names)

    pool: list[dict[str, Any]] = []

    # 1) Canonical persons with matching canonical_name OR matching person_variants.variant
    canonical_rows = conn.execute(
        f"""
        SELECT DISTINCT p.id, p.canonical_name, p.state_id, p.social_category, p.clan_name,
                        p.birth_date_json, p.death_date_json
        FROM persons p
        LEFT JOIN person_variants pv ON pv.person_id = p.id
        WHERE p.canonical_name IN ({placeholders})
           OR pv.variant IN ({placeholders})
        """,
        names_tuple + names_tuple,
    ).fetchall()
    for row in canonical_rows:
        variants = [
            {"variant": vr[0], "kind": vr[1]}
            for vr in conn.execute(
                "SELECT variant, kind FROM person_variants WHERE person_id = ?",
                (row[0],),
            )
        ]
        pool.append(_canonical_row_to_dict(row, variants))

    # 2) Same-run candidate persons with matching canonical_name OR matching variants
    candidate_rows = conn.execute(
        f"""
        SELECT DISTINCT c.id, c.canonical_name, c.state_id, c.social_category, c.clan_name,
                        c.birth_date_json, c.death_date_json
        FROM candidate_persons c
        LEFT JOIN candidate_person_variants cv ON cv.candidate_person_id = c.id
        WHERE c.pipeline_run_id = ?
          AND c.id != ?
          AND (c.canonical_name IN ({placeholders}) OR cv.variant IN ({placeholders}))
        """,
        (pipeline_run_id, candidate_id) + names_tuple + names_tuple,
    ).fetchall()
    for row in candidate_rows:
        variants = [
            {"variant": vr[0], "kind": vr[1]}
            for vr in conn.execute(
                "SELECT variant, kind FROM candidate_person_variants "
                "WHERE candidate_person_id = ?",
                (row[0],),
            )
        ]
        pool.append(_candidate_row_to_dict(row, variants))

    return pool
```

**Schema verification:** before running tests, verify these tables/columns exist:
- `candidate_person_variants(id, candidate_person_id, variant, kind)` — may not exist in the schema if Phase 2 didn't add it. Check via `grep candidate_person_variants pipeline/schemas/canonical_schema.sql`. If missing, the test seed step uses a non-existent table; ADD the table to the schema (with same shape as `person_variants` but `candidate_person_id` FK) before running.

If `candidate_person_variants` doesn't exist yet, add it to `pipeline/schemas/canonical_schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS candidate_person_variants (
    id                       TEXT PRIMARY KEY,
    candidate_person_id      TEXT NOT NULL,
    variant                  TEXT NOT NULL,
    kind                     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidate_person_variants_variant
    ON candidate_person_variants (variant);
```

Then drop+recreate (or ALTER) the test DB. Add a brief note to the schema-addition log entry from Task 1, OR record this as its own log entry.

- [ ] **Step 7.4: Run tests — must pass**

```bash
uv run pytest tests/unit/test_candidate_pool.py -v
```

- [ ] **Step 7.5: Commit**

Append knowledge log entry. Commit:

```bash
git add pipeline/stage5_link/candidate_pool.py tests/unit/test_candidate_pool.py \
        pipeline/schemas/canonical_schema.sql \
        knowledge/log.md
# Plus knowledge/concepts/verification/testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage5): candidate_pool relevance pre-filter (Phase 3 Task 7)

SQL name-overlap pre-filter for the linker. Returns canonical persons +
same-run candidate persons sharing at least one name string with the
target candidate. Excludes self + other-run candidates. Six unit tests
cover canonical match, sibling match, self-exclusion, run-exclusion,
no-overlap exclusion, and variant-table matching.

May add candidate_person_variants table to the schema if not already
present (Phase 2 used variants_json on candidate_persons; this table
gives structured access for the linker's name-overlap query).

no knowledge impact: stage5_link/** glob article lands in Task 12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — Implement `pipeline/stage5_link/linker.py::link_run` + tests

**Files:**
- Create: `pipeline/stage5_link/linker.py`
- Create: `tests/unit/test_linker.py`
- Modify: `pipeline/stage5_link/__init__.py` (add `link_run` to re-export)
- Modify: `knowledge/log.md`

- [ ] **Step 8.1: Failing tests**

Create `tests/unit/test_linker.py`:

```python
"""link_run orchestrator — walks candidate_persons, scores against pool, dispatches by threshold."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline import config
from pipeline.db import open_canonical_db
from pipeline.stage5_link.linker import link_run


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_canonical(c: sqlite3.Connection, *, person_id: str, name: str,
                    state_id: str | None = None, variants: list[tuple[str, str]] | None = None) -> None:
    c.execute(
        "INSERT INTO persons (id, canonical_name, state_id, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'auto', 0.9, 'run:setup')",
        (person_id, name, state_id),
    )
    for v, k in variants or []:
        c.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind) VALUES (?, ?, ?, ?)",
            (f"pv:{person_id}:{v}", person_id, v, k),
        )
    c.commit()


def _seed_candidate(c: sqlite3.Connection, *, run_id: str, cand_id: str, name: str,
                    state_id: str | None = None, social_category: str | None = None,
                    clan_name: str | None = None,
                    variants: list[tuple[str, str]] | None = None) -> None:
    c.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, state_id, social_category, clan_name, "
        " chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, ?, ?, 'chk:t', '', 0.9, ?)",
        (cand_id, name, state_id, social_category, clan_name, run_id),
    )
    for v, k in variants or []:
        c.execute(
            "INSERT INTO candidate_person_variants (id, candidate_person_id, variant, kind) "
            "VALUES (?, ?, ?, ?)",
            (f"cv:{cand_id}:{v}", cand_id, v, k),
        )
    c.commit()


def test_auto_merge_writes_match_target_id_and_audit(conn: sqlite3.Connection) -> None:
    """Strong variant + state same + social same = score ≥ 0.75 → auto-merge."""
    _seed_canonical(conn, person_id="per:jin-wen-gong", name="晋文公",
                    state_id="sta:jin",
                    variants=[("重耳", "本名"), ("文公", "谥号")])
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳", state_id="sta:jin",
                    social_category="royalty")
    # Add social_category to canonical too so they agree
    conn.execute("UPDATE persons SET social_category='royalty' WHERE id='per:jin-wen-gong'")
    conn.commit()

    stats = link_run(conn, "run:1")
    assert stats["auto_merges"] == 1
    assert stats["queued"] == 0

    row = conn.execute(
        "SELECT match_target_id FROM candidate_persons WHERE id='cand:per:run:1:p1'"
    ).fetchone()
    assert row[0] == "per:jin-wen-gong"

    audit = conn.execute(
        "SELECT actor FROM audit_log WHERE entity_id='cand:per:run:1:p1'"
    ).fetchall()
    assert any(r[0] == "link@v1" for r in audit)


def test_queue_writes_merge_candidates_row(conn: sqlite3.Connection) -> None:
    """Mid-score (variant overlap + state DIFFERENT) lands in queue."""
    _seed_canonical(conn, person_id="per:zhong-er-jin", name="重耳",
                    state_id="sta:jin",
                    variants=[("公子重耳", "别名")])
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳", state_id="sta:wei",  # different state
                    variants=[("公子重耳", "别名")])

    stats = link_run(conn, "run:1")
    assert stats["auto_merges"] == 0
    assert stats["queued"] == 1

    mc = conn.execute(
        "SELECT score, surface_features_json FROM merge_candidates WHERE kind='person'"
    ).fetchall()
    assert len(mc) == 1
    assert mc[0][0] >= config.LINKER_QUEUE_THRESHOLD
    assert mc[0][0] < config.LINKER_AUTO_MERGE_THRESHOLD


def test_skip_leaves_no_trace(conn: sqlite3.Connection) -> None:
    """No variant overlap → hard veto → no action."""
    _seed_canonical(conn, person_id="per:other", name="仲山甫")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1", name="重耳")

    stats = link_run(conn, "run:1")
    assert stats["skipped"] == 1
    assert stats["auto_merges"] == 0
    assert stats["queued"] == 0


def test_cross_run_chain_resolution(conn: sqlite3.Connection) -> None:
    """When a candidate's best match is another same-run candidate, match_target_id
    points at that sibling candidate. Stage 7's resolution chain handles it at load
    time; the linker just records the pointer."""
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳", state_id="sta:jin",
                    variants=[("公子重耳", "别名")])
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p2",
                    name="公子重耳", state_id="sta:jin",
                    variants=[("重耳", "本名")])

    stats = link_run(conn, "run:1")
    # One of the two should auto-merge into the other; the other gets nothing.
    matched = conn.execute(
        "SELECT id, match_target_id FROM candidate_persons WHERE pipeline_run_id='run:1' "
        "AND match_target_id IS NOT NULL"
    ).fetchall()
    assert len(matched) == 1
    # The match_target_id points at the OTHER candidate.
    matched_id, target = matched[0]
    assert target in ("cand:per:run:1:p1", "cand:per:run:1:p2")
    assert target != matched_id


def test_returns_stats_dict(conn: sqlite3.Connection) -> None:
    stats = link_run(conn, "run:empty")
    assert set(stats.keys()) == {"candidates_processed", "auto_merges", "queued", "skipped"}
```

- [ ] **Step 8.2: Run — must fail**

```bash
uv run pytest tests/unit/test_linker.py -v
```

- [ ] **Step 8.3: Implement linker.py**

Create `pipeline/stage5_link/linker.py`:

```python
"""Stage 5 (linker) orchestrator. Walks candidate_persons for a pipeline_run_id,
scores each against its candidate pool, dispatches by threshold."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from pipeline import config
from pipeline.stage5_link.candidate_pool import _load_candidate, candidate_pool
from pipeline.stage5_link.scoring import person_match_score


def link_run(conn: sqlite3.Connection, pipeline_run_id: str) -> dict[str, int]:
    """For each candidate_persons row in the run, find plausible match targets and
    dispatch by score:
      - score ≥ LINKER_AUTO_MERGE_THRESHOLD → write match_target_id + audit_log
      - LINKER_QUEUE_THRESHOLD ≤ score < auto → write merge_candidates row
      - score < LINKER_QUEUE_THRESHOLD → no action
    Returns stats: {candidates_processed, auto_merges, queued, skipped}.
    """
    stats = {"candidates_processed": 0, "auto_merges": 0, "queued": 0, "skipped": 0}

    candidate_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM candidate_persons WHERE pipeline_run_id = ? ORDER BY id",
            (pipeline_run_id,),
        )
    ]

    # Track which candidate ids have already been matched, to avoid two-way pairing.
    already_matched: set[str] = set()

    for cand_id in candidate_ids:
        stats["candidates_processed"] += 1

        if cand_id in already_matched:
            # Already became someone else's match_target; skip self-evaluation.
            continue

        me = _load_candidate(conn, cand_id)
        if me is None:
            stats["skipped"] += 1
            continue

        pool = candidate_pool(conn, cand_id, pipeline_run_id)
        if not pool:
            stats["skipped"] += 1
            continue

        # Score each target and pick the best.
        best_target = None
        best_score = 0.0
        best_features: dict[str, Any] = {}
        for target in pool:
            result = person_match_score(me, target)
            if result["score"] > best_score:
                best_score = result["score"]
                best_target = target
                best_features = result["features"]

        if best_target is None or best_score < config.LINKER_QUEUE_THRESHOLD:
            stats["skipped"] += 1
            continue

        if best_score >= config.LINKER_AUTO_MERGE_THRESHOLD:
            # Auto-merge: write match_target_id + audit
            conn.execute(
                "UPDATE candidate_persons SET match_target_id = ? WHERE id = ?",
                (best_target["target_id"], cand_id),
            )
            conn.execute(
                "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
                "before_json, after_json, actor, at) "
                "VALUES (?, 'candidate_persons', ?, 'match_target_id', 'set', "
                "?, ?, 'link@v1', datetime('now'))",
                (
                    f"audit:{uuid.uuid4()}",
                    cand_id,
                    json.dumps({"value": None, "confidence": None}),
                    json.dumps({"value": best_target["target_id"],
                                "score": best_score,
                                "features": best_features}),
                ),
            )
            stats["auto_merges"] += 1
            # If best_target is another candidate, mark it as already matched.
            if best_target.get("target_kind") == "candidate":
                already_matched.add(best_target["target_id"])
        else:
            # Queue: write merge_candidates row.
            conn.execute(
                "INSERT INTO merge_candidates "
                "(id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, status) "
                "VALUES (?, 'person', ?, ?, ?, ?, 'open')",
                (
                    f"mc:{uuid.uuid4()}",
                    cand_id,
                    best_target["target_id"],
                    best_score,
                    json.dumps({"features": best_features, "score": best_score}),
                ),
            )
            stats["queued"] += 1

    conn.commit()
    return stats
```

- [ ] **Step 8.4: Update `__init__.py` to re-export `link_run`**

Edit `pipeline/stage5_link/__init__.py`:

```python
from pipeline.stage5_link.linker import link_run
from pipeline.stage5_link.scoring import person_match_score

__all__ = ["link_run", "person_match_score"]
```

- [ ] **Step 8.5: Run tests + full suite**

```bash
uv run pytest tests/unit/test_linker.py -v
uv run pytest -q
```

- [ ] **Step 8.6: Commit**

Append knowledge log entry. Commit:

```bash
git add pipeline/stage5_link/ tests/unit/test_linker.py knowledge/log.md
# Plus testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage5): link_run orchestrator + dispatch logic (Phase 3 Task 8)

Walks candidate_persons for a pipeline_run_id; for each candidate scores
against its candidate pool; dispatches by threshold:
  - score >= LINKER_AUTO_MERGE_THRESHOLD → match_target_id + audit_log entry
  - LINKER_QUEUE_THRESHOLD <= score < auto → merge_candidates row
  - score < LINKER_QUEUE_THRESHOLD → no action

Cross-run sibling matches handled by tracking already_matched ids and
recording the target candidate id on the source (stage 7 chain helper
in Task 10 resolves to canonical at load time).

Five tests cover: auto-merge writes target+audit; queue writes
merge_candidates; skip leaves no trace; cross-run chain; stats dict shape.

no knowledge impact: pipeline/stage5_link/** article lands in Task 12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — Add `changjuan link` CLI verb + tests

**Files:**
- Modify: `pipeline/cli.py`
- Create: `tests/unit/test_link_cli.py`
- Modify: `knowledge/log.md`

- [ ] **Step 9.1: Failing tests**

Create `tests/unit/test_link_cli.py`:

```python
"""changjuan link CLI verb tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app
from pipeline.db import open_canonical_db


def test_link_cli_runs_on_empty_run(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    runner = CliRunner()
    result = runner.invoke(app, ["link", "run:empty", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "processed=0" in result.stdout


def test_link_cli_reports_counts(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")
    # Seed a candidate with no overlap → will be skipped
    canonical.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES ('cand:per:run:1:p1', '孤独人物', 'chk:t', '', 0.9, 'run:1')"
    )
    canonical.commit()
    runner = CliRunner()
    result = runner.invoke(app, ["link", "run:1", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "processed=1" in result.stdout
    assert "skipped=1" in result.stdout
```

- [ ] **Step 9.2: Run — must fail**

```bash
uv run pytest tests/unit/test_link_cli.py -v
```

- [ ] **Step 9.3: Implement the verb**

Append to `pipeline/cli.py`:

```python
@app.command()
def link(
    pipeline_run_id: str,
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Run Stage 5 (linker) for the given pipeline_run_id.

    Walks candidate_persons, scores against the canonical + same-run pool, and
    dispatches by threshold: auto-merge writes match_target_id + audit_log;
    mid-score writes a merge_candidates row; low-score skips. See
    concepts/pipeline/linking.md for the full picture.
    """
    from pipeline.stage5_link import link_run

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    stats = link_run(canonical, pipeline_run_id)
    typer.echo(
        f"link {pipeline_run_id}: processed={stats['candidates_processed']} "
        f"auto-merged={stats['auto_merges']} queued={stats['queued']} "
        f"skipped={stats['skipped']}"
    )
```

Match the project's existing typer / import style.

- [ ] **Step 9.4: Run + commit**

```bash
uv run pytest tests/unit/test_link_cli.py -v
uv run pytest -q
```

Append knowledge log entry:

```bash
git add pipeline/cli.py tests/unit/test_link_cli.py knowledge/log.md
# Plus testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(cli): link verb wires link_run into the user workflow (Phase 3 Task 9)

Thin shim: `uv run changjuan link <pipeline_run_id>` runs the Stage 5
linker. Sits between extract-load and load in the user workflow. Reports
per-run summary line (processed / auto-merged / queued / skipped).

no knowledge impact: concepts/runtime/cli.md updated in Task 11 where
the full doc lands; pipeline/cli.py is shared by all verbs and already
covered by multiple article mappings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — Modify `pipeline/stage7_load/persons.py` to honor `match_target_id` + cross-run chain helper

**Files:**
- Modify: `pipeline/stage7_load/persons.py`
- Create: `tests/unit/test_stage7_match_target.py`
- Modify: `knowledge/log.md`

- [ ] **Step 10.1: Failing tests**

Create `tests/unit/test_stage7_match_target.py`:

```python
"""Stage 7 honors candidate_persons.match_target_id when set."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db
from pipeline.stage7_load import load_candidate_persons


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return open_canonical_db(tmp_path / "changjuan.sqlite")


def _seed_canonical(c: sqlite3.Connection, *, person_id: str, name: str) -> None:
    c.execute(
        "INSERT INTO persons (id, canonical_name, provenance, confidence, pipeline_run_id) "
        "VALUES (?, ?, 'auto', 0.9, 'run:setup')",
        (person_id, name),
    )
    c.commit()


def _seed_candidate(c: sqlite3.Connection, *, run_id: str, cand_id: str, name: str,
                    match_target_id: str | None = None) -> None:
    c.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, match_target_id, chunk_id, quote, confidence, pipeline_run_id) "
        "VALUES (?, ?, ?, 'chk:t', '', 0.9, ?)",
        (cand_id, name, match_target_id, run_id),
    )
    c.commit()


def test_match_target_id_honored_when_set_to_canonical(conn: sqlite3.Connection) -> None:
    """When match_target_id points at an existing canonical, merge into it (not create new)."""
    _seed_canonical(conn, person_id="per:jin-wen-gong", name="晋文公")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳",  # DIFFERENT canonical_name from target
                    match_target_id="per:jin-wen-gong")
    load_candidate_persons(conn, "run:1")

    # Should NOT create a new canonical Person named 重耳; should merge into 晋文公.
    persons = conn.execute("SELECT id, canonical_name FROM persons").fetchall()
    assert len(persons) == 1
    assert persons[0][0] == "per:jin-wen-gong"


def test_match_target_id_null_falls_back_to_name_match(conn: sqlite3.Connection) -> None:
    """When match_target_id is null, existing canonical_name-match logic runs."""
    _seed_canonical(conn, person_id="per:zhong-er", name="重耳")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳",  # same canonical_name → matches via Phase 2 logic
                    match_target_id=None)
    load_candidate_persons(conn, "run:1")

    persons = conn.execute("SELECT id FROM persons").fetchall()
    assert len(persons) == 1  # not duplicated


def test_match_target_id_missing_target_falls_through_with_warning(conn: sqlite3.Connection,
                                                                    caplog) -> None:
    """When match_target_id points at a non-existent canonical, log warning + fall through."""
    import logging
    _seed_canonical(conn, person_id="per:zhong-er", name="重耳")
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳",
                    match_target_id="per:NONEXISTENT")
    with caplog.at_level(logging.WARNING):
        load_candidate_persons(conn, "run:1")
    # Falls through to canonical_name match → still merges into per:zhong-er.
    persons = conn.execute("SELECT id FROM persons").fetchall()
    assert len(persons) == 1
    assert persons[0][0] == "per:zhong-er"


def test_cross_run_chain_resolves_via_local_map(conn: sqlite3.Connection) -> None:
    """A candidate's match_target_id pointing at a sibling candidate gets resolved
    to the canonical that sibling becomes (in the same load pass)."""
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p1",
                    name="重耳")  # no match_target → creates new canonical
    _seed_candidate(conn, run_id="run:1", cand_id="cand:per:run:1:p2",
                    name="公子重耳",  # match_target points at p1
                    match_target_id="cand:per:run:1:p1")
    load_candidate_persons(conn, "run:1")

    # One canonical should result; p2's record should NOT create per:gong-zi-chong-er.
    persons = conn.execute("SELECT canonical_name FROM persons").fetchall()
    assert len(persons) == 1
    assert persons[0][0] == "重耳"  # p1 created the canonical first; p2 merged in
```

- [ ] **Step 10.2: Run — must fail**

```bash
uv run pytest tests/unit/test_stage7_match_target.py -v
```

- [ ] **Step 10.3: Modify `pipeline/stage7_load/persons.py`**

Open `pipeline/stage7_load/persons.py`. Add at the top of the candidate-processing loop:

```python
# Phase 3: maintain {candidate_id → canonical_id} map for cross-run chain resolution.
local_canonical_map: dict[str, str] = {}

# ... inside the loop, before the existing match logic ...

# Honor match_target_id if Stage 5 set it.
target_id_raw = candidate_row.get("match_target_id")
target_id = None
if target_id_raw is not None:
    target_id = _resolve_canonical_for_candidate_id(conn, target_id_raw, local_canonical_map)
    if target_id is None:
        log.warning(
            "candidate %s has match_target_id=%s but resolution returned no canonical; "
            "falling through to canonical_name match",
            cand_id, target_id_raw,
        )

# Fall back to canonical_name match if target_id is None
if target_id is None:
    existing = conn.execute(
        "SELECT id FROM persons WHERE canonical_name = ?", (canonical_name,),
    ).fetchone()
    target_id = existing[0] if existing else None
else:
    existing = (target_id,)  # treat as if name-match returned the row

# ... rest of the existing Phase 2 merge / create logic uses target_id ...

# After creating or finding the canonical id, record in local_canonical_map for siblings:
local_canonical_map[cand_id] = canonical_id  # canonical_id is whatever this iteration ended up using
```

Add the helper:

```python
def _resolve_canonical_for_candidate_id(
    conn: sqlite3.Connection,
    target_ref: str,
    local_canonical_map: dict[str, str],
) -> str | None:
    """Resolve match_target_id to a canonical Person id.

    target_ref may be:
      - A canonical id like 'per:zhou-xuan-wang' → return it if it exists in persons.
      - A same-run candidate id like 'cand:per:run:1:p1' → look up in
        local_canonical_map (already-processed-in-this-load-pass siblings).

    Returns None if the target doesn't resolve.
    """
    # Sibling candidate path
    if target_ref.startswith("cand:") and target_ref in local_canonical_map:
        return local_canonical_map[target_ref]
    # Canonical path
    if not target_ref.startswith("cand:"):
        row = conn.execute("SELECT id FROM persons WHERE id = ?", (target_ref,)).fetchone()
        if row is not None:
            return row[0]
    return None
```

Place `_resolve_canonical_for_candidate_id` alongside the existing private helpers (above `load_candidate_persons`). The exact integration with the existing loop is a small refactor — read the current persons.py carefully and weave in the match_target_id honor block + the local_canonical_map population without disturbing Phase 2's existing variants accumulation, citation accumulation, conflict emission, or curated-not-overwritten behavior.

- [ ] **Step 10.4: Run tests + full suite**

```bash
uv run pytest tests/unit/test_stage7_match_target.py -v
uv run pytest -q
```

- [ ] **Step 10.5: Commit**

Append knowledge log. Commit:

```bash
git add pipeline/stage7_load/persons.py tests/unit/test_stage7_match_target.py knowledge/log.md
# Plus testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage7): honor candidate_persons.match_target_id (Phase 3 Task 10)

load_candidate_persons now checks match_target_id:
  - set + target exists → merge into that canonical
  - set + target missing → log warning + fall through to canonical_name match
  - null → existing Phase 2 canonical_name-match logic unchanged

Adds _resolve_canonical_for_candidate_id helper for cross-run chain
resolution. When a candidate's match_target_id points at a sibling
candidate in the same run, the local_canonical_map tracks which canonical
each sibling became during the load pass; the chain helper resolves
through it. Four unit tests cover all four match paths.

Articles touched: concepts/pipeline/load-and-merge.md (deferred to Task 11
where the full doc lands).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 — Update `concepts/runtime/cli.md` + `concepts/pipeline/load-and-merge.md`

**Files:**
- Modify: `knowledge/concepts/runtime/cli.md`
- Modify: `knowledge/concepts/pipeline/load-and-merge.md`
- Modify: `knowledge/log.md`

- [ ] **Step 11.1: Update `cli.md`**

Find the verb-list section of `knowledge/concepts/runtime/cli.md`. Add an entry for `link`:

```markdown
### `changjuan link <pipeline_run_id>`

Run Stage 5 (the linker) for one extraction run. Walks `candidate_persons` rows,
scores each against the canonical + same-run pool, dispatches by threshold:

- score ≥ `LINKER_AUTO_MERGE_THRESHOLD` → writes `match_target_id` on the candidate
  + `audit_log` entry tagged `actor='link@v1'`.
- `LINKER_QUEUE_THRESHOLD` ≤ score < auto → writes a `merge_candidates` row with
  `surface_features_json` for human triage.
- score < `LINKER_QUEUE_THRESHOLD` → no action; candidate creates a new canonical
  at load time.

Sits between `extract-load` and `load` in the user workflow. Stage 7's
`load_candidate_persons` honors any `match_target_id` set by `link`; falls back
to the existing canonical_name-match logic when null. See
`concepts/pipeline/linking.md` for the full architecture.

Output: per-run summary line with processed / auto-merged / queued / skipped
counts.
```

- [ ] **Step 11.2: Update `load-and-merge.md`**

Find the persons-loader section of `knowledge/concepts/pipeline/load-and-merge.md`. Add:

```markdown
### `match_target_id` honor (Phase 3)

`load_candidate_persons` checks `candidate_persons.match_target_id`:

- **Set to a canonical id** (e.g., `per:zhou-xuan-wang`) → merge into that canonical;
  skip the canonical_name-match fallback.
- **Set to a sibling candidate id** (e.g., `cand:per:run:1:p1`) → look up in the
  `local_canonical_map` tracked across the load pass to find which canonical the
  sibling became, then merge into that.
- **Set to a non-existent target** → log a warning, fall through to the existing
  canonical_name-match logic (Phase 2 safety net).
- **Null** → existing Phase 2 behavior unchanged.

The Stage 5 linker (`pipeline/stage5_link/linker.py::link_run`) is the only
producer of `match_target_id`. See `concepts/pipeline/linking.md` for the
scoring + threshold logic.
```

Update both articles' `affects:` globs to include `pipeline/stage5_link/**` if not already covered.

- [ ] **Step 11.3: Commit**

```bash
git add knowledge/concepts/runtime/cli.md knowledge/concepts/pipeline/load-and-merge.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
docs(knowledge): document link verb + match_target_id honor (Phase 3 Task 11)

cli.md gains a link section; load-and-merge.md gains a match_target_id
honor subsection. Both reference concepts/pipeline/linking.md for the
linker's full architecture (lands in Task 12).

Articles touched: concepts/runtime/cli.md, concepts/pipeline/load-and-merge.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — Create `concepts/pipeline/linking.md` + update CLAUDE.md + knowledge/index.md

**Files:**
- Create: `knowledge/concepts/pipeline/linking.md`
- Modify: `knowledge/index.md`
- Modify: `CLAUDE.md`
- Modify: `knowledge/log.md`

- [ ] **Step 12.1: Write the article**

Create `knowledge/concepts/pipeline/linking.md` with sections matching the spec's Section 5:

- **What stage 5 does** — deterministic surface-feature matching + threshold-based dispatch over candidate_persons.
- **Why deterministic-only in Phase 3** — LLM judge deferred until curator UI exists for comparison.
- **Feature dimensions + scoring formula** — five dimensions (variant_overlap, state_agreement, clan_agreement, social_category_agreement, temporal_proximity) + the weighted-sum formula + hard-veto on no-variant-overlap. Link to `pipeline/stage5_link/scoring.py` for the implementation.
- **Threshold dispatch** — auto-merge / queue / skip per `LINKER_AUTO_MERGE_THRESHOLD` + `LINKER_QUEUE_THRESHOLD`. Link to `pipeline/config.py` for the values + recalibration history.
- **Merge regression set** — `tests/golden/merge_regression.yaml` + the @pytest.mark.regression test that pins behavior.
- **`match_target_id` lifecycle** — set by `link_run` → honored by `load_candidate_persons` with fallback + cross-run chain resolution. Cross-reference `concepts/pipeline/load-and-merge.md`.
- **`merge_candidates` queue** — what the curator (eventually, UI) consumes; the `surface_features_json` payload makes each row actionable.
- **Cross-run vs intra-run pairs** — handled by tracking `already_matched` in the linker + `local_canonical_map` in stage 7.
- **What would invalidate this article** — list of changes that would require this article to be revised (scoring formula change, threshold semantics change, LLM judge addition, etc.).

Frontmatter (mirror other articles' shape):

```yaml
---
title: Stage 5 — Link & Dedup
type: concept
area: pipeline
updated: 2026-MM-DD
status: thin
load_bearing: true
references:
  - concepts/pipeline/architecture.md
  - concepts/data-model/knowledge-graph.md
  - concepts/pipeline/load-and-merge.md
  - concepts/runtime/cli.md
  - concepts/verification/confidence-and-invariants.md
affects:
  - pipeline/stage5_link/**
  - pipeline/cli.py
  - tests/golden/merge_regression.yaml
  - tests/golden/regression_loader.py
---
```

Aim for ~500-800 words. Use elements-of-style: short subsections, link liberally.

- [ ] **Step 12.2: Update `knowledge/index.md`**

Add a row under the `pipeline` section pointing to the new article.

- [ ] **Step 12.3: Update `CLAUDE.md` article-mapping table**

Add a row:

```
| `pipeline/stage5_link/**` | `concepts/pipeline/linking.md` |
```

- [ ] **Step 12.4: Validate**

```bash
./scripts/validate-articles
```

Expected: clean.

- [ ] **Step 12.5: Commit**

```bash
git add knowledge/concepts/pipeline/linking.md knowledge/index.md CLAUDE.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
docs(knowledge): concepts/pipeline/linking.md — Stage 5 architecture (Phase 3 Task 12)

Documents the deterministic surface-feature linker: five feature dimensions,
weighted-sum scoring with hard-veto on no-variant-overlap, threshold dispatch
(auto-merge / queue / skip), match_target_id lifecycle, merge_candidates
queue + surface_features_json payload, cross-run chain handling. Cross-
references load-and-merge.md (stage-7 honor), runtime/cli.md (link verb),
data-model/knowledge-graph.md (match_target_id field), config (thresholds).

Articles created: concepts/pipeline/linking.md.
Articles touched: knowledge/index.md (pipeline row), CLAUDE.md
(stage5_link mapping row).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13 — Add `@pytest.mark.regression` integration test

**Files:**
- Create: `tests/integration/test_link_regression.py`
- Modify: `pyproject.toml` (register `regression` marker if not yet)
- Modify: `knowledge/log.md`

- [ ] **Step 13.1: Register the `regression` pytest marker**

Open `pyproject.toml`. Find `[tool.pytest.ini_options]`. Add `regression` to the markers list:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: integration tests (slower; need corpus.sqlite)",
    "golden: golden-fixture comparison tests (slowest)",
    "regression: linker regression-set assertions (Phase 3+)",
]
```

(Preserve any existing markers; just add the new one.)

- [ ] **Step 13.2: Write the test**

Create `tests/integration/test_link_regression.py`:

```python
"""Linker regression-set assertion. Every same-pair must score ≥ auto-threshold;
every different-pair must score < auto-threshold."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import config
from pipeline.stage5_link.scoring import person_match_score
from tests.golden.regression_loader import load_regression_set


pytestmark = pytest.mark.regression


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_known_same_pairs_score_above_auto_merge_threshold() -> None:
    regset = load_regression_set(REPO_ROOT / "tests" / "golden" / "merge_regression.yaml")
    failures = []
    for pair in regset["same_person_pairs"]:
        result = person_match_score(pair["person_a"], pair["person_b"])
        if result["score"] < config.LINKER_AUTO_MERGE_THRESHOLD:
            failures.append(
                f"{pair['person_a']['canonical_name']} ↔ {pair['person_b']['canonical_name']}: "
                f"scored {result['score']:.2f} (below {config.LINKER_AUTO_MERGE_THRESHOLD}). "
                f"Rationale: {pair['rationale']}. Features: {result['features']}"
            )
    assert not failures, "\n".join(failures)


def test_known_different_pairs_score_below_auto_merge_threshold() -> None:
    regset = load_regression_set(REPO_ROOT / "tests" / "golden" / "merge_regression.yaml")
    failures = []
    for pair in regset["different_person_pairs"]:
        result = person_match_score(pair["person_a"], pair["person_b"])
        if result["score"] >= config.LINKER_AUTO_MERGE_THRESHOLD:
            failures.append(
                f"{pair['person_a']['canonical_name']} vs {pair['person_b']['canonical_name']}: "
                f"scored {result['score']:.2f} (auto-merge threshold {config.LINKER_AUTO_MERGE_THRESHOLD}). "
                f"Rationale: {pair['rationale']}. Features: {result['features']}"
            )
    assert not failures, "\n".join(failures)
```

- [ ] **Step 13.3: Run**

```bash
uv run pytest -m regression -v
```

Expected: both tests pass.

If a pair lands in the wrong bucket, follow the calibration loop in `pipeline/config.py`'s comment block:
1. Add a feature dimension (rare).
2. Adjust a weight by ±0.05.
3. Move the threshold (last resort).

Document any adjustment in the config.py comment block + the same commit.

- [ ] **Step 13.4: Commit**

```bash
git add tests/integration/test_link_regression.py pyproject.toml knowledge/log.md
# Plus testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
test(integration): linker regression-set assertion (Phase 3 Task 13)

@pytest.mark.regression — pins every same-pair scores ≥ 0.75 (auto-merge)
and every different-pair scores < 0.75. Failure output prints the
rationale + features so calibration is actionable.

If a pair lands in the wrong bucket, follow the calibration loop in
pipeline/config.py's comment block (feature → weight → threshold).

Articles touched: concepts/verification/testing.md (regression test
documented; mark registered in pyproject.toml).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14 — Add `@pytest.mark.golden` integration test `test_link_ch01.py`

**Files:**
- Create: `tests/integration/test_link_ch01.py`
- Modify: `knowledge/log.md`

- [ ] **Step 14.1: Write the test**

Create `tests/integration/test_link_ch01.py`:

```python
"""End-to-end: load the frozen v2 fixture, run linker, then load, assert
exactly 13 canonical persons (Ch.1 golden's count). No false-positive merges
within a single chapter's candidates."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction
from pipeline.stage5_link import link_run
from pipeline.stage7_load import load_candidate_persons


pytestmark = pytest.mark.golden


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_link_then_load_ch01_yields_thirteen_canonical_persons(tmp_path: Path) -> None:
    """Run extract-load → link → load on Ch.1's v2 fixture. Expect exactly
    13 canonical persons (the golden Ch.1 count). Zero false-positive merges
    within the chapter's own candidate set."""
    src_corpus = REPO_ROOT / "data" / "corpus.sqlite"
    if not src_corpus.exists():
        pytest.skip(f"corpus.sqlite missing at {src_corpus}")

    (tmp_path / "data").mkdir()
    shutil.copyfile(src_corpus, tmp_path / "data" / "corpus.sqlite")

    corpus = open_corpus_db(tmp_path / "data" / "corpus.sqlite")
    canonical = open_canonical_db(tmp_path / "data" / "changjuan.sqlite")

    fixture = REPO_ROOT / "tests" / "fixtures" / "ch01-extraction-v1.yaml"
    assert fixture.exists()

    # 1) extract-load: writes candidate_* rows
    load_extraction(
        canonical, corpus_conn=corpus, chapter_num=1,
        extraction_file=fixture, prompt_version="v1",
        pipeline_run_id="run:link-ch01-test",
    )

    # 2) link: writes match_target_id on candidates that auto-merge
    stats = link_run(canonical, "run:link-ch01-test")
    # All Ch.1 candidates are distinct persons (golden has 13 separate ids),
    # so within a single run no auto-merges should fire.
    assert stats["auto_merges"] == 0, (
        f"Phase 3 linker should NOT auto-merge any same-chapter Ch.1 candidates "
        f"(all 13 golden persons are distinct). Got {stats['auto_merges']} auto-merges. "
        f"Either the scorer is too aggressive or the candidate pool is wrong."
    )

    # 3) load: writes canonical persons
    load_candidate_persons(canonical, "run:link-ch01-test")

    n_persons = canonical.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    assert n_persons == 13, (
        f"Ch.1 golden has 13 distinct persons; got {n_persons} canonical persons "
        f"after link+load. Names:\n" +
        "\n".join(r[0] for r in canonical.execute("SELECT canonical_name FROM persons"))
    )
```

- [ ] **Step 14.2: Run**

```bash
uv run pytest -m golden -v
```

Expected: PASS. The Ch.1 v2 fixture has 13 distinct candidate_persons; the linker should preserve all 13 as separate canonical entities (since they're 13 distinct historical figures within the same chapter, none should merge with each other).

If the test FAILS, investigate:
- **auto_merges > 0**: linker is too aggressive. Look at which pairs scored ≥ 0.75 (query `audit_log WHERE actor='link@v1'`). Most likely a scorer issue — same chapter usually has shared state_id (`周`) and clan (`姬`) for officials, which combined with even a weak variant overlap might score too high. Tighten the formula or the candidate_pool's variant-overlap requirement.
- **n_persons != 13**: stage 7's match_target_id integration is wrong, OR the canonical_name-match fallback is misbehaving. Trace via audit_log.

- [ ] **Step 14.3: Commit**

```bash
git add tests/integration/test_link_ch01.py knowledge/log.md
# Plus testing.md if drift-check requires
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
test(integration): link + load on Ch.1 fixture preserves 13 persons (Phase 3 Task 14)

@pytest.mark.golden — runs extract-load → link → load against the frozen
v2 Ch.1 fixture and asserts exactly 13 canonical persons result (the
Ch.1 golden's count). Catches over-aggressive linker / wrong candidate
pool / broken match_target_id integration as a single regression.

Articles touched: concepts/verification/testing.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15 — Create `scripts/phase3-prep.sh`

**Files:**
- Create: `scripts/phase3-prep.sh`
- Modify: `knowledge/log.md`

- [ ] **Step 15.1: Write the script**

Create `scripts/phase3-prep.sh`. Model after `scripts/phase2-prep.sh`'s helpers (color codes, `pass`/`warn`/`fail`/`section`/`log`/`why`). Sections:

```bash
#!/usr/bin/env bash
# changjuan Phase 3 readiness check.
# Run from the repo root: ./scripts/phase3-prep.sh

set -uo pipefail

# (Copy color/helper definitions from scripts/phase2-prep.sh — pass, warn,
#  fail, section, why, log, summary helpers. Same patterns as Phase 2.)

# ... (copy the helper block from phase2-prep.sh) ...

# === PHASE3_DEFERRED — Phase 4 starter backlog ===
PHASE3_DEFERRED=(
  "LLM judge for Stage 5 ambiguous cases — defer until curator UI exists for with/without comparison"
  "explicit_reign_other date parsing + reign tables for 晋/齐/楚/秦/宋/郑/卫… (Phase 2 backlog item)"
  "Ch.~40 golden annotation (城濮之战) — cross-chapter linker validation"
  "Curator UI (Stage 8) — Streamlit; first queue: merge_candidates from Stage 5"
  "Cross-chunk relative-date automation — Phase 2 manual CLI suffices for now"
  "Linker for events / places / states / relations — Phase 3 was persons only"
  "Multi-chapter extraction runs — actually run extract→link→load on chapters 2-108"
)

LOG_FILE="data/logs/phase3-prep.log"
mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"

echo "==== changjuan Phase 3 readiness check ===="

section "1. Phase 2 still passes"
why "Phase 3 must not regress anything from Phase 2."
if ./scripts/phase2-prep.sh >>"$LOG_FILE" 2>&1; then
    pass "phase2-prep.sh green"
else
    fail "phase2-prep.sh FAILED — see log"
fi

section "2. Stage 5 module present"
why "Phase 3's core deliverable."
if [ -d "pipeline/stage5_link" ] && [ -f "pipeline/stage5_link/linker.py" ] \
        && [ -f "pipeline/stage5_link/scoring.py" ] \
        && [ -f "pipeline/stage5_link/candidate_pool.py" ]; then
    pass "pipeline/stage5_link/ package with scoring + candidate_pool + linker"
else
    fail "pipeline/stage5_link/ missing files"
fi

section "3. link CLI verb"
why "User-facing entry point for Stage 5."
if uv run changjuan link --help >>"$LOG_FILE" 2>&1; then
    pass "changjuan link --help works"
else
    fail "changjuan link verb missing"
fi

section "4. Merge regression set"
why "Linker validation surface; must have ≥10 pairs total."
if [ -f "tests/golden/merge_regression.yaml" ]; then
    counts=$(uv run python -c "
from pathlib import Path
from tests.golden.regression_loader import load_regression_set
data = load_regression_set(Path('tests/golden/merge_regression.yaml'))
print(f\"{len(data['same_person_pairs'])} {len(data['different_person_pairs'])}\")
" 2>>"$LOG_FILE")
    same=$(echo "$counts" | awk '{print $1}')
    diff=$(echo "$counts" | awk '{print $2}')
    if [ "$same" -ge 5 ] && [ "$diff" -ge 5 ]; then
        pass "regression set: $same same / $diff different pairs"
    else
        fail "regression set too small: $same same / $diff different (need ≥5 of each)"
    fi
else
    fail "tests/golden/merge_regression.yaml missing"
fi

section "5. Linker regression test"
why "Pins every same-pair scores ≥ auto; every different-pair scores < auto."
if uv run pytest -m regression -q >>"$LOG_FILE" 2>&1; then
    pass "regression test passes"
else
    fail "regression test FAILS — calibrate per pipeline/config.py comment block"
fi

section "6. Ch.1 link-then-load integration test"
why "Confirms link + load on the frozen v2 fixture preserves the 13 golden persons."
if uv run pytest -m golden tests/integration/test_link_ch01.py -q >>"$LOG_FILE" 2>&1; then
    pass "Ch.1 link-then-load yields 13 persons"
else
    fail "test_link_ch01.py FAILED — see log"
fi

section "7. PHASE3_DEFERRED backlog"
why "Phase 4 starter list. Recorded here so Phase 4 has its starting agenda."
log "  ${#PHASE3_DEFERRED[@]} items deferred to Phase 4:"
for item in "${PHASE3_DEFERRED[@]}"; do
    log "    • $item"
done

summary
```

The helper functions (`pass`, `warn`, `fail`, `section`, `why`, `log`, `summary`) should be copy-pasted from `scripts/phase2-prep.sh`'s top section so the output style matches.

- [ ] **Step 15.2: Make executable + run**

```bash
chmod +x scripts/phase3-prep.sh
./scripts/phase3-prep.sh
```

Expected: green across §1-6; §7 prints the 7-item Phase 4 backlog.

- [ ] **Step 15.3: Commit**

Append knowledge log entry:

```bash
git add scripts/phase3-prep.sh knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
chore(scripts): phase3-prep.sh — Phase 3 acceptance check (Phase 3 Task 15)

Mirrors phase2-prep.sh's structure. Sections: Phase 2 still passes
(non-regression), Stage 5 module present, link CLI verb works,
regression set ≥10 pairs, regression test green, Ch.1 link-then-load
preserves 13 persons, PHASE3_DEFERRED summary (7 items: LLM judge,
date expansion, Ch.~40 golden, curator UI, cross-chunk date automation,
linker for other entity kinds, multi-chapter extraction runs).

no knowledge impact: script only; behavior documented in
PHASE3_DEFERRED comments + knowledge/log.md entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16 — Phase 3 acceptance check + Phase 3 complete log entry

**Files:**
- Modify: `knowledge/log.md`

- [ ] **Step 16.1: Final acceptance sweep**

Run all of these in sequence on `main`:

```bash
uv run pytest -q                                  # all unit tests
uv run pytest -m golden -v                        # all golden tests (Phase 2 + Phase 3)
uv run pytest -m integration -v                   # all integration tests
uv run pytest -m regression -v                    # Phase 3 regression test
PATH=".venv/bin:$PATH" uv run pre-commit run --all-files
./scripts/validate-articles
./scripts/drift-check
./scripts/phase2-prep.sh
./scripts/phase3-prep.sh
uv run changjuan link --help                      # verb exists
git log --oneline | head -50                      # clean linear history
```

All must be green. If any fails, fix the underlying cause and re-run.

- [ ] **Step 16.2: Phase 3 complete log entry**

Append to `knowledge/log.md`:

```markdown
## [2026-MM-DD] Phase 3 complete — Stage 5 (Link & Dedup) for Persons shipped

Phase 3 ships Stage 5 — deterministic surface-feature linker for Person
entities only. Persons-only scope was deliberate: it's the highest-stakes
stage (founding spec §3) and persons are the hardest case (variant chains,
state/clan/category agreement, era proximity). LLM judge deferred to Phase 4.

### What shipped

- `pipeline/stage5_link/` package: `scoring.py` (pure-function scorer with
  hard-veto on no-variant-overlap + 5-dimension weighted sum), `candidate_pool.py`
  (relevance pre-filter via SQL name-overlap), `linker.py` (orchestrator with
  threshold-based dispatch + cross-run chain handling).
- `pipeline/cli.py::link` verb between extract-load and load.
- `pipeline/stage7_load/persons.py` honors `match_target_id` with canonical-name
  fallback + missing-target warning + cross-run chain resolution via
  `_resolve_canonical_for_candidate_id`.
- `pipeline/schemas/canonical_schema.sql` gained `candidate_persons.match_target_id`
  (TEXT, nullable, no FK) and `candidate_person_variants` table.
- `pipeline/config.py` thresholds: `LINKER_AUTO_MERGE_THRESHOLD = 0.75`,
  `LINKER_QUEUE_THRESHOLD = 0.40`.
- `tests/golden/merge_regression.yaml` with <N> same + <N> different pairs.
- `tests/golden/regression_loader.py` with 7 unit tests.
- `tests/integration/test_link_regression.py` (`@pytest.mark.regression`).
- `tests/integration/test_link_ch01.py` (`@pytest.mark.golden`).
- `scripts/phase3-prep.sh` acceptance checker.

### Final test counts

<N> total (Phase 2 was 173; Phase 3 added <N> new). Marker breakdown:
- Default: <N>
- `@pytest.mark.integration`: <N>
- `@pytest.mark.golden`: <N>
- `@pytest.mark.regression`: <N>

### Phase 3 acceptance state

- `./scripts/phase2-prep.sh` green
- `./scripts/phase3-prep.sh` green
- All 5 pre-commit hooks clean
- `./scripts/validate-articles` clean
- `./scripts/drift-check` clean

### Articles created/extended

- New: `concepts/pipeline/linking.md`.
- Extended: `concepts/data-model/knowledge-graph.md` (match_target_id field),
  `concepts/pipeline/load-and-merge.md` (match_target_id honor block),
  `concepts/runtime/cli.md` (link verb), `concepts/runtime/configuration.md`
  (LINKER thresholds), `CLAUDE.md` (stage5_link mapping row), `knowledge/index.md`.

### Phase 2 backlog status

Phase 2 deferred 7 items; Phase 3 resolves item #1 (Stage 5 Link & dedup for
persons) + item #6 (relation P/R consolidation — partial, since Phase 3
addresses person-side merging which feeds into relation matching). 5 items
remain → PHASE3_DEFERRED.

### Phase 4 starter backlog (7 items)

(See `scripts/phase3-prep.sh::PHASE3_DEFERRED` for the canonical list.)

1. LLM judge for Stage 5 ambiguous cases.
2. `explicit_reign_other` date parsing + reign tables for non-鲁/周.
3. Ch.~40 golden annotation.
4. Curator UI (Stage 8) — Streamlit; first queue: merge_candidates.
5. Cross-chunk relative-date automation.
6. Linker for events / places / states / relations.
7. Multi-chapter extraction runs (chapters 2-108).

### Next phase

Phase 4 spec written when ready. The PHASE3_DEFERRED list is the seed agenda.
Curator UI (item #4) is the natural starting point — it unblocks the
merge_candidates queue triage that Stage 5 produces, AND provides the
infrastructure for "with-LLM-judge" vs "without-LLM-judge" comparison
(item #1's prerequisite).
```

Fill in `<N>` placeholders with actual counts from your runs.

- [ ] **Step 16.3: Commit**

```bash
git add knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
docs(knowledge): Phase 3 complete — Stage 5 (Link & Dedup) for Persons shipped

Deterministic surface-feature linker for Person entities. 5-dimension
weighted-sum scorer with hard-veto + threshold-based dispatch
(auto-merge / queue / skip). match_target_id honored by stage 7 with
canonical-name fallback. Regression set + Ch.1 link-then-load
integration test confirm 13 distinct persons preserved.

Phase 2 backlog: 2 items resolved (Stage 5 linker for persons; partial
relation consolidation). 5 items remain → PHASE3_DEFERRED. Phase 4
starts with curator UI (unblocks merge_candidates triage + sets up
LLM-judge comparison infrastructure).

no knowledge impact: this commit IS the knowledge impact.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 acceptance check

Before declaring Phase 3 done, run all of:

- [ ] `uv run pytest -q` — all unit tests green.
- [ ] `uv run pytest -m golden -v` — Phase 2 + Phase 3 golden tests green.
- [ ] `uv run pytest -m integration -v` — integration tests green.
- [ ] `uv run pytest -m regression -v` — regression test green.
- [ ] `PATH=".venv/bin:$PATH" uv run pre-commit run --all-files` — clean.
- [ ] `./scripts/validate-articles` — clean.
- [ ] `./scripts/drift-check` — clean.
- [ ] `./scripts/phase2-prep.sh` — still green (no Phase 2 regressions).
- [ ] `./scripts/phase3-prep.sh` — green.
- [ ] `uv run changjuan link --help` — verb is invokable.
- [ ] `git log --oneline` — clean linear history; every commit has either article touch or `no knowledge impact:` body line.

If any check fails, treat as a Phase 3 task and fix before opening Phase 4.

---

## Plan self-review

**Spec coverage:**

| Spec requirement | Plan task(s) |
|---|---|
| `candidate_persons.match_target_id` (Phase 3 §1) | Task 1 |
| `pipeline/stage5_link/` package (§1, §5) | Tasks 6, 7, 8 |
| `changjuan link` CLI verb (§1, §5) | Task 9 |
| Stage 7 honors `match_target_id` (§1, §5) | Task 10 |
| LINKER thresholds in config.py (§1, §4) | Task 5 |
| Merge regression set (§1, §3) | Tasks 2, 3, 4 |
| `concepts/pipeline/linking.md` (§1, §5) | Task 12 |
| Other article updates (§1) | Tasks 1, 5, 11, 12 |
| Regression test (§1, §3, §6) | Task 13 |
| Ch.1 link-then-load integration test (§1, §6) | Task 14 |
| `scripts/phase3-prep.sh` (§6) | Task 15 |
| Phase 3 acceptance + log entry (§6) | Task 16 |

**Placeholder scan:** no "TBD" / "TODO" / "fill in" — every step has complete code, exact commands, expected output. The only intentionally-templated bits are the `<N>` placeholders in Task 16's Phase 3 complete log entry (the implementer fills with actual counts at acceptance time) and Task 4's bracket-suggested decisions-log entries (human task; user fills in).

**Type consistency:**
- `match_target_id` (TEXT, nullable, no FK) — consistent throughout.
- `person_match_score(a, b) -> dict[str, Any]` returning `{score, features}` — consistent.
- `link_run(conn, pipeline_run_id) -> dict[str, int]` returning `{candidates_processed, auto_merges, queued, skipped}` — consistent.
- `LINKER_AUTO_MERGE_THRESHOLD = 0.75`, `LINKER_QUEUE_THRESHOLD = 0.40` — consistent.
- `audit_log.actor = 'link@v1'` — consistent.
- Five feature dimensions (`variant_overlap`, `state_agreement`, `clan_agreement`, `social_category_agreement`, `temporal_proximity`) — consistent across spec §4 + Task 6 implementation + tests.
- `candidate_person_variants` table — introduced in Task 7 if not present; consistent in Tasks 7-10.

No issues to fix inline. Plan is complete.
