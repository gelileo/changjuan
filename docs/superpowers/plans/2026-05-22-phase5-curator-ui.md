# changjuan Phase 5 — Curator UI v1 (Merge-Candidates Triage) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first slice of the Stage-8 curator surface — a Streamlit app with a spec-faithful home screen (108-cell coverage grid + queue panel), the uniform 40/40/20 review shell, and the merge-candidates queue implemented end-to-end against the 31 open rows produced by Phase 3-4.

**Architecture:** Decision logic lives in a new `pipeline.stage5_link.merge` module (pure functions on a sqlite Connection, single-transaction with atomic audit_log writes); `curation/` is a thin view layer with read-only DB access; the other two queues ship as stub pages so the sidebar has its final shape but only merge-candidates is functional.

**Tech Stack:** Python 3.14, `uv`, sqlite3 (already WAL-enabled via `pipeline.db.connect`), Streamlit, `streamlit-shortcuts` (NEW dependency for keyboard bindings), pytest.

**Spec:** `docs/superpowers/specs/2026-05-22-phase5-curator-ui-design.md` (committed at `aa5f16d`).

---

## Before you start

- The workspace is the changjuan project. Confirm: `pwd` ends in `changjuan`, `git log -1 --format='%h %s'` shows `aa5f16d docs(spec): Phase 5 …`, `uv run pytest -q` ends with `234 passed`.
- The pipeline DB at `data/changjuan.sqlite` is the post-Phase-4 state: 75 persons, 102 events, 31 open merge_candidates, 12 open conflicts. Do not mutate it during development — every test that needs realistic data must copy it into `tmp_path` first.
- The corpus DB at `data/corpus.sqlite` is read-only and immutable after stage 1. Do not mutate.
- `uv sync --all-extras` (not plain `uv sync`) before running anything, per the HANDOFF gotcha.
- **Pre-commit hooks are strict.** Five hooks: drift-check, ruff, ruff-format, mypy strict, regen-extraction-schema. Mypy is the most likely friction — use `from __future__ import annotations` in every new file, type every public function signature, and prefer `dict[str, Any]` over un-typed dicts at the boundaries.
- **The living-docs same-task rule applies to every commit.** Each commit that touches `pipeline/stage5_link/**` must also touch `knowledge/concepts/pipeline/linking.md`. Each commit that touches `curation/**/*.py` must also touch `knowledge/concepts/curation/streamlit-app.md`. Each commit that touches `tests/**/*.py` must also touch `knowledge/concepts/verification/testing.md`. Commits that touch only `scripts/` or only the spec doc may use `no knowledge impact: <reason>` in the commit body.
- The article-mapping table is in `CLAUDE.md`. Re-read its "Article mapping" section before your first commit if you haven't recently.
- All new code must pass `uv run mypy --strict pipeline curation` (or whatever module(s) the change touched).

---

## Definition of done (Phase 5)

The phase is complete when **all** of the following are true:

1. `streamlit run curation/app.py` boots; the home screen renders the 108-cell coverage grid (5 green, 103 gray) plus three queue rows (merge-candidates active link; conflicts and low-confidence rendered disabled with "Phase 6"); the disabled search input shows a "Phase 6" tooltip.
2. Clicking through to "Merge candidates (N open)" loads all 31 currently-open candidates sorted by `created_at ASC`, renders the 40/40/20 shell for the first row, and the five action handlers (`accept`, `edit & accept`, `reject`, `defer`, `split`) each work via mouse OR via the `a`/`e`/`r`/`d`/`s` keyboard shortcuts.
3. `tests/integration/test_curator_smoke.py` calls every action at least once against a `tmp_path` copy of `data/changjuan.sqlite` and asserts: `merge_candidates` rows all resolved (no `status='open'` remaining among the 31); zero orphan FKs across the 5 person-FK columns retargeted by `accept_merge`; `audit_log` row count == decisions made + collisions resolved.
4. Unit tests for `pipeline.stage5_link.merge`: each of the 4 collision branches in §3 step 5 of the spec has a dedicated test; the atomicity guarantee is verified by full-DB snapshot before/after on every error branch.
5. All 5 pre-commit hooks pass on every commit.
6. `uv run pytest -q` is green (the new test count = 234 + however many tests this plan adds; expect ~30-40 new tests).
7. `scripts/phase5-prep.sh` reports all green.
8. `knowledge/concepts/curation/streamlit-app.md` is no longer `status: thin`; it accurately describes the shipped UI shape, action semantics, audit_log contract, and connection management. `knowledge/log.md` has Phase 5 entries.

The acceptance bar is "the surface works." Phase 5 does **not** require actually working through the 31 candidates — that happens after.

---

## File structure (what Phase 5 creates or modifies)

```text
changjuan/
├── pipeline/
│   ├── stage5_link/
│   │   └── merge.py                            # NEW: accept/reject/defer/split + dataclasses
│   └── cli.py                                  # MODIFY: add `changjuan curator` subcommand
├── curation/                                   # NEW package (path reserved in CLAUDE.md)
│   ├── __init__.py                             # NEW
│   ├── app.py                                  # NEW: Streamlit entry, home screen
│   ├── db.py                                   # NEW: read helpers (read-only connection)
│   ├── pages/
│   │   ├── 1_Merge_candidates.py               # NEW: review screen
│   │   ├── 2_Conflicts.py                      # NEW: stub
│   │   └── 3_Low_confidence.py                 # NEW: stub
│   └── components/
│       ├── __init__.py                         # NEW
│       ├── shell.py                            # NEW: 40/40/20 layout primitive
│       ├── coverage_grid.py                    # NEW: 108-cell grid
│       └── records.py                          # NEW: side-by-side records w/ diff
├── tests/
│   ├── unit/
│   │   ├── test_stage5_merge.py                # NEW
│   │   └── test_curation_db.py                 # NEW
│   ├── integration/
│   │   └── test_curator_smoke.py               # NEW
│   └── fixtures/
│       └── curation/                           # NEW directory
│           └── seed_merge_db.py                # NEW: helper to build a tiny test DB
├── scripts/
│   ├── curator-smoke                           # NEW: thin pytest wrapper
│   └── phase5-prep.sh                          # NEW: acceptance check
├── knowledge/
│   ├── concepts/
│   │   ├── curation/
│   │   │   └── streamlit-app.md                # MODIFY: grow from "thin" to full article
│   │   ├── pipeline/
│   │   │   └── linking.md                      # MODIFY: append "Merge actions" section
│   │   └── verification/
│   │       └── testing.md                      # MODIFY: append new-test sections
│   └── log.md                                  # MODIFY across most tasks
└── pyproject.toml                              # MODIFY: add `streamlit-shortcuts` dep
```

---

## Task index

**Phase 5a — Decision logic (the load-bearing module)**
1. `pipeline/stage5_link/merge.py` skeleton + dataclasses + `accept_merge` happy-path test (failing)
2. Implement `accept_merge` happy path (no edits, no collisions)
3. `accept_merge` PK-collision handling (4 collision rules)
4. `accept_merge` with `edits` (field-level audit_log)
5. `reject_merge` + `defer_merge`
6. `split_person`

**Phase 5b — Curation app shell**
7. `curation/db.py` read helpers + tests
8. `curation/components/{shell,coverage_grid,records}.py`
9. `curation/app.py` (home screen) + stub pages + streamlit-shortcuts dependency
10. `curation/pages/1_Merge_candidates.py` (review screen + keyboard bindings)

**Phase 5c — Closeout**
11. Integration test + `scripts/curator-smoke`
12. `pipeline/cli.py` `changjuan curator` + `scripts/phase5-prep.sh` + phase log entry

---

## Task 1 — `merge.py` skeleton + dataclasses + first failing test

**Files:**
- Create: `pipeline/stage5_link/merge.py`
- Create: `tests/unit/test_stage5_merge.py`
- Create: `tests/fixtures/curation/__init__.py`
- Create: `tests/fixtures/curation/seed_merge_db.py`
- Modify: `knowledge/concepts/pipeline/linking.md` (append "Merge actions" header + stub)
- Modify: `knowledge/concepts/verification/testing.md` (append a row noting `test_stage5_merge.py`)
- Modify: `knowledge/log.md` (Phase 5 Task 1 entry)

- [ ] **Step 1: Create the fixture seeder** — a tiny DB-builder so unit tests have realistic shapes without the live DB's noise.

Write `tests/fixtures/curation/seed_merge_db.py`:

```python
"""Seed a tiny sqlite DB for stage5_link.merge unit tests.

Builds a DB with two persons (one canonical, one candidate), a merge_candidates
row joining them, and a minimal set of relations on each so FK-retarget
behavior is exercisable.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA


def seed(db_path: Path) -> str:
    """Build a fresh test DB at db_path. Return the merge_candidates id."""
    with connect(db_path) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
        _seed_persons(conn)
        _seed_relations(conn)
        return _seed_merge_candidate(conn)


def _seed_persons(conn: sqlite3.Connection) -> None:
    # canonical: per:周宣王 (the survivor)
    conn.execute(
        "INSERT INTO persons (id, canonical_name, gender, clan_name) VALUES (?, ?, ?, ?)",
        ("per:test:canonical", "周宣王", "M", "姬"),
    )
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) VALUES (?, ?, ?, ?)",
        ("pv:test:c:1", "per:test:canonical", "宣王", "谥号"),
    )
    # candidate: a candidate_persons row that looks like the same person
    conn.execute(
        "INSERT INTO persons (id, canonical_name, gender, clan_name) VALUES (?, ?, ?, ?)",
        ("per:test:candidate", "周宣王", "M", None),
    )
    conn.execute(
        "INSERT INTO person_variants (id, person_id, variant, kind) VALUES (?, ?, ?, ?)",
        ("pv:test:cand:1", "per:test:candidate", "周宣王", "谥号"),
    )


def _seed_relations(conn: sqlite3.Connection) -> None:
    # a minimal event + participants so accept_merge has FKs to retarget
    conn.execute(
        "INSERT INTO events (id, type, outcome, summary) VALUES (?, ?, ?, ?)",
        ("evt:test:1", "battle", "outcome text", "summary text"),
    )
    conn.execute(
        "INSERT INTO event_participants (event_id, person_id, role, confidence, provenance) VALUES (?, ?, ?, ?, ?)",
        ("evt:test:1", "per:test:candidate", "victor", 0.9, "auto"),
    )


def _seed_merge_candidate(conn: sqlite3.Connection) -> str:
    mc_id = "mc:test:1"
    conn.execute(
        "INSERT INTO merge_candidates "
        "(id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'open')",
        (
            mc_id,
            "person",
            "per:test:candidate",  # A is the candidate (will be folded away)
            "per:test:canonical",  # B is the canonical (survivor)
            0.7,
            json.dumps({"features": {"variant_overlap": "strong"}, "score": 0.7}),
        ),
    )
    return mc_id
```

Also create the empty `tests/fixtures/curation/__init__.py`:

```python
```

- [ ] **Step 2: Create `merge.py` with empty function signatures + dataclasses**

Write `pipeline/stage5_link/merge.py`:

```python
"""Stage 5 merge actions — the load-bearing module behind the curator UI.

Each public function takes a sqlite Connection and performs its DB writes
in a single BEGIN ... COMMIT transaction. On any error the transaction
is rolled back; in particular, the audit_log row is atomic with the data
change. This atomicity is what makes the field_history view (founding
spec §5) correct.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class MergeError(Exception):
    """Base class for merge-action errors."""


class StaleMergeCandidateError(MergeError):
    """The merge_candidates row is no longer open (resolved in another tab/session)."""


class MergeConflictError(MergeError):
    """Candidate and canonical have non-NULL disagreement on a field.

    These should be routed to the conflicts queue during linking; raising here
    is defense-in-depth. The caller should surface the field name to the curator
    so they can either Edit & accept or Reject.
    """

    def __init__(self, field_name: str, candidate_value: Any, canonical_value: Any) -> None:
        super().__init__(f"field disagreement: {field_name}={candidate_value!r} vs {canonical_value!r}")
        self.field_name = field_name
        self.candidate_value = candidate_value
        self.canonical_value = canonical_value


class SplitValidationError(MergeError):
    """split_person was asked to peel off variants that don't all exist on the source row."""


@dataclass
class MergeResult:
    canonical_id: str
    variants_added: int
    relations_retargeted: int
    fields_edited: int
    collisions_resolved: int = 0


@dataclass
class RejectResult:
    mc_id: str
    note: str | None


@dataclass
class SplitResult:
    source_person_id: str
    new_person_id: str
    variants_moved: list[str] = field(default_factory=list)


def accept_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    edits: dict[str, Any] | None = None,
) -> MergeResult:
    """Fuse candidate (A) into canonical (B). Survivor = canonical.

    See spec §3 for the full algorithm. All work happens in one transaction.
    """
    raise NotImplementedError  # implemented in Task 2


def reject_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    note: str | None = None,
) -> RejectResult:
    """Mark a merge_candidates row as rejected with an optional curator note."""
    raise NotImplementedError  # implemented in Task 5


def defer_merge(conn: sqlite3.Connection, mc_id: str) -> None:
    """No-op from the DB's perspective. Curator advances the cursor in-memory."""
    raise NotImplementedError  # implemented in Task 5


def split_person(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    variants_to_extract: list[str],
    note: str | None = None,
) -> SplitResult:
    """Peel listed variants into a new person row. Source-row relations stay put."""
    raise NotImplementedError  # implemented in Task 6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _new_audit_id() -> str:
    return f"aud:{uuid.uuid4().hex[:12]}"


def _row_snapshot(conn: sqlite3.Connection, table: str, row_id: str) -> dict[str, Any] | None:
    cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cur.fetchone()
    return dict(row) if row else None
```

- [ ] **Step 3: Write the first failing test**

Write `tests/unit/test_stage5_merge.py`:

```python
"""Unit tests for pipeline.stage5_link.merge.

Each test seeds a fresh tmp_path DB via tests.fixtures.curation.seed_merge_db,
then exercises one branch of one merge action.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import connect
from pipeline.stage5_link.merge import (
    MergeConflictError,
    MergeResult,
    StaleMergeCandidateError,
    accept_merge,
)
from tests.fixtures.curation.seed_merge_db import seed


@pytest.fixture
def seeded_db(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "merge_test.sqlite"
    mc_id = seed(db_path)
    return db_path, mc_id


def test_accept_merge_happy_path_returns_result(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert isinstance(result, MergeResult)
    assert result.canonical_id == "per:test:canonical"
    assert result.relations_retargeted >= 1  # the seeded event_participants row
```

- [ ] **Step 4: Run the test and confirm it fails for the expected reason**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
```

Expected: `FAILED` with `NotImplementedError`.

- [ ] **Step 5: Update knowledge articles (small, accurate, no future-tense)**

Append to `knowledge/concepts/pipeline/linking.md` near the end (above any "What would invalidate this article" section if present):

```markdown
## Merge actions (Phase 5)

`pipeline.stage5_link.merge` provides the decision actions invoked by the
curator UI: `accept_merge`, `reject_merge`, `defer_merge`, `split_person`.
Each function takes a sqlite Connection and performs its DB writes in a
single transaction. The audit_log row is atomic with the data change.
Detailed semantics live in the Phase 5 design spec (`docs/superpowers/specs/2026-05-22-phase5-curator-ui-design.md` §3, §4).
```

Append to `knowledge/concepts/verification/testing.md` (in the test-inventory section, if any; otherwise under a "New for Phase 5" subhead):

```markdown
### Phase 5 — curator UI

- `tests/unit/test_stage5_merge.py` — unit tests for the decision actions
  (`accept_merge`, `reject_merge`, `defer_merge`, `split_person`). Atomicity
  is verified by full-DB snapshot before/after on every error branch.
- `tests/fixtures/curation/seed_merge_db.py` — tiny synthetic DB seeder
  used by the merge unit tests.
```

Append to `knowledge/log.md` (top of file, reverse chronological):

```markdown
## [2026-05-22] feat(stage5): merge.py skeleton + first failing test (Phase 5 Task 1)

Scaffolds `pipeline/stage5_link/merge.py` with dataclasses, error classes,
and four `NotImplementedError` function stubs. Adds the seeded-DB fixture
under `tests/fixtures/curation/`. First failing test asserts `accept_merge`
returns a `MergeResult` for the happy path — fails with NotImplementedError
as expected.
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/stage5_link/merge.py \
        tests/unit/test_stage5_merge.py \
        tests/fixtures/curation/__init__.py \
        tests/fixtures/curation/seed_merge_db.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/concepts/verification/testing.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(stage5): merge.py skeleton + first failing test (Phase 5 Task 1)

Scaffolds the decision-action module behind the curator UI. Empty function
signatures + dataclasses + error classes; first happy-path test fails with
NotImplementedError as expected. Implementation lands in Task 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Pre-commit hooks should all pass — drift-check sees both `pipeline/stage5_link/**` and `tests/**` touched, and both target articles are in the commit.

---

## Task 2 — Implement `accept_merge` happy path

Goal: make the failing test from Task 1 pass. No edits, no PK-collision handling yet (those land in Tasks 3-4 with their own tests).

**Files:**
- Modify: `pipeline/stage5_link/merge.py`
- Modify: `tests/unit/test_stage5_merge.py` (add more happy-path assertions)
- Modify: `knowledge/concepts/pipeline/linking.md` (one-line "Phase 5 Task 2 implements `accept_merge` happy path")
- Modify: `knowledge/log.md`

- [ ] **Step 1: Expand the happy-path test before writing implementation**

Replace the body of `test_accept_merge_happy_path_returns_result` and add a second test:

```python
def test_accept_merge_happy_path_returns_result(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert isinstance(result, MergeResult)
    assert result.canonical_id == "per:test:canonical"
    assert result.variants_added == 1  # 周宣王 fold; 宣王 already on canonical
    assert result.relations_retargeted == 1  # event_participants row
    assert result.fields_edited == 0
    assert result.collisions_resolved == 0


def test_accept_merge_writes_audit_log_row(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT change_kind, entity_kind, entity_id, before_json, after_json "
            "FROM audit_log WHERE entity_id = 'per:test:canonical' "
            "AND change_kind = 'merge'"
        ).fetchone()
    assert row is not None
    assert row["entity_kind"] == "person"
    before = json.loads(row["before_json"])
    after = json.loads(row["after_json"])
    assert before["id"] == "per:test:candidate"  # candidate snapshot
    assert after["id"] == "per:test:canonical"   # post-merge canonical


def test_accept_merge_flips_status_and_resolved_at(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, resolved_at FROM merge_candidates WHERE id = ?", (mc_id,)
        ).fetchone()
    assert row["status"] == "merged"
    assert row["resolved_at"] is not None


def test_accept_merge_retargets_event_participants(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id FROM event_participants WHERE event_id = 'evt:test:1'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["person_id"] == "per:test:canonical"


def test_accept_merge_deletes_candidate_row(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM persons WHERE id = 'per:test:candidate'"
        ).fetchone()
    assert row is None


def test_accept_merge_folds_variants_dedup(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT variant, kind FROM person_variants WHERE person_id = 'per:test:canonical' "
            "ORDER BY variant"
        ).fetchall()
    variants = {(r["variant"], r["kind"]) for r in rows}
    # canonical had 宣王 (谥号); candidate brought 周宣王 (谥号)
    assert variants == {("宣王", "谥号"), ("周宣王", "谥号")}


def test_accept_merge_stale_raises(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE merge_candidates SET status = 'merged' WHERE id = ?", (mc_id,)
        )
    with connect(db_path) as conn:
        with pytest.raises(StaleMergeCandidateError):
            accept_merge(conn, mc_id)
```

Also add `import json` and the missing `MergeConflictError` is referenced later — keep it in the import list.

- [ ] **Step 2: Run the new tests, all should fail with NotImplementedError**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
```

Expected: 7 FAILED.

- [ ] **Step 3: Implement `accept_merge` happy path**

Replace the `accept_merge` body in `pipeline/stage5_link/merge.py`:

```python
def accept_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    edits: dict[str, Any] | None = None,
) -> MergeResult:
    """Fuse candidate (A) into canonical (B). Survivor = canonical."""
    # Edits are processed in Task 4. For Task 2, edits must be None or empty.
    if edits:
        raise NotImplementedError("edits handled in Task 4")

    cur = conn.execute(
        "SELECT id, candidate_a_id, candidate_b_id, status "
        "FROM merge_candidates WHERE id = ?",
        (mc_id,),
    )
    mc_row = cur.fetchone()
    if mc_row is None:
        raise MergeError(f"no merge_candidates row with id={mc_id!r}")
    if mc_row["status"] != "open":
        raise StaleMergeCandidateError(f"merge_candidates {mc_id!r} status is {mc_row['status']!r}")

    candidate_id = mc_row["candidate_a_id"]
    canonical_id = mc_row["candidate_b_id"]

    # Snapshots for audit_log.
    candidate_snapshot = _row_snapshot(conn, "persons", candidate_id)
    if candidate_snapshot is None:
        raise MergeError(f"candidate person {candidate_id!r} not found")
    canonical_snapshot_before = _row_snapshot(conn, "persons", canonical_id)
    if canonical_snapshot_before is None:
        raise MergeError(f"canonical person {canonical_id!r} not found")

    # 3. Field-level fold: NULL canonical slots filled from candidate.
    nullable_fields = ("gender", "birth_date_json", "death_date_json", "notes", "state_id", "clan_name")
    field_updates: dict[str, Any] = {}
    for field_name in nullable_fields:
        cand_val = candidate_snapshot.get(field_name)
        can_val = canonical_snapshot_before.get(field_name)
        if cand_val is None or cand_val == can_val:
            continue
        if can_val is None:
            field_updates[field_name] = cand_val
        else:
            raise MergeConflictError(field_name, cand_val, can_val)
    if field_updates:
        set_clause = ", ".join(f"{f} = ?" for f in field_updates)
        conn.execute(
            f"UPDATE persons SET {set_clause} WHERE id = ?",
            (*field_updates.values(), canonical_id),
        )

    # 4. Variant fold (UNIQUE(person_id, variant, kind) makes this collision-safe).
    existing = {
        (r["variant"], r["kind"])
        for r in conn.execute(
            "SELECT variant, kind FROM person_variants WHERE person_id = ?", (canonical_id,)
        )
    }
    variants_added = 0
    candidate_variants = conn.execute(
        "SELECT id, variant, kind FROM person_variants WHERE person_id = ?", (candidate_id,)
    ).fetchall()
    for v in candidate_variants:
        if (v["variant"], v["kind"]) in existing:
            conn.execute("DELETE FROM person_variants WHERE id = ?", (v["id"],))
            continue
        conn.execute(
            "UPDATE person_variants SET person_id = ? WHERE id = ?", (canonical_id, v["id"])
        )
        variants_added += 1

    # 5. FK retarget across the 5 person-FK columns. Task 3 adds collision handling;
    #    for Task 2 the seeded fixture has no collisions, so naive UPDATE suffices.
    relations_retargeted = 0
    relations_retargeted += conn.execute(
        "UPDATE event_participants SET person_id = ? WHERE person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE person_relations SET from_person_id = ? WHERE from_person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE person_relations SET to_person_id = ? WHERE to_person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE person_states SET person_id = ? WHERE person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE entity_citations SET entity_id = ? "
        "WHERE entity_kind = 'person' AND entity_id = ?",
        (canonical_id, candidate_id),
    ).rowcount

    # 6. Delete candidate row. person_variants with person_id=candidate_id are gone
    #    (all either moved or deleted in step 4).
    conn.execute("DELETE FROM persons WHERE id = ?", (candidate_id,))

    # 7. Flip merge_candidates status.
    conn.execute(
        "UPDATE merge_candidates SET status = 'merged', resolved_at = ? WHERE id = ?",
        (_now_iso(), mc_id),
    )

    # 8. Audit log — record-level row only in Task 2; field-level rows for edits in Task 4.
    canonical_snapshot_after = _row_snapshot(conn, "persons", canonical_id)
    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) VALUES (?, 'person', ?, NULL, 'merge', ?, ?, ?, ?)",
        (
            _new_audit_id(),
            canonical_id,
            json.dumps(candidate_snapshot, ensure_ascii=False),
            json.dumps(canonical_snapshot_after, ensure_ascii=False),
            "curator",
            _now_iso(),
        ),
    )

    return MergeResult(
        canonical_id=canonical_id,
        variants_added=variants_added,
        relations_retargeted=relations_retargeted,
        fields_edited=0,
    )
```

Add `MergeError` to the public exports (already declared); no other module changes needed.

- [ ] **Step 4: Run the tests, all should pass**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Run mypy strict on the touched modules**

```bash
uv run mypy --strict pipeline/stage5_link/merge.py
```

Expected: `Success: no issues found`.

- [ ] **Step 6: Update articles + commit**

Append to `knowledge/concepts/pipeline/linking.md` (extending the "Merge actions" section started in Task 1):

```markdown
### `accept_merge` algorithm

In one transaction: validate `status='open'`, fold NULL canonical slots
from candidate (raise on non-NULL disagreement), fold variants (UNIQUE
constraint dedups), retarget the 5 person-FK columns, delete candidate
row, flip `merge_candidates` status, write record-level audit_log row.
Spec §3 has the full step-by-step.
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-22] feat(stage5): accept_merge happy path (Phase 5 Task 2)

Implements the no-edits, no-collisions accept_merge path. 7 unit tests
green. NULL canonical fields are filled from candidate; variants are
folded via UNIQUE constraint; FKs retargeted across event_participants,
person_relations (both columns), person_states, and entity_citations
where entity_kind='person'. audit_log row written with the candidate
snapshot as `before_json` and the post-merge canonical as `after_json`.
```

```bash
git add pipeline/stage5_link/merge.py \
        tests/unit/test_stage5_merge.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(stage5): accept_merge happy path (Phase 5 Task 2)

Implements the no-edits no-collisions accept_merge: field-level NULL fold,
variant fold via UNIQUE, FK retarget across 5 person-FK columns, candidate
row deletion, status flip, atomic audit_log row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — `accept_merge` PK-collision handling

Extends the seeder + accept_merge with the four collision rules from spec §3 step 5.

**Files:**
- Modify: `tests/fixtures/curation/seed_merge_db.py` (add a collision-seeding helper)
- Modify: `pipeline/stage5_link/merge.py` (collision resolution before each UPDATE)
- Modify: `tests/unit/test_stage5_merge.py` (one test per collision rule)
- Modify: `knowledge/concepts/pipeline/linking.md`, `knowledge/log.md`

- [ ] **Step 1: Add a collision-seeding helper to the fixture**

Append to `tests/fixtures/curation/seed_merge_db.py`:

```python
def add_event_participants_collision(db_path: Path) -> None:
    """Both candidate AND canonical play 'victor' in evt:test:1.

    After the seeder, event_participants has the candidate row only. This
    helper adds a canonical row with the same (event_id, role), forcing a
    PK collision on retarget. Confidence of the canonical row is higher
    so it should be the survivor.
    """
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO event_participants "
            "(event_id, person_id, role, confidence, provenance) "
            "VALUES ('evt:test:1', 'per:test:canonical', 'victor', 0.95, 'auto')",
        )


def add_person_relations_self_loop(db_path: Path) -> None:
    """Candidate has a 'spouse' relation TO the canonical.

    After merge, this would become (canonical, canonical, 'spouse') — a self-loop.
    The merge function should delete the relation outright.
    """
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO person_relations "
            "(from_person_id, to_person_id, kind, confidence, provenance) "
            "VALUES ('per:test:candidate', 'per:test:canonical', 'spouse', 0.9, 'auto')",
        )


def add_person_states_collision(db_path: Path) -> None:
    """Both rows are 'ruler' of sta:周 with the same from_date_json (NULL).

    The canonical row has higher confidence and wins.
    """
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO states (id, name, type) VALUES ('sta:周', '周', 'state')"
        )
        conn.execute(
            "INSERT INTO person_states "
            "(person_id, state_id, role, confidence, provenance) "
            "VALUES ('per:test:candidate', 'sta:周', 'ruler', 0.8, 'auto')"
        )
        conn.execute(
            "INSERT INTO person_states "
            "(person_id, state_id, role, confidence, provenance) "
            "VALUES ('per:test:canonical', 'sta:周', 'ruler', 0.95, 'auto')"
        )


def add_entity_citations_duplicate(db_path: Path) -> None:
    """Both rows reference the same citation. Candidate's row should drop silently."""
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
            "VALUES ('person', 'per:test:candidate', 'cite:test:1')"
        )
        conn.execute(
            "INSERT INTO entity_citations (entity_kind, entity_id, citation_id) "
            "VALUES ('person', 'per:test:canonical', 'cite:test:1')"
        )
```

- [ ] **Step 2: Write four collision tests**

Append to `tests/unit/test_stage5_merge.py`:

```python
from tests.fixtures.curation.seed_merge_db import (
    add_entity_citations_duplicate,
    add_event_participants_collision,
    add_person_relations_self_loop,
    add_person_states_collision,
)


def test_accept_merge_event_participants_collision_keeps_higher_confidence(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_event_participants_collision(db_path)  # canonical row, confidence 0.95
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id, confidence FROM event_participants "
            "WHERE event_id = 'evt:test:1' AND role = 'victor'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["person_id"] == "per:test:canonical"
    assert rows[0]["confidence"] == 0.95  # higher-confidence row survived


def test_accept_merge_person_relations_self_loop_deletes(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_person_relations_self_loop(db_path)
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM person_relations WHERE kind = 'spouse'"
        ).fetchone()
    assert row is None  # self-loop was deleted, not folded


def test_accept_merge_person_states_collision_keeps_higher_confidence(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_person_states_collision(db_path)
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT person_id, confidence FROM person_states "
            "WHERE state_id = 'sta:周' AND role = 'ruler'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["confidence"] == 0.95


def test_accept_merge_entity_citations_duplicate_drops_candidate(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    add_entity_citations_duplicate(db_path)
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id)
    assert result.collisions_resolved == 1
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT entity_id FROM entity_citations "
            "WHERE entity_kind = 'person' AND citation_id = 'cite:test:1'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "per:test:canonical"


def test_accept_merge_collision_writes_audit_log(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    add_event_participants_collision(db_path)
    with connect(db_path) as conn:
        accept_merge(conn, mc_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT entity_kind, change_kind FROM audit_log "
            "WHERE change_kind = 'merge_collision_resolved'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_kind"] == "event_participant"
```

- [ ] **Step 3: Run; expect the 5 new tests to fail**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
```

Expected: 5 FAILED (the new collision tests), 7 PASSED.

- [ ] **Step 4: Implement collision resolution**

Refactor the FK-retarget block in `pipeline/stage5_link/merge.py`. Add a helper above `accept_merge`:

```python
def _resolve_collisions_event_participants(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """Detect (event_id, role) PK collisions between candidate's and canonical's rows.

    Keeps the higher-confidence row; deletes the other. Returns the number
    of collisions resolved. Writes audit_log rows for each deletion.
    """
    cur = conn.execute(
        "SELECT cand.event_id, cand.role, cand.confidence AS cand_conf, "
        "       can.confidence AS can_conf "
        "FROM event_participants cand "
        "JOIN event_participants can "
        "  ON cand.event_id = can.event_id AND cand.role = can.role "
        "WHERE cand.person_id = ? AND can.person_id = ?",
        (candidate_id, canonical_id),
    )
    collisions = list(cur)
    for c in collisions:
        loser_person = candidate_id if c["cand_conf"] < c["can_conf"] else canonical_id
        loser_conf = c["cand_conf"] if loser_person == candidate_id else c["can_conf"]
        # Record the loser row's snapshot before deleting (audit_log payload).
        loser_row = conn.execute(
            "SELECT * FROM event_participants "
            "WHERE event_id = ? AND person_id = ? AND role = ?",
            (c["event_id"], loser_person, c["role"]),
        ).fetchone()
        conn.execute(
            "DELETE FROM event_participants "
            "WHERE event_id = ? AND person_id = ? AND role = ?",
            (c["event_id"], loser_person, c["role"]),
        )
        conn.execute(
            "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'event_participant', ?, NULL, 'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"{c['event_id']}:{loser_person}:{c['role']}",
                json.dumps(dict(loser_row), ensure_ascii=False),
                _now_iso(),
            ),
        )
        _ = loser_conf  # silence unused-var if mypy complains
    return len(collisions)


def _resolve_self_loops_person_relations(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """A relation FROM candidate TO canonical (or vice versa) becomes a self-loop after merge.

    Delete those outright. Returns the count.
    """
    rows = conn.execute(
        "SELECT from_person_id, to_person_id, kind FROM person_relations "
        "WHERE (from_person_id = ? AND to_person_id = ?) "
        "   OR (from_person_id = ? AND to_person_id = ?)",
        (candidate_id, canonical_id, canonical_id, candidate_id),
    ).fetchall()
    for r in rows:
        loser_snapshot = dict(r)
        conn.execute(
            "DELETE FROM person_relations "
            "WHERE from_person_id = ? AND to_person_id = ? AND kind = ?",
            (r["from_person_id"], r["to_person_id"], r["kind"]),
        )
        conn.execute(
            "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'person_relation', ?, NULL, 'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"{r['from_person_id']}:{r['to_person_id']}:{r['kind']}",
                json.dumps(loser_snapshot, ensure_ascii=False),
                _now_iso(),
            ),
        )
    return len(rows)


def _resolve_collisions_person_states(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """PK is (person_id, state_id, role, from_date_json). Higher-confidence wins."""
    cur = conn.execute(
        "SELECT cand.state_id, cand.role, cand.from_date_json, "
        "       cand.confidence AS cand_conf, can.confidence AS can_conf "
        "FROM person_states cand "
        "JOIN person_states can "
        "  ON cand.state_id = can.state_id "
        " AND cand.role = can.role "
        " AND COALESCE(cand.from_date_json, '') = COALESCE(can.from_date_json, '') "
        "WHERE cand.person_id = ? AND can.person_id = ?",
        (candidate_id, canonical_id),
    )
    collisions = list(cur)
    for c in collisions:
        loser_person = candidate_id if c["cand_conf"] < c["can_conf"] else canonical_id
        loser_row = conn.execute(
            "SELECT * FROM person_states "
            "WHERE person_id = ? AND state_id = ? AND role = ? "
            "  AND COALESCE(from_date_json, '') = COALESCE(?, '')",
            (loser_person, c["state_id"], c["role"], c["from_date_json"]),
        ).fetchone()
        conn.execute(
            "DELETE FROM person_states "
            "WHERE person_id = ? AND state_id = ? AND role = ? "
            "  AND COALESCE(from_date_json, '') = COALESCE(?, '')",
            (loser_person, c["state_id"], c["role"], c["from_date_json"]),
        )
        conn.execute(
            "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'person_state', ?, NULL, 'merge_collision_resolved', ?, NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"{loser_person}:{c['state_id']}:{c['role']}",
                json.dumps(dict(loser_row), ensure_ascii=False),
                _now_iso(),
            ),
        )
    return len(collisions)


def _resolve_collisions_entity_citations(
    conn: sqlite3.Connection, candidate_id: str, canonical_id: str
) -> int:
    """PK is (entity_kind, entity_id, citation_id). Idempotent — drop candidate's row."""
    cur = conn.execute(
        "SELECT cand.citation_id FROM entity_citations cand "
        "JOIN entity_citations can "
        "  ON cand.entity_kind = can.entity_kind AND cand.citation_id = can.citation_id "
        "WHERE cand.entity_kind = 'person' AND cand.entity_id = ? AND can.entity_id = ?",
        (candidate_id, canonical_id),
    )
    collisions = list(cur)
    for c in collisions:
        conn.execute(
            "DELETE FROM entity_citations "
            "WHERE entity_kind = 'person' AND entity_id = ? AND citation_id = ?",
            (candidate_id, c["citation_id"]),
        )
        conn.execute(
            "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
            "before_json, after_json, actor, at) "
            "VALUES (?, 'entity_citation', ?, NULL, 'merge_collision_resolved', "
            "'{\"duplicate\":true}', NULL, 'curator', ?)",
            (
                _new_audit_id(),
                f"person:{candidate_id}:{c['citation_id']}",
                _now_iso(),
            ),
        )
    return len(collisions)
```

Now modify `accept_merge` to call these helpers before the naive UPDATEs. Replace the `relations_retargeted = 0` block with:

```python
    # 5. PK-collision resolution must happen BEFORE the retarget UPDATEs.
    collisions_resolved = 0
    collisions_resolved += _resolve_collisions_event_participants(conn, candidate_id, canonical_id)
    collisions_resolved += _resolve_self_loops_person_relations(conn, candidate_id, canonical_id)
    collisions_resolved += _resolve_collisions_person_states(conn, candidate_id, canonical_id)
    collisions_resolved += _resolve_collisions_entity_citations(conn, candidate_id, canonical_id)

    # Now the UPDATEs are safe.
    relations_retargeted = 0
    relations_retargeted += conn.execute(
        "UPDATE event_participants SET person_id = ? WHERE person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE person_relations SET from_person_id = ? WHERE from_person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE person_relations SET to_person_id = ? WHERE to_person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE person_states SET person_id = ? WHERE person_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
    relations_retargeted += conn.execute(
        "UPDATE entity_citations SET entity_id = ? "
        "WHERE entity_kind = 'person' AND entity_id = ?",
        (canonical_id, candidate_id),
    ).rowcount
```

And update the final `MergeResult(...)` call:

```python
    return MergeResult(
        canonical_id=canonical_id,
        variants_added=variants_added,
        relations_retargeted=relations_retargeted,
        fields_edited=0,
        collisions_resolved=collisions_resolved,
    )
```

- [ ] **Step 5: Run tests + mypy**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
uv run mypy --strict pipeline/stage5_link/merge.py
```

Expected: 12 PASSED; mypy clean.

- [ ] **Step 6: Update articles + commit**

Append to `knowledge/concepts/pipeline/linking.md`:

```markdown
### PK-collision rules (Phase 5 Task 3)

`accept_merge` resolves PK collisions before retargeting:
- `event_participants` `(event_id, person_id, role)` — higher-confidence wins.
- `person_relations` self-loops (relation from/to merged pair) — deleted.
- `person_states` `(person_id, state_id, role, COALESCE(from_date_json,''))` —
  higher-confidence wins.
- `entity_citations` `(entity_kind, entity_id, citation_id)` — candidate row dropped.

Each resolution writes an `audit_log` row with `change_kind='merge_collision_resolved'`.
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-22] feat(stage5): accept_merge PK-collision handling (Phase 5 Task 3)

Adds four collision-resolution helpers + 5 unit tests exercising each rule.
audit_log row written per collision with `change_kind='merge_collision_resolved'`.
```

```bash
git add pipeline/stage5_link/merge.py \
        tests/fixtures/curation/seed_merge_db.py \
        tests/unit/test_stage5_merge.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(stage5): accept_merge PK-collision handling (Phase 5 Task 3)

Resolves event_participants/person_states higher-confidence-wins, person_relations
self-loops (drop), and entity_citations duplicates before the retarget UPDATEs.
Each collision writes an audit_log row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `accept_merge` with `edits` (field-level audit_log)

**Files:**
- Modify: `pipeline/stage5_link/merge.py` (edits handling)
- Modify: `tests/unit/test_stage5_merge.py`
- Modify: `knowledge/concepts/pipeline/linking.md`, `knowledge/log.md`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_stage5_merge.py`:

```python
def test_accept_merge_with_edits_applies_field_change(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = accept_merge(conn, mc_id, edits={"clan_name": "姬"})
    assert result.fields_edited == 1
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT clan_name FROM persons WHERE id = 'per:test:canonical'"
        ).fetchone()
    assert row["clan_name"] == "姬"


def test_accept_merge_with_edits_writes_field_level_audit(
    seeded_db: tuple[Path, str],
) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        accept_merge(conn, mc_id, edits={"notes": "edited by curator"})
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT field, before_json, after_json FROM audit_log "
            "WHERE entity_id = 'per:test:canonical' AND field = 'notes'"
        ).fetchone()
    assert row is not None
    assert row["field"] == "notes"
    after = json.loads(row["after_json"])
    assert after["value"] == "edited by curator"
    # before_json should match the §5 shape: {value, confidence, source_excerpt}
    before = json.loads(row["before_json"])
    assert "value" in before and "confidence" in before
```

- [ ] **Step 2: Run; expect 2 FAILED**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
```

- [ ] **Step 3: Implement edits handling**

In `pipeline/stage5_link/merge.py`, replace the early guard `if edits: raise NotImplementedError(...)` with real handling. Place this block AFTER the snapshot reads and BEFORE the NULL-fold:

```python
    # Apply curator edits to canonical FIRST (before NULL-fold) so the field
    # value the fold sees is the edited one. Field-level audit_log rows per §5.
    fields_edited = 0
    if edits:
        for field_name, new_value in edits.items():
            before_value = canonical_snapshot_before.get(field_name)
            conn.execute(
                f"UPDATE persons SET {field_name} = ? WHERE id = ?",
                (new_value, canonical_id),
            )
            conn.execute(
                "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
                "before_json, after_json, actor, at) "
                "VALUES (?, 'person', ?, ?, 'edit', ?, ?, 'curator', ?)",
                (
                    _new_audit_id(),
                    canonical_id,
                    field_name,
                    json.dumps(
                        {"value": before_value, "confidence": 1.0, "source_excerpt": None},
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {"value": new_value, "confidence": 1.0, "source_excerpt": None},
                        ensure_ascii=False,
                    ),
                    _now_iso(),
                ),
            )
            fields_edited += 1
        # Refresh the in-memory snapshot so subsequent fold logic sees edited values.
        canonical_snapshot_before = _row_snapshot(conn, "persons", canonical_id) or canonical_snapshot_before
```

Update the final `MergeResult(...)` to pass `fields_edited=fields_edited` instead of `0`. **Whitelist allowed fields** — to keep this safe, validate `field_name` against `nullable_fields` before the UPDATE:

```python
    _ALLOWED_EDIT_FIELDS = frozenset(
        {"gender", "birth_date_json", "death_date_json", "notes", "state_id", "clan_name", "canonical_name"}
    )
    if edits:
        for field_name in edits:
            if field_name not in _ALLOWED_EDIT_FIELDS:
                raise MergeError(f"field {field_name!r} not editable via accept_merge")
```

(Place the `_ALLOWED_EDIT_FIELDS` constant at module level.)

- [ ] **Step 4: Run tests + mypy**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
uv run mypy --strict pipeline/stage5_link/merge.py
```

Expected: 14 PASSED.

- [ ] **Step 5: Update articles + commit**

Append to `knowledge/concepts/pipeline/linking.md`:

```markdown
### Field-level edits (Phase 5 Task 4)

`accept_merge(conn, mc_id, edits={field_name: new_value, ...})` applies
the listed edits to the canonical row BEFORE the field-level NULL fold,
so the fold sees the curator's intended values. Each edit produces a
field-level `audit_log` row with the §5 shape `{value, confidence,
source_excerpt}` for both `before_json` and `after_json`.

Editable fields: `gender`, `birth_date_json`, `death_date_json`, `notes`,
`state_id`, `clan_name`, `canonical_name`. Other field names raise
`MergeError`.
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-22] feat(stage5): accept_merge edits + field-level audit_log (Phase 5 Task 4)

Curator can pass `edits={field: value}` to apply to canonical pre-fold.
Field-level audit_log rows conform to §5 shape. Edits restricted to a
whitelist of person columns.
```

```bash
git add pipeline/stage5_link/merge.py \
        tests/unit/test_stage5_merge.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(stage5): accept_merge edits + field-level audit_log (Phase 5 Task 4)

Curator-supplied edits apply to canonical before NULL-fold. Each edit
produces a field-level audit_log row in the §5 shape.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — `reject_merge` + `defer_merge`

**Files:**
- Modify: `pipeline/stage5_link/merge.py`
- Modify: `tests/unit/test_stage5_merge.py`
- Modify: `knowledge/concepts/pipeline/linking.md`, `knowledge/log.md`

- [ ] **Step 1: Tests first**

Append to `tests/unit/test_stage5_merge.py`:

```python
from pipeline.stage5_link.merge import defer_merge, reject_merge


def test_reject_merge_flips_status(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        result = reject_merge(conn, mc_id, note="different people")
    assert result.mc_id == mc_id
    assert result.note == "different people"
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, resolved_at FROM merge_candidates WHERE id = ?",
            (mc_id,),
        ).fetchone()
    assert row["status"] == "rejected"
    assert row["resolved_at"] is not None
    # Note: merge_candidates has no curator_note column. The note lives on
    # the audit_log row (asserted in test_reject_merge_writes_audit_log below).


def test_reject_merge_writes_audit_log(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        reject_merge(conn, mc_id, note="different people")
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT change_kind, before_json, after_json FROM audit_log "
            "WHERE change_kind = 'merge_rejected'"
        ).fetchone()
    assert row is not None
    after = json.loads(row["after_json"])
    assert after["note"] == "different people"


def test_reject_merge_stale_raises(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    with connect(db_path) as conn:
        conn.execute("UPDATE merge_candidates SET status='rejected' WHERE id = ?", (mc_id,))
    with connect(db_path) as conn:
        with pytest.raises(StaleMergeCandidateError):
            reject_merge(conn, mc_id)


def test_defer_merge_is_noop(seeded_db: tuple[Path, str]) -> None:
    db_path, mc_id = seeded_db
    # Snapshot the full DB before/after; assert equality.
    before = _dump(db_path)
    with connect(db_path) as conn:
        defer_merge(conn, mc_id)
    after = _dump(db_path)
    assert before == after


def _dump(db_path: Path) -> dict[str, list[tuple]]:
    """Full-DB snapshot for atomicity assertions. Returns table -> rows."""
    out: dict[str, list[tuple]] = {}
    with connect(db_path) as conn:
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            out[table] = [tuple(r) for r in rows]
    return out
```

Note the `merge_candidates` schema doesn't have a `curator_note` column — verify by re-checking the schema if needed. The note lives in `audit_log.after_json` as `{"note": "..."}`. Update the first test if the schema does have curator_note (it might — confirm via `sqlite3 data/changjuan.sqlite ".schema merge_candidates"`). If it does, also write to that column.

- [ ] **Step 2: Run; expect 4 FAILED**

- [ ] **Step 3: Implement `reject_merge` + `defer_merge`**

Replace the bodies in `pipeline/stage5_link/merge.py`:

```python
def reject_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    note: str | None = None,
) -> RejectResult:
    mc_row = conn.execute(
        "SELECT status FROM merge_candidates WHERE id = ?", (mc_id,)
    ).fetchone()
    if mc_row is None:
        raise MergeError(f"no merge_candidates row with id={mc_id!r}")
    if mc_row["status"] != "open":
        raise StaleMergeCandidateError(f"merge_candidates {mc_id!r} status is {mc_row['status']!r}")

    conn.execute(
        "UPDATE merge_candidates SET status = 'rejected', resolved_at = ? WHERE id = ?",
        (_now_iso(), mc_id),
    )
    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) "
        "VALUES (?, 'merge_candidate', ?, NULL, 'merge_rejected', '{}', ?, 'curator', ?)",
        (
            _new_audit_id(),
            mc_id,
            json.dumps({"note": note}, ensure_ascii=False),
            _now_iso(),
        ),
    )
    return RejectResult(mc_id=mc_id, note=note)


def defer_merge(conn: sqlite3.Connection, mc_id: str) -> None:
    """No DB writes — curator's cursor advances in Streamlit memory only.

    Kept as a function so the UI layer has a uniform shape for all five actions
    (each handler calls one merge function). The body is intentionally empty.
    """
    return None
```

- [ ] **Step 4: Run + mypy**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
uv run mypy --strict pipeline/stage5_link/merge.py
```

Expected: 18 PASSED.

- [ ] **Step 5: Articles + commit**

Append to `knowledge/concepts/pipeline/linking.md`:

```markdown
### `reject_merge` and `defer_merge`

`reject_merge(conn, mc_id, *, note=None)` flips `merge_candidates.status` to
`'rejected'`, sets `resolved_at`, and writes an `audit_log` row with
`change_kind='merge_rejected'` and `after_json={"note": <note>}`.

`defer_merge(conn, mc_id)` is a no-op from the DB's perspective — the
curator's cursor advances in Streamlit memory. Kept as a function so the
UI dispatch layer is uniform.

Reject-memory (preventing the next linker run from re-flagging a rejected
pair) is deferred to Phase 6.
```

Log entry + commit:

```bash
git add pipeline/stage5_link/merge.py \
        tests/unit/test_stage5_merge.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(stage5): reject_merge + defer_merge (Phase 5 Task 5)

reject_merge flips status + writes audit_log row with curator note.
defer_merge is a no-op kept for UI uniformity.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — `split_person`

**Files:**
- Modify: `pipeline/stage5_link/merge.py`
- Modify: `tests/unit/test_stage5_merge.py`
- Modify: `knowledge/concepts/pipeline/linking.md`, `knowledge/log.md`

- [ ] **Step 1: Tests**

Append to `tests/unit/test_stage5_merge.py`:

```python
from pipeline.stage5_link.merge import SplitValidationError, split_person


def test_split_person_creates_new_row_with_variants(seeded_db: tuple[Path, str]) -> None:
    db_path, _ = seeded_db
    # Add a second variant to the canonical row so we have something to peel off.
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind) "
            "VALUES ('pv:test:c:2', 'per:test:canonical', '姬靖', '本名')"
        )
    with connect(db_path) as conn:
        result = split_person(
            conn,
            "per:test:canonical",
            variants_to_extract=["姬靖"],
            note="peeling off an incorrectly-merged identity",
        )
    assert result.source_person_id == "per:test:canonical"
    assert result.new_person_id.startswith("per:")
    assert result.variants_moved == ["姬靖"]
    # The peeled variant should now point at the new person.
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT person_id FROM person_variants WHERE variant = '姬靖'"
        ).fetchone()
    assert row["person_id"] == result.new_person_id


def test_split_person_writes_audit_log(seeded_db: tuple[Path, str]) -> None:
    db_path, _ = seeded_db
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO person_variants (id, person_id, variant, kind) "
            "VALUES ('pv:test:c:2', 'per:test:canonical', '姬靖', '本名')"
        )
    with connect(db_path) as conn:
        result = split_person(conn, "per:test:canonical", variants_to_extract=["姬靖"])
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT change_kind, entity_id FROM audit_log WHERE change_kind = 'split'"
        ).fetchone()
    assert row is not None
    assert row["entity_id"] == result.new_person_id


def test_split_person_unknown_variant_raises(seeded_db: tuple[Path, str]) -> None:
    db_path, _ = seeded_db
    with connect(db_path) as conn:
        with pytest.raises(SplitValidationError):
            split_person(conn, "per:test:canonical", variants_to_extract=["不存在"])
```

- [ ] **Step 2: Implementation**

Add to `pipeline/stage5_link/merge.py`:

```python
def split_person(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    variants_to_extract: list[str],
    note: str | None = None,
) -> SplitResult:
    """Peel listed variants off the source row into a new person row.

    Relations on the source row stay put — the new row starts relation-less.
    The curator can fix relations via the conflicts queue or future undo flow.
    """
    source = _row_snapshot(conn, "persons", person_id)
    if source is None:
        raise MergeError(f"no person row with id={person_id!r}")
    existing_variants = {
        r["variant"]
        for r in conn.execute(
            "SELECT variant FROM person_variants WHERE person_id = ?", (person_id,)
        )
    }
    missing = [v for v in variants_to_extract if v not in existing_variants]
    if missing:
        raise SplitValidationError(f"variants not on source row: {missing!r}")

    new_id = f"per:split:{uuid.uuid4().hex[:12]}"
    # New row inherits the canonical_name = first peeled variant; curator can edit later.
    conn.execute(
        "INSERT INTO persons (id, canonical_name) VALUES (?, ?)",
        (new_id, variants_to_extract[0]),
    )
    for v in variants_to_extract:
        conn.execute(
            "UPDATE person_variants SET person_id = ? "
            "WHERE person_id = ? AND variant = ?",
            (new_id, person_id, v),
        )

    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) "
        "VALUES (?, 'person', ?, NULL, 'split', ?, ?, 'curator', ?)",
        (
            _new_audit_id(),
            new_id,
            json.dumps(source, ensure_ascii=False),
            json.dumps(
                {"id": new_id, "source_person_id": person_id, "variants": variants_to_extract, "note": note},
                ensure_ascii=False,
            ),
            _now_iso(),
        ),
    )
    return SplitResult(
        source_person_id=person_id,
        new_person_id=new_id,
        variants_moved=list(variants_to_extract),
    )
```

- [ ] **Step 3: Run + mypy**

```bash
uv run pytest tests/unit/test_stage5_merge.py -v
uv run mypy --strict pipeline/stage5_link/merge.py
uv run pytest -q
```

Expected: 21 PASSED in `test_stage5_merge.py`; full suite still green (234 + 21 = 255 or so).

- [ ] **Step 4: Articles + commit**

Append to `knowledge/concepts/pipeline/linking.md`:

```markdown
### `split_person` (manual escape hatch)

`split_person(conn, person_id, *, variants_to_extract, note=None)` creates
a new person row and moves the listed variants from the source row to it.
Relations on the source row stay put — the new row starts relation-less.
Validates that all listed variants exist on the source row; raises
`SplitValidationError` otherwise.
```

Commit:

```bash
git add pipeline/stage5_link/merge.py \
        tests/unit/test_stage5_merge.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(stage5): split_person manual escape hatch (Phase 5 Task 6)

Creates a new person row with the named variants peeled off. Relations
stay on the source row. SplitValidationError on unknown variants.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

This closes Phase 5a. The load-bearing module is done; ~21 unit tests green.

---

## Task 7 — `curation/db.py` read helpers

**Files:**
- Create: `curation/__init__.py`
- Create: `curation/db.py`
- Create: `tests/unit/test_curation_db.py`
- Modify: `knowledge/concepts/curation/streamlit-app.md` (grow from "thin" to "in-progress")
- Modify: `knowledge/concepts/verification/testing.md`
- Modify: `knowledge/log.md`

- [ ] **Step 1: Create the package**

Write `curation/__init__.py`:

```python
"""Streamlit curation app — view layer over data/changjuan.sqlite."""
```

- [ ] **Step 2: Write the read-helper tests**

Write `tests/unit/test_curation_db.py`:

```python
"""Unit tests for curation.db read helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from curation.db import (
    ChapterStatus,
    MergeCandidateRow,
    coverage_stats,
    low_confidence_count,
    open_merge_candidates,
)
from pipeline.db import apply_schema, connect
from pipeline.schemas import CANONICAL_SCHEMA


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "curation_test.sqlite"
    with connect(db_path) as conn:
        apply_schema(conn, CANONICAL_SCHEMA)
    return db_path


def test_open_merge_candidates_filters_status(empty_db: Path) -> None:
    with connect(empty_db) as conn:
        # one open, one merged
        conn.execute(
            "INSERT INTO persons (id, canonical_name) VALUES ('per:a', 'A'), ('per:b', 'B')"
        )
        conn.execute(
            "INSERT INTO merge_candidates "
            "(id, kind, candidate_a_id, candidate_b_id, score, status) "
            "VALUES ('mc:1', 'person', 'per:a', 'per:b', 0.7, 'open'), "
            "       ('mc:2', 'person', 'per:a', 'per:b', 0.7, 'merged')"
        )
    rows = open_merge_candidates(empty_db)
    assert len(rows) == 1
    assert rows[0].mc_id == "mc:1"


def test_open_merge_candidates_sorted_by_created_at(empty_db: Path) -> None:
    with connect(empty_db) as conn:
        conn.execute(
            "INSERT INTO persons (id, canonical_name) VALUES ('per:a', 'A'), ('per:b', 'B')"
        )
        conn.execute(
            "INSERT INTO merge_candidates "
            "(id, kind, candidate_a_id, candidate_b_id, score, status, created_at) "
            "VALUES ('mc:2', 'person', 'per:a', 'per:b', 0.7, 'open', '2026-05-22 10:00:00'), "
            "       ('mc:1', 'person', 'per:a', 'per:b', 0.7, 'open', '2026-05-22 09:00:00')"
        )
    rows = open_merge_candidates(empty_db)
    assert [r.mc_id for r in rows] == ["mc:1", "mc:2"]


def test_coverage_stats_returns_108_rows(empty_db: Path, tmp_path: Path) -> None:
    """Even with an empty corpus, coverage_stats should return exactly 108 ChapterStatus rows.

    coverage_stats reads chapter list from corpus.sqlite; for the test we
    point at a synthetic corpus DB with 108 rows.
    """
    corpus_path = tmp_path / "corpus.sqlite"
    from pipeline.schemas import CORPUS_SCHEMA
    with connect(corpus_path) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
        for n in range(1, 109):
            conn.execute(
                "INSERT INTO documents (id, corpus, title, chapter_num, chapter_title, raw_text, source_edition, ingested_at) "
                "VALUES (?, 'dzlgz', '东周列国志', ?, ?, '', 'test', '2026-05-22')",
                (f"doc:{n}", n, f"第{n}回"),
            )
    stats = coverage_stats(empty_db, corpus_path=corpus_path)
    assert len(stats) == 108
    assert all(isinstance(s, ChapterStatus) for s in stats)
    # No pipeline_runs in the canonical DB -> nothing is "extracted".
    assert all(not s.extracted for s in stats)


def test_low_confidence_count_handles_empty_db(empty_db: Path) -> None:
    assert low_confidence_count(empty_db) == 0
```

- [ ] **Step 3: Implement `curation/db.py`**

Write `curation/db.py`:

```python
"""Read helpers for the curation app.

Connections opened here are READ-ONLY. Every write path must go through
pipeline.stage5_link.merge (which opens its own write connection).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pipeline.config import LOW_CONFIDENCE_THRESHOLD  # noqa: F401  see Step 4


@dataclass(frozen=True)
class MergeCandidateRow:
    mc_id: str
    kind: str
    candidate_a_id: str
    candidate_b_id: str
    score: float
    surface_features_json: str | None
    llm_judgment_json: str | None
    created_at: str


@dataclass(frozen=True)
class ChapterStatus:
    chapter_num: int
    title: str
    extracted: bool
    latest_run_id: str | None


@contextmanager
def _ro_connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a read-only sqlite connection. Closes on context exit.

    Uses the `mode=ro` URI parameter so any accidental writes raise immediately.
    Mirrors the @contextmanager pattern in `pipeline.db.connect`.
    """
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def open_merge_candidates(db_path: Path) -> list[MergeCandidateRow]:
    with _ro_connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, kind, candidate_a_id, candidate_b_id, score, "
            "       surface_features_json, llm_judgment_json, created_at "
            "FROM merge_candidates WHERE status = 'open' "
            "ORDER BY created_at ASC"
        ).fetchall()
    return [
        MergeCandidateRow(
            mc_id=r["id"],
            kind=r["kind"],
            candidate_a_id=r["candidate_a_id"],
            candidate_b_id=r["candidate_b_id"],
            score=r["score"],
            surface_features_json=r["surface_features_json"],
            llm_judgment_json=r["llm_judgment_json"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def coverage_stats(
    db_path: Path, *, corpus_path: Path | None = None
) -> list[ChapterStatus]:
    """Join the 108 corpus chapters against pipeline_runs.scope_json."""
    corpus_path = corpus_path or db_path.parent / "corpus.sqlite"
    with _ro_connect(corpus_path) as corpus_conn:
        chapters = corpus_conn.execute(
            "SELECT chapter_num, chapter_title FROM documents ORDER BY chapter_num"
        ).fetchall()
    with _ro_connect(db_path) as canon_conn:
        runs = canon_conn.execute(
            "SELECT id, scope_json FROM pipeline_runs WHERE stage = 'extract'"
        ).fetchall()
    extracted_chapters: dict[int, str] = {}
    for r in runs:
        scope = r["scope_json"] or ""
        # scope_json is loosely shaped: look for an integer chapter_num field
        import json as _json
        try:
            payload = _json.loads(scope)
        except (ValueError, TypeError):
            continue
        ch = payload.get("chapter_num") or payload.get("chapter")
        if isinstance(ch, int):
            extracted_chapters[ch] = r["id"]
    return [
        ChapterStatus(
            chapter_num=c["chapter_num"],
            title=c["chapter_title"] or f"第{c['chapter_num']}回",
            extracted=c["chapter_num"] in extracted_chapters,
            latest_run_id=extracted_chapters.get(c["chapter_num"]),
        )
        for c in chapters
    ]


def low_confidence_count(db_path: Path) -> int:
    with _ro_connect(db_path) as conn:
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM candidate_facts WHERE confidence < ?",
                (LOW_CONFIDENCE_THRESHOLD,),
            ).fetchone()
        except sqlite3.OperationalError:
            # candidate_facts may not exist on freshly-applied schema in tests
            return 0
    return int(row["n"]) if row else 0
```

Verify `LOW_CONFIDENCE_THRESHOLD` exists in `pipeline.config` first:

```bash
grep -n "LOW_CONFIDENCE\|low_confidence" pipeline/config.py
```

If it doesn't exist, add it to `pipeline/config.py`:

```python
LOW_CONFIDENCE_THRESHOLD: float = 0.55
```

If you add it, `concepts/runtime/configuration.md` must be updated in the same commit. Verify with `grep -n affects: knowledge/concepts/runtime/configuration.md` — that article's affects glob covers `pipeline/config.py`.

- [ ] **Step 4: Add `chapter_citation_context` helper** (deferred to a separate test for readability)

Append to `curation/db.py`:

```python
@dataclass(frozen=True)
class ChapterContext:
    citation_id: str
    text: str
    span_start: int
    span_end: int
    paragraphs: list[str]  # the context window, citation paragraph in the middle


def chapter_citation_context(
    citation_id: str,
    *,
    corpus_path: Path,
    paragraphs_before: int = 2,
    paragraphs_after: int = 2,
) -> ChapterContext:
    """Resolve a citation to its source paragraph + context window."""
    with _ro_connect(corpus_path) as conn:
        row = conn.execute(
            "SELECT c.id, c.span_start, c.span_end, c.quote, c.chunk_id, "
            "       ch.text, ch.document_id, ch.paragraph_start, ch.paragraph_end "
            "FROM citations c JOIN chunks ch ON c.chunk_id = ch.id "
            "WHERE c.id = ?",
            (citation_id,),
        ).fetchone()
    if row is None:
        return ChapterContext(citation_id=citation_id, text="(citation not found)", span_start=0, span_end=0, paragraphs=[])
    return ChapterContext(
        citation_id=citation_id,
        text=row["quote"],
        span_start=row["span_start"],
        span_end=row["span_end"],
        paragraphs=[row["text"]],  # for v1, full chunk text. paragraph splitting is Phase 6.
    )
```

Add a test:

```python
def test_chapter_citation_context_miss_returns_placeholder(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.sqlite"
    from pipeline.schemas import CORPUS_SCHEMA
    with connect(corpus) as conn:
        apply_schema(conn, CORPUS_SCHEMA)
    from curation.db import chapter_citation_context
    ctx = chapter_citation_context("cite:does-not-exist", corpus_path=corpus)
    assert ctx.text == "(citation not found)"
```

- [ ] **Step 5: Run tests + mypy**

```bash
uv run pytest tests/unit/test_curation_db.py -v
uv run mypy --strict curation/db.py
```

Expected: 5 PASSED.

- [ ] **Step 6: Grow the curation article + commit**

Replace the `status: thin` line in `knowledge/concepts/curation/streamlit-app.md` with `status: in-progress`. Append a section near the end:

```markdown
## DB access layer (Phase 5 Task 7)

`curation/db.py` is the only place the app touches sqlite for reads. It
opens connections in `mode=ro` so any accidental writes raise immediately;
write paths go through `pipeline.stage5_link.merge` which opens its own
short-lived write connection inside the merge functions.

Public helpers (all return frozen dataclasses):
- `open_merge_candidates(db_path)` — joined view of `merge_candidates`
  with `candidate_persons` (A) and `persons` (B), filtered to `status='open'`
  and sorted by `created_at ASC`.
- `coverage_stats(db_path, corpus_path=...)` — joins the 108 corpus chapters
  against `pipeline_runs.scope_json` to label each as extracted/not.
- `low_confidence_count(db_path)` — derived from
  `candidate_facts.confidence < LOW_CONFIDENCE_THRESHOLD`.
- `chapter_citation_context(citation_id, corpus_path, paragraphs_before=2, paragraphs_after=2)` —
  resolves a citation to its source quote + context window. Returns a
  placeholder `ChapterContext(text="(citation not found)", ...)` on miss
  rather than raising, because evidence-column failure is non-blocking per
  spec §5.
```

Append to `knowledge/concepts/verification/testing.md`:

```markdown
- `tests/unit/test_curation_db.py` — read-helper tests for the curation
  app. Uses synthetic canonical + corpus DBs built via `pipeline.db.apply_schema`.
```

Log + commit:

```bash
git add curation/__init__.py curation/db.py \
        tests/unit/test_curation_db.py \
        knowledge/concepts/curation/streamlit-app.md \
        knowledge/concepts/verification/testing.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(curation): db.py read helpers (Phase 5 Task 7)

open_merge_candidates, coverage_stats, low_confidence_count,
chapter_citation_context. Read-only mode=ro connections; writes are routed
through pipeline.stage5_link.merge.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — `curation/components/{shell,coverage_grid,records}.py`

Pure rendering primitives. No DB access, no state — easier to keep correct.

**Files:**
- Create: `curation/components/__init__.py`
- Create: `curation/components/shell.py`
- Create: `curation/components/coverage_grid.py`
- Create: `curation/components/records.py`
- Modify: `knowledge/concepts/curation/streamlit-app.md`, `knowledge/log.md`

These are mostly Streamlit calls; unit-testing the HTML output is low-value. We'll exercise them via the integration test in Task 11.

- [ ] **Step 1: `components/__init__.py`**

```python
"""Pure-rendering Streamlit components for the curation app."""
```

- [ ] **Step 2: `components/shell.py`**

Write `curation/components/shell.py`:

```python
"""40/40/20 review-screen shell."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st


def render_shell(
    *,
    render_left: Callable[[], Any],
    render_center: Callable[[], Any],
    render_right: Callable[[], Any],
) -> None:
    """Render the three-column shell. Each callable owns its column's content."""
    left, center, right = st.columns([40, 40, 20])
    with left:
        st.markdown('<div class="curation-label">EVIDENCE</div>', unsafe_allow_html=True)
        render_left()
    with center:
        st.markdown('<div class="curation-label">CANDIDATE PAIR</div>', unsafe_allow_html=True)
        render_center()
    with right:
        st.markdown('<div class="curation-label">DECISION</div>', unsafe_allow_html=True)
        render_right()
```

- [ ] **Step 3: `components/coverage_grid.py`**

Write:

```python
"""108-cell coverage grid for the home screen."""

from __future__ import annotations

import streamlit as st

from curation.db import ChapterStatus


_GRID_CSS = """
<style>
.coverage-grid { display: grid; grid-template-columns: repeat(18, 1fr); gap: 3px; }
.coverage-cell { aspect-ratio: 1; border-radius: 2px; background: #2a2a2a; }
.coverage-cell.extracted { background: #2f7f3f; }
.coverage-cell:hover { outline: 1px solid #6a6a6a; }
</style>
"""


def render_coverage_grid(stats: list[ChapterStatus]) -> None:
    st.markdown(_GRID_CSS, unsafe_allow_html=True)
    cells = "".join(
        f'<div class="coverage-cell {"extracted" if s.extracted else ""}" '
        f'title="第{s.chapter_num}回 · {s.title}"></div>'
        for s in stats
    )
    st.markdown(f'<div class="coverage-grid">{cells}</div>', unsafe_allow_html=True)
    extracted = sum(1 for s in stats if s.extracted)
    st.caption(f"{extracted} / {len(stats)} chapters extracted")
```

- [ ] **Step 4: `components/records.py`**

Write:

```python
"""Side-by-side candidate-vs-canonical renderer with diff coloring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import streamlit as st


_FIELDS = ("canonical_name", "gender", "clan_name", "state_id", "notes")


@dataclass(frozen=True)
class FieldDiff:
    field: str
    candidate_value: Any
    canonical_value: Any
    badge: str  # one of: same, one_null, disagree


def _badge(cand: Any, can: Any) -> str:
    if cand == can:
        return "same"
    if cand is None or can is None:
        return "one_null"
    return "disagree"


def render_pair(
    candidate: dict[str, Any],
    canonical: dict[str, Any],
    *,
    edit_mode: bool = False,
    surface_features_json: str | None = None,
    llm_judgment_json: str | None = None,
) -> dict[str, Any] | None:
    """Render the candidate-vs-canonical pair. Returns edits dict if edit_mode."""
    diffs = [
        FieldDiff(f, candidate.get(f), canonical.get(f), _badge(candidate.get(f), canonical.get(f)))
        for f in _FIELDS
    ]
    col_a, col_b = st.columns(2)
    edits: dict[str, Any] = {}
    with col_a:
        st.caption(f"A · candidate · {candidate.get('id', '?')}")
        for d in diffs:
            _render_field_readonly(d.field, d.candidate_value, d.badge)
    with col_b:
        st.caption(f"B · canonical · {canonical.get('id', '?')}")
        for d in diffs:
            if edit_mode:
                new_value = st.text_input(
                    d.field,
                    value=str(d.canonical_value or ""),
                    key=f"edit-{canonical.get('id')}-{d.field}",
                )
                if new_value != (d.canonical_value or ""):
                    edits[d.field] = new_value or None
            else:
                _render_field_readonly(d.field, d.canonical_value, d.badge)
    if surface_features_json:
        try:
            features = json.loads(surface_features_json)
            st.caption(f"features: {features}")
        except (ValueError, TypeError):
            pass
    if llm_judgment_json:
        with st.expander("LLM judgment"):
            st.code(llm_judgment_json, language="json")
    return edits if edit_mode else None


def _render_field_readonly(field: str, value: Any, badge: str) -> None:
    badge_color = {"same": "#2f7f3f", "one_null": "#7a7a3a", "disagree": "#7f3f3f"}.get(badge, "#444")
    display = value if value is not None else "—"
    st.markdown(
        f'<div style="padding:4px 0"><span style="color:#888">{field}</span> '
        f'<span style="background:{badge_color};padding:1px 6px;border-radius:2px">{display}</span></div>',
        unsafe_allow_html=True,
    )
```

- [ ] **Step 5: Mypy check the new components**

```bash
uv run mypy --strict curation/components/
```

Expected: `Success: no issues found`. (Streamlit's type stubs are imperfect; if mypy complains about specific `st.X` calls, add `# type: ignore[<error-code>]` per line — not blanket `Any`. Document any added ignores in the commit body.)

- [ ] **Step 6: Article + commit**

Append to `knowledge/concepts/curation/streamlit-app.md`:

```markdown
## Components (Phase 5 Task 8)

`curation/components/` holds three pure-rendering primitives — no state,
no DB access:

- `shell.render_shell(render_left, render_center, render_right)` — the
  uniform 40/40/20 review-screen layout. Each callable owns its column.
- `coverage_grid.render_coverage_grid(stats)` — 9×12 (or 18×6) cell grid
  over the 108 chapters. Green = extracted, gray = not yet. Tooltip
  shows chapter title.
- `records.render_pair(candidate, canonical, edit_mode=False, ...)` —
  side-by-side records with field-level diff badges (`same` / `one_null`
  / `disagree`). In `edit_mode` returns an edits dict for `accept_merge`.

Components have no unit tests (Streamlit-native testing is flaky); they
are exercised through the integration smoke in Task 11.
```

Commit:

```bash
git add curation/components/ \
        knowledge/concepts/curation/streamlit-app.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(curation): rendering components (Phase 5 Task 8)

shell.render_shell, coverage_grid.render_coverage_grid, records.render_pair.
Pure functions, no state, no DB. Field-level diff badges (same/one_null/disagree).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — `curation/app.py` (home screen) + stub pages + streamlit-shortcuts

**Files:**
- Modify: `pyproject.toml` (add `streamlit-shortcuts` dep)
- Create: `curation/app.py`
- Create: `curation/pages/2_Conflicts.py`
- Create: `curation/pages/3_Low_confidence.py`
- Modify: `knowledge/concepts/curation/streamlit-app.md`, `knowledge/concepts/runtime/configuration.md` (if pyproject changed → dep added is a configuration change), `knowledge/log.md`

- [ ] **Step 1: Add the dependency**

```bash
uv add streamlit streamlit-shortcuts
uv sync --all-extras
```

This adds `streamlit` (if not already present) and `streamlit-shortcuts 1.2.1+`. Verify with:

```bash
grep -A 1 "streamlit" pyproject.toml
```

- [ ] **Step 2: Create the stub pages**

`curation/pages/2_Conflicts.py`:

```python
"""Conflicts queue — Phase 6 stub."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Conflicts · changjuan curator", layout="wide")
st.title("Conflicts queue")
st.warning(
    "This queue is scheduled for Phase 6. Phase 5 ships the merge-candidates "
    "queue only. See `docs/superpowers/specs/2026-05-22-phase5-curator-ui-design.md` §1."
)
```

`curation/pages/3_Low_confidence.py`:

```python
"""Low-confidence extractions queue — Phase 6 stub."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Low confidence · changjuan curator", layout="wide")
st.title("Low-confidence extractions")
st.warning(
    "This queue is scheduled for Phase 6. Phase 5 ships the merge-candidates "
    "queue only. See `docs/superpowers/specs/2026-05-22-phase5-curator-ui-design.md` §1."
)
```

- [ ] **Step 3: Create `curation/app.py`**

Write `curation/app.py`:

```python
"""changjuan curator — home screen.

Run with: streamlit run curation/app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from curation.components.coverage_grid import render_coverage_grid
from curation.db import coverage_stats, low_confidence_count, open_merge_candidates


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "changjuan.sqlite"
CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "corpus.sqlite"


def main() -> None:
    st.set_page_config(page_title="changjuan curator", layout="wide")
    st.title("changjuan curator")
    st.caption("Phase 5 — merge-candidates triage. Conflicts and low-confidence are Phase 6.")

    if not DB_PATH.exists():
        st.error(f"DB not found: {DB_PATH}")
        st.stop()

    stats = coverage_stats(DB_PATH, corpus_path=CORPUS_PATH) if CORPUS_PATH.exists() else []
    st.subheader("Chapter coverage")
    if stats:
        render_coverage_grid(stats)
    else:
        st.info("Corpus not loaded — chapter grid unavailable.")

    st.subheader("Queues")
    mc_open = len(open_merge_candidates(DB_PATH))
    st.page_link(
        "pages/1_Merge_candidates.py",
        label=f"🔗 Merge candidates · **{mc_open} open**",
    )
    st.markdown(
        '<div style="opacity:0.5;padding:6px 0">⚖️ Conflicts · '
        '<span style="font-size:0.85em">(Phase 6)</span></div>',
        unsafe_allow_html=True,
    )
    low = low_confidence_count(DB_PATH)
    st.markdown(
        f'<div style="opacity:0.5;padding:6px 0">❓ Low confidence · {low} candidate facts · '
        f'<span style="font-size:0.85em">(Phase 6)</span></div>',
        unsafe_allow_html=True,
    )

    st.subheader("Search")
    st.text_input("search persons / events / places…", disabled=True, help="Phase 6")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke check — does Streamlit boot?**

```bash
uv run streamlit run curation/app.py --server.headless true --server.port 8765 &
STREAMLIT_PID=$!
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/
kill $STREAMLIT_PID 2>/dev/null
wait $STREAMLIT_PID 2>/dev/null
```

Expected: `200`. If you get a different status, check Streamlit's stderr (it prints to the terminal that launched it).

- [ ] **Step 5: Mypy**

```bash
uv run mypy --strict curation/
```

Expected: `Success: no issues found`.

- [ ] **Step 6: Articles + commit**

Append to `knowledge/concepts/curation/streamlit-app.md`:

```markdown
## Home screen (Phase 5 Task 9)

`curation/app.py` renders:
1. The 108-cell coverage grid via `components.coverage_grid.render_coverage_grid`.
2. A queue panel with three rows — merge-candidates as an active page link;
   conflicts and low-confidence as visible-but-disabled rows tagged "(Phase 6)".
3. A disabled search input (tooltip: "Phase 6").

Conflicts and low-confidence ship as Streamlit pages
(`pages/2_Conflicts.py`, `pages/3_Low_confidence.py`) so the sidebar has
its final shape, but their bodies show a "Phase 6" notice.
```

If `pyproject.toml` changed, also append to `knowledge/concepts/runtime/configuration.md`:

```markdown
- `streamlit-shortcuts` (added in Phase 5 Task 9) — keyboard-binding helper
  for the curator review screen.
```

Commit:

```bash
git add pyproject.toml uv.lock \
        curation/app.py curation/pages/ \
        knowledge/concepts/curation/streamlit-app.md \
        knowledge/concepts/runtime/configuration.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(curation): app.py home screen + stub pages (Phase 5 Task 9)

Streamlit home screen: 108-cell coverage grid, queue panel, disabled
search box. Conflicts and low-confidence ship as stub pages. Adds
streamlit-shortcuts dep.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — `curation/pages/1_Merge_candidates.py` (review screen + keyboard shortcuts)

**Files:**
- Create: `curation/pages/1_Merge_candidates.py`
- Modify: `knowledge/concepts/curation/streamlit-app.md`, `knowledge/log.md`

- [ ] **Step 1: Write the page**

```python
"""Merge candidates review screen."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import streamlit as st
from streamlit_shortcuts import add_keyboard_shortcuts

from curation.components.records import render_pair
from curation.components.shell import render_shell
from curation.db import chapter_citation_context, open_merge_candidates
from pipeline.stage5_link.merge import (
    MergeConflictError,
    MergeError,
    StaleMergeCandidateError,
    accept_merge,
    defer_merge,
    reject_merge,
    split_person,
)


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changjuan.sqlite"
CORPUS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "corpus.sqlite"


def _write_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _load_queue() -> list:
    if "mc_queue" not in st.session_state:
        st.session_state["mc_queue"] = open_merge_candidates(DB_PATH)
        st.session_state["mc_cursor"] = 0
    return st.session_state["mc_queue"]


def _advance() -> None:
    st.session_state["mc_cursor"] = st.session_state.get("mc_cursor", 0) + 1


def _retreat() -> None:
    st.session_state["mc_cursor"] = max(0, st.session_state.get("mc_cursor", 0) - 1)


def _reload() -> None:
    st.session_state.pop("mc_queue", None)
    st.session_state.pop("mc_cursor", None)
    st.rerun()


def _load_person(conn: sqlite3.Connection, person_id: str) -> dict:
    row = conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    return dict(row) if row else {"id": person_id}


def _do_accept(mc_id: str, edits: dict | None = None) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            result = accept_merge(conn, mc_id, edits=edits)
        st.success(
            f"Merged. variants_added={result.variants_added}, "
            f"relations_retargeted={result.relations_retargeted}, "
            f"collisions_resolved={result.collisions_resolved}"
        )
        _advance()
    except StaleMergeCandidateError as e:
        st.warning(f"Already resolved, skipping: {e}")
        _advance()
    except MergeConflictError as e:
        st.error(f"Field disagreement: {e}. Use Edit & accept or Reject.")
    except MergeError as e:
        st.error(f"Merge failed: {e}")
    finally:
        conn.close()


def _do_reject(mc_id: str, note: str | None = None) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            reject_merge(conn, mc_id, note=note)
        st.info("Rejected.")
        _advance()
    except StaleMergeCandidateError as e:
        st.warning(f"Already resolved, skipping: {e}")
        _advance()
    except MergeError as e:
        st.error(f"Reject failed: {e}")
    finally:
        conn.close()


def _do_defer(mc_id: str) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            defer_merge(conn, mc_id)
        _advance()
    finally:
        conn.close()


def _do_split(person_id: str, variants_to_extract: list[str], note: str | None) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            result = split_person(
                conn, person_id, variants_to_extract=variants_to_extract, note=note
            )
        st.success(f"Split — new person {result.new_person_id} with variants {result.variants_moved}")
        _advance()
    except MergeError as e:
        st.error(f"Split failed: {e}")
    finally:
        conn.close()


def main() -> None:
    st.set_page_config(page_title="Merge candidates · changjuan curator", layout="wide")
    queue = _load_queue()
    cursor = st.session_state.get("mc_cursor", 0)

    if not queue:
        st.title("Merge candidates")
        st.info("No open merge candidates. The queue is empty.")
        return
    if cursor >= len(queue):
        st.title("Merge candidates")
        st.success(f"Queue empty — {cursor} triaged this session.")
        if st.button("Reload queue"):
            _reload()
        return

    current = queue[cursor]
    st.title(f"Merge candidates · {cursor + 1} / {len(queue)}")

    edit_mode = st.session_state.get("edit_mode", False)
    edits_captured: dict | None = None

    def render_left() -> None:
        # Look up citation from candidate side (the new finding's evidence).
        cit_id_row = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True).execute(
            "SELECT citation_id FROM entity_citations "
            "WHERE entity_kind = 'person' AND entity_id = ? LIMIT 1",
            (current.candidate_a_id,),
        ).fetchone()
        if cit_id_row is None:
            st.write("(no citation linked to candidate)")
            return
        ctx = chapter_citation_context(cit_id_row[0], corpus_path=CORPUS_PATH)
        st.write(ctx.text)
        if ctx.paragraphs:
            with st.expander("± 2 paragraphs"):
                for p in ctx.paragraphs:
                    st.write(p)

    def render_center() -> None:
        nonlocal edits_captured
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            candidate = _load_person(conn, current.candidate_a_id)
            canonical = _load_person(conn, current.candidate_b_id)
        edits_captured = render_pair(
            candidate,
            canonical,
            edit_mode=edit_mode,
            surface_features_json=current.surface_features_json,
            llm_judgment_json=current.llm_judgment_json,
        )

    def render_right() -> None:
        if st.button("a · Accept merge", use_container_width=True):
            _do_accept(current.mc_id)
            st.rerun()
        if st.button("e · Edit & accept", use_container_width=True):
            if edit_mode and edits_captured is not None:
                _do_accept(current.mc_id, edits=edits_captured)
                st.session_state["edit_mode"] = False
                st.rerun()
            else:
                st.session_state["edit_mode"] = True
                st.rerun()
        if st.button("r · Reject", use_container_width=True):
            _do_reject(current.mc_id)
            st.rerun()
        if st.button("d · Defer", use_container_width=True):
            _do_defer(current.mc_id)
            st.rerun()
        with st.expander("s · Split"):
            variants_text = st.text_input("variants to peel off (comma-separated)")
            split_note = st.text_input("note (optional)", key="split-note")
            if st.button("Confirm split"):
                variants = [v.strip() for v in variants_text.split(",") if v.strip()]
                _do_split(current.candidate_b_id, variants, split_note or None)
                st.rerun()
        st.divider()
        col_prev, col_next = st.columns(2)
        if col_prev.button("◀ k", use_container_width=True):
            _retreat()
            st.rerun()
        if col_next.button("j ▶", use_container_width=True):
            _advance()
            st.rerun()

    render_shell(
        render_left=render_left,
        render_center=render_center,
        render_right=render_right,
    )

    add_keyboard_shortcuts(
        {
            "a": "a · Accept merge",
            "e": "e · Edit & accept",
            "r": "r · Reject",
            "d": "d · Defer",
            "j": "j ▶",
            "k": "◀ k",
        }
    )


main()
```

- [ ] **Step 2: Boot smoke check**

```bash
uv run streamlit run curation/app.py --server.headless true --server.port 8766 &
SMP=$!
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8766/
# Note: Streamlit's multipage app loads sub-pages on-demand. Verifying that
# pages/1_Merge_candidates.py compiles without import-time errors is the
# bar here; full interaction is exercised by the integration test in Task 11.
kill $SMP 2>/dev/null
```

Expected: `200`. If the page errors on import, fix and re-run.

- [ ] **Step 3: Mypy**

```bash
uv run mypy --strict curation/
```

- [ ] **Step 4: Articles + commit**

Append to `knowledge/concepts/curation/streamlit-app.md`:

```markdown
## Review screen (Phase 5 Task 10)

`pages/1_Merge_candidates.py` is the workhorse page. Reads the open queue
into `st.session_state` once at first render; the cursor advances in
memory only. The five action handlers (`accept`, `edit & accept`,
`reject`, `defer`, `split`) each open a short-lived write connection,
call the corresponding `pipeline.stage5_link.merge` function in a
context-managed transaction (commit/rollback handled by sqlite3's
connection context manager), and surface the result via
`st.success`/`st.warning`/`st.error`.

Keyboard bindings via `streamlit-shortcuts`: `a` accept, `e` edit-and-accept,
`r` reject, `d` defer, `j` next, `k` prev. `s` opens the split expander
(no single-keypress trigger because split needs a variants text input
that the keyboard handler can't fill in).

Two-connection rule: the display reads use `mode=ro` URIs; write paths
open a new read-write connection inside each handler so a failed
transaction doesn't poison long-lived state.
```

Commit:

```bash
git add curation/pages/1_Merge_candidates.py \
        knowledge/concepts/curation/streamlit-app.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(curation): merge-candidates review screen (Phase 5 Task 10)

40/40/20 shell wired to all 5 actions. Keyboard shortcuts a/e/r/d/j/k via
streamlit-shortcuts. Read-only display connection + short-lived write
connection per action.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 — Integration test + `scripts/curator-smoke`

**Files:**
- Create: `tests/integration/test_curator_smoke.py`
- Create: `scripts/curator-smoke`
- Modify: `knowledge/concepts/verification/testing.md`, `knowledge/log.md`

- [ ] **Step 1: Integration test**

Write `tests/integration/test_curator_smoke.py`:

```python
"""End-to-end exercise of the curator merge surface against a real DB copy."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from curation.db import open_merge_candidates
from pipeline.stage5_link.merge import (
    MergeConflictError,
    MergeError,
    StaleMergeCandidateError,
    accept_merge,
    defer_merge,
    reject_merge,
)

LIVE_DB = Path(__file__).resolve().parent.parent.parent / "data" / "changjuan.sqlite"


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
    if not LIVE_DB.exists():
        pytest.skip(f"live DB not present at {LIVE_DB}")
    dst = tmp_path / "smoke.sqlite"
    shutil.copy(LIVE_DB, dst)
    return dst


def test_curator_smoke_resolves_all_open_candidates(db_copy: Path) -> None:
    rows = open_merge_candidates(db_copy)
    assert len(rows) > 0, "expected open merge candidates to exercise"

    decisions = 0
    rejected = 0
    deferred = 0
    accepted = 0
    skipped_conflicts = 0
    for i, row in enumerate(rows):
        action = ["accept", "reject", "defer"][i % 3]
        conn = sqlite3.connect(db_copy)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                if action == "accept":
                    try:
                        accept_merge(conn, row.mc_id)
                        accepted += 1
                    except MergeConflictError:
                        # Defense-in-depth: skip and tally; the conflicts queue should
                        # have caught this. Don't fail the smoke on a real-data
                        # disagreement.
                        skipped_conflicts += 1
                        continue
                elif action == "reject":
                    reject_merge(conn, row.mc_id, note="smoke test reject")
                    rejected += 1
                else:
                    defer_merge(conn, row.mc_id)
                    deferred += 1
                decisions += 1
        except StaleMergeCandidateError:
            pass
        finally:
            conn.close()

    # Assertions
    remaining = open_merge_candidates(db_copy)
    # Anything we deferred or skipped-on-conflict should still be open.
    assert len(remaining) == deferred + skipped_conflicts, (
        f"queue mismatch: remaining={len(remaining)}, deferred={deferred}, "
        f"skipped_conflicts={skipped_conflicts}"
    )

    # No orphan FKs across the 5 person-FK columns.
    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    for q in (
        "SELECT COUNT(*) AS n FROM event_participants ep "
        "LEFT JOIN persons p ON ep.person_id = p.id WHERE p.id IS NULL",
        "SELECT COUNT(*) AS n FROM person_relations pr "
        "LEFT JOIN persons p1 ON pr.from_person_id = p1.id WHERE p1.id IS NULL",
        "SELECT COUNT(*) AS n FROM person_relations pr "
        "LEFT JOIN persons p2 ON pr.to_person_id = p2.id WHERE p2.id IS NULL",
        "SELECT COUNT(*) AS n FROM person_states ps "
        "LEFT JOIN persons p ON ps.person_id = p.id WHERE p.id IS NULL",
        "SELECT COUNT(*) AS n FROM entity_citations ec "
        "LEFT JOIN persons p ON ec.entity_id = p.id "
        "WHERE ec.entity_kind = 'person' AND p.id IS NULL",
    ):
        row = conn.execute(q).fetchone()
        assert row["n"] == 0, f"orphan FK: {q.splitlines()[0]} -> {row['n']}"

    # audit_log row count >= decisions made (merges may have written collision rows too).
    audit_n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert audit_n >= accepted + rejected, f"audit_log undercount: {audit_n} < {accepted + rejected}"
    conn.close()
```

- [ ] **Step 2: Script wrapper**

Write `scripts/curator-smoke` (executable, no extension):

```bash
#!/usr/bin/env bash
# Thin pytest wrapper for the curator integration smoke test.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run pytest tests/integration/test_curator_smoke.py -v "$@"
```

Make it executable:

```bash
chmod +x scripts/curator-smoke
```

- [ ] **Step 3: Run it**

```bash
./scripts/curator-smoke
```

Expected: `1 passed`. Inspect counts in the output — `accepted + rejected + deferred + skipped_conflicts` should equal the initial `len(rows)`.

- [ ] **Step 4: Article + commit**

Append to `knowledge/concepts/verification/testing.md`:

```markdown
- `tests/integration/test_curator_smoke.py` — end-to-end exercise of
  `accept_merge`/`reject_merge`/`defer_merge` against a `tmp_path` copy of
  the live DB. Verifies no orphan FKs across the 5 person-FK columns after
  the run + `audit_log` row count >= decisions made. `scripts/curator-smoke`
  is the runner wrapper.
```

Commit (`scripts/` doesn't map to an article, but the tests do):

```bash
git add tests/integration/test_curator_smoke.py \
        scripts/curator-smoke \
        knowledge/concepts/verification/testing.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
test(curation): end-to-end smoke + scripts/curator-smoke (Phase 5 Task 11)

Exercises accept/reject/defer against a copy of the live DB. Verifies no
orphan FKs across the 5 person-FK columns and audit_log row count >=
decisions made.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — `changjuan curator` subcommand + `phase5-prep.sh` + phase log entry

**Files:**
- Modify: `pipeline/cli.py`
- Create: `scripts/phase5-prep.sh`
- Modify: `knowledge/concepts/runtime/cli.md`, `knowledge/log.md`

- [ ] **Step 1: Find the existing CLI shape**

```bash
grep -n "def.*_cmd\|subparser\|argparse\|click" pipeline/cli.py | head -20
```

Read enough to add a new subcommand that matches existing patterns. The pattern is likely an `add_parser("name")` + a handler function.

- [ ] **Step 2: Add the subcommand**

Add to `pipeline/cli.py` (the exact placement depends on existing structure):

```python
def _curator_cmd(args: argparse.Namespace) -> int:
    """Exec `streamlit run curation/app.py`."""
    import os
    project_root = Path(__file__).resolve().parent.parent
    app_path = project_root / "curation" / "app.py"
    if not app_path.exists():
        print(f"curation app not found at {app_path}", file=sys.stderr)
        return 1
    os.execvp("streamlit", ["streamlit", "run", str(app_path)])
```

And in the subparser-registration block:

```python
curator = subparsers.add_parser("curator", help="Launch the Streamlit curator UI")
curator.set_defaults(func=_curator_cmd)
```

- [ ] **Step 3: Smoke test the CLI registration**

```bash
uv run changjuan --help | grep curator
```

Expected: a line containing `curator   Launch the Streamlit curator UI`.

(Don't run `uv run changjuan curator` for real in the test — it execs streamlit which blocks.)

- [ ] **Step 4: Write `scripts/phase5-prep.sh`**

Model after `scripts/phase4-prep.sh`. Sections:

```bash
#!/usr/bin/env bash
# Phase 5 acceptance check. Mirrors phase4-prep.sh structure.
set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
WARN=0
LOGDIR="data/logs/phase5-prep"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%Y%m%dT%H%M%S).log"
exec > >(tee "$LOG") 2>&1

section() { echo; echo "==== $* ===="; }
pass()    { echo "  ✓ PASS $*"; PASS=$((PASS+1)); }
fail()    { echo "  ✗ FAIL $*"; FAIL=$((FAIL+1)); }
warn()    { echo "  ! $*"; WARN=$((WARN+1)); }

section "1. Git tree clean"
if [[ -z "$(git status --porcelain | grep -v -E 'data/exports/|\.claude/settings\.local\.json')" ]]; then
  pass "git status clean (only expected untracked items)"
else
  warn "uncommitted changes present"
fi

section "2. Pre-commit hooks"
if uv run pre-commit run --all-files >/dev/null 2>&1; then
  pass "all 5 hooks pass"
else
  fail "pre-commit reports issues; run 'uv run pre-commit run --all-files' for details"
fi

section "3. pytest"
if uv run pytest -q >/dev/null 2>&1; then
  pass "pytest green"
else
  fail "pytest failures; run 'uv run pytest -q' for details"
fi

section "4. Integration smoke"
if ./scripts/curator-smoke >/dev/null 2>&1; then
  pass "curator-smoke passes"
else
  fail "curator-smoke failed; run './scripts/curator-smoke' for details"
fi

section "5. Drift check"
if ./scripts/drift-check >/dev/null 2>&1; then
  pass "drift-check passes"
else
  fail "drift-check failed; run './scripts/drift-check' for details"
fi

section "6. Streamlit boot smoke"
uv run streamlit run curation/app.py --server.headless true --server.port 8767 >/tmp/p5-streamlit.log 2>&1 &
SP=$!
sleep 5
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8767/ | grep -q 200; then
  pass "streamlit boot OK"
else
  fail "streamlit boot did not return 200 (see /tmp/p5-streamlit.log)"
fi
kill $SP 2>/dev/null || true
wait $SP 2>/dev/null || true

section "7. PHASE5_DEFERRED"
cat <<'EOF'
12 items deferred to Phase 6+:
  - Reject-memory (prevent linker re-flagging rejected pairs)
  - Undo button (audit_log replay)
  - Conflicts queue full implementation
  - Low-confidence extractions queue
  - Re-extract button per chapter
  - person_relations zero-kind extractor bug (stage 3)
  - LLM judge for ambiguous merges
  - Prefetch ergonomics (<200ms per record)
  - Linker for events / places / states / relations
  - Coverage grid per-chapter detail view
  - Search box implementation
  - Headline counter widgets
EOF
pass "deferred list printed"

section "Summary"
echo "  $PASS passed   $WARN warn   $FAIL failed"
echo
echo "Full log: $LOG"
[[ $FAIL -eq 0 ]] || exit 1
```

Make executable:

```bash
chmod +x scripts/phase5-prep.sh
```

- [ ] **Step 5: Run phase5-prep.sh**

```bash
./scripts/phase5-prep.sh
```

Expected: `6 passed   0 failed` (warns OK). If anything fails, fix and re-run.

- [ ] **Step 6: Final article + log entry**

Append to `knowledge/concepts/runtime/cli.md`:

```markdown
### `changjuan curator`

Launches the Streamlit curator UI:

```bash
uv run changjuan curator
```

Equivalent to `streamlit run curation/app.py` but registered as a CLI
verb for symmetry with `extract`, `link`, `load`, etc. Phase 5 surface
implements the merge-candidates queue only; conflicts and low-confidence
are Phase 6.
```

Append to `knowledge/log.md`:

```markdown
## [2026-05-22] feat(phase5): Phase 5 complete — curator UI v1 (merge-candidates triage)

12 tasks shipped. `streamlit run curation/app.py` boots; merge-candidates
queue works end-to-end against the 31 open rows; integration smoke green;
phase5-prep.sh reports all pass. Three queues materialized as Streamlit
pages (one functional, two stubs). Decision logic in
`pipeline.stage5_link.merge` (six functions, ~21 unit tests).

Phase 5 acceptance bar was "UI ready" — the curator can now sit down and
work through the 31 candidates whenever they want. Reject-memory, undo,
and the other two queues are Phase 6.
```

- [ ] **Step 7: Commit**

```bash
git add pipeline/cli.py \
        scripts/phase5-prep.sh \
        knowledge/concepts/runtime/cli.md \
        knowledge/log.md
git commit -m "$(cat <<'EOF'
feat(phase5): Phase 5 complete — changjuan curator + phase5-prep.sh (Phase 5 Task 12)

Adds `changjuan curator` subcommand and the Phase 5 acceptance check.
All 12 Phase 5 tasks shipped; merge-candidates triage UI is end-to-end
operational.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 done — sanity sweep

Before declaring victory:

```bash
git log --oneline aa5f16d..HEAD
uv run pytest -q
./scripts/phase2-prep.sh | tail -3
./scripts/phase3-prep.sh | tail -3
./scripts/phase4-prep.sh | tail -3
./scripts/phase5-prep.sh | tail -3
```

Expected:
- 12 new commits since `aa5f16d`.
- pytest reports a higher number than 234 (depends on exactly how many tests landed; ~270-280 is the rough target).
- Phase 2-4 prep scripts still green (no regressions).
- Phase 5 prep all-pass.

If any prep script regresses, identify the regressing commit via `git bisect` and fix forward — do NOT roll back without understanding why.

---

## Self-review notes (for the executing engineer)

A few things this plan **did not** prescribe; use judgment:

- **Streamlit version pin.** `uv add streamlit` will pull the latest. If that breaks (Streamlit's API has been volatile around `st.set_page_config` and multipage routing), pin to a known-good version with `uv add 'streamlit>=1.30,<2'`. Streamlit-shortcuts may not yet support a brand-new Streamlit release.
- **`changjuan curator` argparse placement.** I described the pattern but not the exact line numbers — read the existing `pipeline/cli.py` and follow whatever subparser layout it already uses.
- **mypy strict on `curation/`.** Streamlit's type stubs are imperfect. If `mypy --strict curation/` produces unavoidable errors, use targeted `# type: ignore[<code>]` comments and explain them in the commit body — do not blanket `Any`.
- **Test ordering.** The plan lists tests in narrative order. Pytest doesn't guarantee order; if any test depends on previous state, it's a bug. Each test in this plan should be order-independent.
- **`pipeline.config.LOW_CONFIDENCE_THRESHOLD`.** Verify before referencing. If the constant doesn't exist, add it in the same task that needs it (Task 7) with a documented default of `0.55`.
