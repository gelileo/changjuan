# Phase 6 Implementation Plan — Curator Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship reject-memory so the linker never re-flags rejected pairs; walk the 31 open `merge_candidates` to recorded decisions; fix the one-line `person_relations` field-name bug and backfill the table.

**Architecture:** Three tracks. **Track A** (reject-memory) adds a `rejected_merges` table and a pure fingerprint helper, extends `reject_merge` to write to it, and adds a filter to the linker. **Track C** (person_relations bug) flips one field name in `stage3_extract.py` and replays cached YAMLs through stages 3→5→7. **Track B** (walk the 31) is curator work over the Phase 5 UI on top of a `.bak` snapshot, with a ≤3 friction-fix budget and a retrospective. Order: A → C → B (A is a hard prerequisite for B; C is independent and lands between).

**Tech Stack:** Python 3.14, sqlite3 (`mode=ro` for reads in curation; `with conn:` transactions for writes), typer CLI, pytest, Streamlit + streamlit-shortcuts. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-23-phase6-curator-hardening-design.md` (committed `85dba53`).

---

## File structure (declared up front)

| File | Action | Responsibility |
|---|---|---|
| `pipeline/stage5_link/fingerprint.py` | **Create** | Pure helper: `candidate_fingerprint(name, variants)` → 16-hex SHA-1. No DB access. |
| `pipeline/schemas/canonical_schema.sql` | Modify (line ~363 area) | Add `rejected_merges` table + index. |
| `pipeline/stage5_link/merge.py` | Modify (`reject_merge` at line 492) | After existing audit_log write, look up candidate A's name/variants from `candidate_persons` or `persons` (table-detection branch), compute fingerprint, `INSERT OR IGNORE` into `rejected_merges`. |
| `pipeline/stage5_link/linker.py` | Modify (`link_run` at line 58) | Load rejection set once per run; skip pairs whose `(canonical_id, fingerprint)` is in the set. Honor `ignore_rejections` arg. |
| `pipeline/stage5_link/__init__.py` | Modify | Re-export `candidate_fingerprint` for cross-module use. |
| `pipeline/cli.py` | Modify (`link` at line 696) | Add `--ignore-rejections` boolean flag; pass through. |
| `pipeline/stage3_extract.py` | Modify (line 377) | `relation_kind` → `kind_detail`. |
| `tests/unit/test_fingerprint.py` | **Create** | Unit tests for the pure helper. |
| `tests/unit/test_reject_memory.py` | **Create** | Unit tests for `reject_merge`'s new rejected_merges side effect. |
| `tests/integration/test_link_rejection_loop.py` | **Create** | End-to-end link → reject → link assertion. |
| `tests/integration/test_person_relations_backfill.py` | **Create** | Stages 3→5→7 against fixture YAML, assert `person_relations` populated. |
| `scripts/phase6-prep.sh` | **Create** | Acceptance check mirroring `phase5-prep.sh`. |
| `docs/superpowers/retros/2026-05-23-phase6-walk.md` | **Create** | Track B retrospective. |
| Knowledge articles (multiple) | Modify | Per the article-mapping table — see §"Same-task rule cheat sheet" below. |

### Same-task rule cheat sheet (from CLAUDE.md article-mapping table)

When a task touches… update these articles in the same commit:
- `pipeline/stage5_link/**` → `concepts/pipeline/linking.md` **and** `concepts/data-model/knowledge-graph.md` **and** `concepts/runtime/configuration.md`
- `pipeline/schemas/*.sql` → `concepts/data-model/knowledge-graph.md`
- `pipeline/cli.py` → `concepts/runtime/cli.md`
- `pipeline/stage3_extract.py` → `concepts/pipeline/extraction.md`
- `tests/**/*.py` → `concepts/verification/testing.md`
- Any commit also append a line to `knowledge/log.md`.

If a commit is genuinely doc-irrelevant: commit body must say `no knowledge impact: <reason>`.

---

## Track A — Reject-memory

### Task A1: Schema migration — add `rejected_merges` table

**Files:**
- Modify: `pipeline/schemas/canonical_schema.sql` — append after the `merge_candidates` block (around line 363)
- Test: `tests/unit/test_canonical_schema.py` — append a small assertion

- [ ] **Step 1: Write a failing schema test**

Add to `tests/unit/test_canonical_schema.py` (find a `def test_<schema thing>` and append a sibling):

```python
def test_rejected_merges_table_exists() -> None:
    """Phase 6: rejected_merges is part of the canonical schema."""
    import sqlite3
    from pipeline.db import apply_schema
    from pipeline.schemas import CANONICAL_SCHEMA

    conn = sqlite3.connect(":memory:")
    apply_schema(conn, CANONICAL_SCHEMA)
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='rejected_merges'"
    ).fetchone()
    assert row is not None, "rejected_merges table missing from schema"
    ddl = row[0]
    assert "canonical_id" in ddl
    assert "candidate_fingerprint" in ddl
    assert "PRIMARY KEY" in ddl

    idx = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND name='idx_rejected_merges_fingerprint'"
    ).fetchone()
    assert idx is not None, "fingerprint index missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_canonical_schema.py::test_rejected_merges_table_exists -v`
Expected: FAIL with `assert None is not None` (table doesn't exist yet).

- [ ] **Step 3: Add the table to canonical_schema.sql**

Open `pipeline/schemas/canonical_schema.sql`. After the `CREATE TABLE IF NOT EXISTS merge_candidates (...)` block ending around line 363, insert:

```sql
-- Phase 6: persist curator rejections so the linker never re-flags the same pair.
-- canonical_id  → persons.id (the survivor in the rejected pair).
-- candidate_fingerprint → stable 16-hex hash of (name, sorted(set(variants))),
--                         computed at reject time from whichever table candidate A
--                         lives in (candidate_persons or persons, per Phase 5.1).
-- audit_log_id  → linked audit row (FK is soft; audit_log.id is TEXT).
CREATE TABLE IF NOT EXISTS rejected_merges (
    canonical_id          TEXT NOT NULL REFERENCES persons(id),
    candidate_fingerprint TEXT NOT NULL,
    rejected_at           TEXT NOT NULL,
    audit_log_id          TEXT REFERENCES audit_log(id),
    PRIMARY KEY (canonical_id, candidate_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_rejected_merges_fingerprint
    ON rejected_merges (candidate_fingerprint);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_canonical_schema.py::test_rejected_merges_table_exists -v`
Expected: PASS.

- [ ] **Step 5: Run the full canonical-schema test file**

Run: `uv run pytest tests/unit/test_canonical_schema.py -v`
Expected: all green (existing tests unaffected).

- [ ] **Step 6: Commit**

Touch the article required by the article-mapping table.

Edit `knowledge/concepts/data-model/knowledge-graph.md`: add a short section (~80 words) titled `### rejected_merges` describing the table's purpose, PK, and that the fingerprint is derived from candidate-side data only. Status field stays as-is unless it was `thin` — bump to `mature` if you grow the article significantly.

Append one line to `knowledge/log.md` under today's date: `- Phase 6 Task A1: added rejected_merges table for curator reject-memory.`

```bash
git add pipeline/schemas/canonical_schema.sql tests/unit/test_canonical_schema.py \
        knowledge/concepts/data-model/knowledge-graph.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(schema): add rejected_merges table (Phase 6 Track A)

Persists curator rejections so the linker can filter previously-rejected
(canonical_id, candidate_fingerprint) pairs on future runs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A2: Pure fingerprint helper

**Files:**
- Create: `pipeline/stage5_link/fingerprint.py`
- Create: `tests/unit/test_fingerprint.py`
- Modify: `pipeline/stage5_link/__init__.py` (re-export)

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/test_fingerprint.py`:

```python
"""Unit tests for the candidate-person fingerprint helper.

The fingerprint is the stability key for reject-memory: rejecting a pair
should remain effective even after re-extraction perturbs variant order or
duplicates entries. Genuinely new evidence (a new variant) should change
the fingerprint so the rejection no longer applies.
"""

from __future__ import annotations

from pipeline.stage5_link.fingerprint import candidate_fingerprint


def test_determinism() -> None:
    assert candidate_fingerprint("申侯", ["申侯", "申伯"]) == \
           candidate_fingerprint("申侯", ["申侯", "申伯"])


def test_length_and_charset() -> None:
    fp = candidate_fingerprint("申侯", ["申侯"])
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_variant_order_does_not_matter() -> None:
    a = candidate_fingerprint("褒姒", ["褒姒", "褒妃", "褒娰"])
    b = candidate_fingerprint("褒姒", ["褒娰", "褒姒", "褒妃"])
    assert a == b


def test_duplicate_variants_dont_matter() -> None:
    a = candidate_fingerprint("申侯", ["申侯", "申伯"])
    b = candidate_fingerprint("申侯", ["申侯", "申伯", "申伯", "申侯"])
    assert a == b


def test_new_variant_changes_fingerprint() -> None:
    a = candidate_fingerprint("申侯", ["申侯", "申伯"])
    b = candidate_fingerprint("申侯", ["申侯", "申伯", "申国君"])
    assert a != b


def test_name_change_changes_fingerprint() -> None:
    a = candidate_fingerprint("申侯", ["申侯", "申伯"])
    b = candidate_fingerprint("申伯", ["申侯", "申伯"])
    assert a != b


def test_empty_variants_is_valid() -> None:
    fp = candidate_fingerprint("申侯", [])
    assert len(fp) == 16
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_fingerprint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.stage5_link.fingerprint'`.

- [ ] **Step 3: Implement the helper**

Create `pipeline/stage5_link/fingerprint.py`:

```python
"""Stable identity hash for a candidate person across re-extractions.

The fingerprint is the key reject-memory uses to recognize the same
candidate even after a re-link or re-extraction run. It is computed from
candidate-side data only — no canonical-side dependency — so it remains
stable across canonical-side merges performed later.

Properties:
  - Deterministic given (name, variants).
  - Order-insensitive and dedup-insensitive over variants.
  - Changes when the name changes or a new variant is added (genuine new
    evidence; re-flagging is intentional).

See concepts/pipeline/linking.md for the role this plays in the linker
filter, and the Phase 6 spec §3.2 for trade-offs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable


def candidate_fingerprint(name: str, variants: Iterable[str]) -> str:
    """Compute a 16-hex SHA-1 fingerprint over (name, sorted(set(variants)))."""
    normalized = sorted(set(variants))
    payload = json.dumps({"name": name, "variants": normalized}, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_fingerprint.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Re-export from the package**

Read `pipeline/stage5_link/__init__.py`. Append:

```python
from pipeline.stage5_link.fingerprint import candidate_fingerprint  # noqa: E402,F401
```

(The `noqa` markers are because the file already has imports; place this at the end and adjust if the file has its own pattern.)

- [ ] **Step 6: Run pytest broadly**

Run: `uv run pytest -q`
Expected: 265 prior + 7 new + 1 schema test = 273 passed (or thereabouts; existing count is fine if no regressions).

- [ ] **Step 7: Commit**

Update `knowledge/concepts/pipeline/linking.md`: add a short subsection (`### Reject-memory fingerprint`) describing what the fingerprint covers, why order/dedup are normalized, and the new-variant→new-fingerprint behavior (~120 words).

Per the three-article rule, also touch `concepts/data-model/knowledge-graph.md` and `concepts/runtime/configuration.md` — even just one line noting the fingerprint helper exists is enough to satisfy drift-check.

Append to `knowledge/log.md`: `- Phase 6 Task A2: added candidate_fingerprint helper.`

```bash
git add pipeline/stage5_link/fingerprint.py pipeline/stage5_link/__init__.py \
        tests/unit/test_fingerprint.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/concepts/data-model/knowledge-graph.md \
        knowledge/concepts/runtime/configuration.md \
        knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage5): add candidate_fingerprint helper (Phase 6 Track A)

Pure function over (name, sorted(set(variants))) → 16-hex SHA-1. Stability
key for reject-memory; order- and dedup-insensitive; sensitive to new
evidence (new variant or different name).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A3: Extend `reject_merge` to write `rejected_merges`

**Files:**
- Modify: `pipeline/stage5_link/merge.py` — `reject_merge` at line 492
- Create: `tests/unit/test_reject_memory.py`

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/test_reject_memory.py`:

```python
"""Unit tests for reject_merge's Phase 6 rejected_merges side effect.

Covers:
  - When candidate A is in candidate_persons (the typical Phase 5.1 case),
    reject_merge writes a rejected_merges row with the correct fingerprint
    and audit_log_id linkage inside a single transaction.
  - Second rejection of the same (canonical_id, fingerprint) is idempotent
    (INSERT OR IGNORE).
  - When candidate A is in persons (escape-hatch case from Phase 5.1),
    variants come from person_variants and the row still writes.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from pipeline.db import apply_schema
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage5_link.fingerprint import candidate_fingerprint
from pipeline.stage5_link.merge import reject_merge


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn, CANONICAL_SCHEMA)
    return conn


def _seed_canonical_b(conn: sqlite3.Connection, person_id: str = "p:survivor") -> str:
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES (?, '宣王', 0.95, 'auto')",
        (person_id,),
    )
    return person_id


def _seed_candidate_a_in_candidate_persons(
    conn: sqlite3.Connection,
    cand_id: str = "cp:申侯-run1",
    name: str = "申侯",
    variants: list[str] | None = None,
) -> str:
    if variants is None:
        variants = ["申侯", "申伯"]
    conn.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, variants_json, confidence, pipeline_run_id, "
        " chunk_id, quote) "
        "VALUES (?, ?, ?, 0.7, 'run:test', 'chk:test', '...')",
        (cand_id, name, json.dumps([{"variant": v} for v in variants])),
    )
    return cand_id


def _seed_open_mc(
    conn: sqlite3.Connection,
    *,
    mc_id: str = "mc:test1",
    cand_a: str,
    cand_b: str,
) -> str:
    conn.execute(
        "INSERT INTO merge_candidates "
        "(id, kind, candidate_a_id, candidate_b_id, score, status) "
        "VALUES (?, 'person', ?, ?, 0.6, 'open')",
        (mc_id, cand_a, cand_b),
    )
    return mc_id


def test_reject_writes_rejected_merges_row() -> None:
    conn = _fresh_db()
    canonical_id = _seed_canonical_b(conn)
    cand_id = _seed_candidate_a_in_candidate_persons(conn)
    mc_id = _seed_open_mc(conn, cand_a=cand_id, cand_b=canonical_id)
    conn.commit()

    reject_merge(conn, mc_id, note="not the same person")

    rows = conn.execute(
        "SELECT canonical_id, candidate_fingerprint, audit_log_id "
        "FROM rejected_merges"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["canonical_id"] == canonical_id
    expected_fp = candidate_fingerprint("申侯", ["申侯", "申伯"])
    assert row["candidate_fingerprint"] == expected_fp
    assert row["audit_log_id"] is not None
    # audit_log_id must reference a real audit row
    audit = conn.execute(
        "SELECT change_kind FROM audit_log WHERE id = ?", (row["audit_log_id"],)
    ).fetchone()
    assert audit is not None
    assert audit["change_kind"] == "merge_rejected"


def test_reject_is_idempotent_on_duplicate() -> None:
    conn = _fresh_db()
    canonical_id = _seed_canonical_b(conn)
    cand_id = _seed_candidate_a_in_candidate_persons(conn)
    mc_id1 = _seed_open_mc(conn, mc_id="mc:1", cand_a=cand_id, cand_b=canonical_id)
    mc_id2 = _seed_open_mc(conn, mc_id="mc:2", cand_a=cand_id, cand_b=canonical_id)
    conn.commit()

    reject_merge(conn, mc_id1)
    reject_merge(conn, mc_id2)

    count = conn.execute("SELECT COUNT(*) FROM rejected_merges").fetchone()[0]
    assert count == 1  # second insert hit INSERT OR IGNORE


def test_reject_from_persons_side_candidate_a() -> None:
    """Phase 5.1 escape-hatch case: candidate A lives in persons."""
    conn = _fresh_db()
    # A and B both in persons (the rare case)
    canonical_id = _seed_canonical_b(conn, person_id="p:B")
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES ('p:A', '申侯', 0.85, 'auto')"
    )
    conn.execute(
        "INSERT INTO person_variants (person_id, variant, provenance) "
        "VALUES ('p:A', '申侯', 'auto'), ('p:A', '申伯', 'auto')"
    )
    mc_id = _seed_open_mc(conn, cand_a="p:A", cand_b=canonical_id)
    conn.commit()

    reject_merge(conn, mc_id)

    row = conn.execute("SELECT canonical_id, candidate_fingerprint FROM rejected_merges").fetchone()
    assert row is not None
    # In the persons-side case, the spec (§3.3 step 3) says "treat A's id as
    # the canonical_id" — the rejected pair is "don't merge B into A".
    assert row["canonical_id"] == "p:A"
    expected_fp = candidate_fingerprint("申侯", ["申侯", "申伯"])
    assert row["candidate_fingerprint"] == expected_fp
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_reject_memory.py -v`
Expected: 3 FAIL — `rejected_merges` table has zero rows (current `reject_merge` doesn't touch it).

- [ ] **Step 3: Extend `reject_merge`**

Open `pipeline/stage5_link/merge.py`. Find `reject_merge` (line 492). Replace the function body with the version below. **Show the full updated function:**

```python
def reject_merge(
    conn: sqlite3.Connection,
    mc_id: str,
    *,
    note: str | None = None,
) -> RejectResult:
    """Mark a merge_candidates row as rejected and persist a rejected_merges row.

    Phase 6: the rejected_merges row is the linker's filter against re-flagging.
    Candidate A may live in either candidate_persons (typical) or persons
    (escape-hatch case from Phase 5.1) — both paths are handled here.
    """
    mc_row = conn.execute(
        "SELECT status, candidate_a_id, candidate_b_id FROM merge_candidates WHERE id = ?",
        (mc_id,),
    ).fetchone()
    if mc_row is None:
        raise MergeError(f"no merge_candidates row with id={mc_id!r}")
    if mc_row["status"] != "open":
        raise StaleMergeCandidateError(f"merge_candidates {mc_id!r} status is {mc_row['status']!r}")

    cand_a_id = mc_row["candidate_a_id"]
    cand_b_id = mc_row["candidate_b_id"]

    # Phase 5.1 dual-table detection: candidate A can be in either table.
    name, variants, canonical_id = _load_reject_payload(conn, cand_a_id, cand_b_id)
    fingerprint = candidate_fingerprint(name, variants)

    audit_id = _new_audit_id()
    now = _now_iso()

    conn.execute(
        "UPDATE merge_candidates SET status = 'rejected', resolved_at = ? WHERE id = ?",
        (now, mc_id),
    )
    conn.execute(
        "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
        "before_json, after_json, actor, at) "
        "VALUES (?, 'merge_candidate', ?, NULL, 'merge_rejected', '{}', ?, 'curator', ?)",
        (
            audit_id,
            mc_id,
            json.dumps({"note": note, "fingerprint": fingerprint}, ensure_ascii=False),
            now,
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO rejected_merges "
        "(canonical_id, candidate_fingerprint, rejected_at, audit_log_id) "
        "VALUES (?, ?, ?, ?)",
        (canonical_id, fingerprint, now, audit_id),
    )
    return RejectResult(mc_id=mc_id, note=note)


def _load_reject_payload(
    conn: sqlite3.Connection, cand_a_id: str, cand_b_id: str
) -> tuple[str, list[str], str]:
    """Return (name, variants, canonical_id_for_rejected_merges) for reject_merge.

    Phase 5.1 dual-table reality:
      - Typical: A in candidate_persons; B in persons.
        → name from candidate_persons.canonical_name
        → variants from candidate_persons.variants_json
        → canonical_id = B (persons.id)
      - Escape-hatch: A in persons; B in persons.
        → name from persons.canonical_name
        → variants from person_variants
        → canonical_id = A (the rejected pair means "don't merge B into A")
    """
    cp = conn.execute(
        "SELECT canonical_name, variants_json FROM candidate_persons WHERE id = ?",
        (cand_a_id,),
    ).fetchone()
    if cp is not None:
        raw = cp["variants_json"]
        variants: list[str] = []
        if raw:
            parsed = json.loads(raw)
            variants = [v["variant"] for v in parsed if isinstance(v, dict) and "variant" in v]
        return cp["canonical_name"], variants, cand_b_id

    p = conn.execute(
        "SELECT canonical_name FROM persons WHERE id = ?", (cand_a_id,)
    ).fetchone()
    if p is None:
        raise MergeError(
            f"candidate_a_id {cand_a_id!r} not found in candidate_persons or persons"
        )
    variant_rows = conn.execute(
        "SELECT variant FROM person_variants WHERE person_id = ?", (cand_a_id,)
    ).fetchall()
    return p["canonical_name"], [r["variant"] for r in variant_rows], cand_a_id
```

Also add the import at the top of `merge.py` (after the existing `from datetime import …` lines):

```python
from pipeline.stage5_link.fingerprint import candidate_fingerprint
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_reject_memory.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run the wider merge suite to confirm no regression**

Run: `uv run pytest tests/unit/test_merge.py tests/integration/test_curator_smoke.py -v` (the curator-smoke test exercises reject_merge against the live DB copy).

If `test_curator_smoke.py` fails with a schema error about `rejected_merges`, the live-DB migration helper (`_migrate_audit_log_check`) needs a companion that runs `apply_schema()` on the copy. **Inspect `tests/integration/test_curator_smoke.py` lines 39-80** to see the migration pattern; add a new helper alongside it:

```python
def _migrate_rejected_merges(db_path: Path) -> None:
    """Add the Phase 6 rejected_merges table if missing.

    Idempotent — CREATE TABLE IF NOT EXISTS plus the matching index.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rejected_merges (
                canonical_id          TEXT NOT NULL REFERENCES persons(id),
                candidate_fingerprint TEXT NOT NULL,
                rejected_at           TEXT NOT NULL,
                audit_log_id          TEXT REFERENCES audit_log(id),
                PRIMARY KEY (canonical_id, candidate_fingerprint)
            );
            CREATE INDEX IF NOT EXISTS idx_rejected_merges_fingerprint
                ON rejected_merges (candidate_fingerprint);
            """
        )
        conn.commit()
    finally:
        conn.close()
```

Call it from wherever `_migrate_audit_log_check` is called (look for the call site — likely a session-scoped fixture).

- [ ] **Step 6: Confirm tests pass**

Run: `uv run pytest tests/integration/test_curator_smoke.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

Three-article touch required (`pipeline/stage5_link/**`): update `concepts/pipeline/linking.md` (extend the merge-actions section with the rejected_merges write), `concepts/data-model/knowledge-graph.md` (note that reject also writes a rejected_merges row), `concepts/runtime/configuration.md` (no config change — add a one-line note so drift-check passes).

Append to `knowledge/log.md`: `- Phase 6 Task A3: reject_merge writes rejected_merges; dual-table candidate-A handled.`

```bash
git add pipeline/stage5_link/merge.py tests/unit/test_reject_memory.py \
        tests/integration/test_curator_smoke.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/concepts/data-model/knowledge-graph.md \
        knowledge/concepts/runtime/configuration.md \
        knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage5): reject_merge persists rejected_merges row (Phase 6 Track A)

Inside the existing transaction reject_merge now writes a rejected_merges
row keyed on (canonical_id, candidate_fingerprint). Handles both
candidate-A locations from Phase 5.1: candidate_persons (typical) and
persons (escape-hatch).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A4: Linker filters against `rejected_merges`

**Files:**
- Modify: `pipeline/stage5_link/linker.py` — `link_run` at line 58
- Create: `tests/integration/test_link_rejection_loop.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_link_rejection_loop.py`:

```python
"""Integration test: linker honors rejected_merges on subsequent runs.

Seeds a candidate that scores into the queue threshold, runs the linker
(yields a merge_candidates row), rejects it (writes rejected_merges),
runs the linker again (must NOT re-emit the rejected pair). Also
exercises the --ignore-rejections override.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from pipeline.db import apply_schema
from pipeline.schemas import CANONICAL_SCHEMA
from pipeline.stage5_link import link_run
from pipeline.stage5_link.merge import reject_merge


def _seed_minimal_world(conn: sqlite3.Connection) -> tuple[str, str]:
    """Return (canonical_persons_id, candidate_persons_id) plumbed to score into queue range."""
    canonical_id = "p:canonical-A"
    conn.execute(
        "INSERT INTO persons (id, canonical_name, confidence, provenance) "
        "VALUES (?, '申侯', 0.95, 'auto')",
        (canonical_id,),
    )
    conn.execute(
        "INSERT INTO person_variants (person_id, variant, provenance) "
        "VALUES (?, '申侯', 'auto'), (?, '申伯', 'auto')",
        (canonical_id, canonical_id),
    )
    cand_id = "cp:申侯-runX"
    run_id = "run:test-link-rejection"
    conn.execute(
        "INSERT INTO candidate_persons "
        "(id, canonical_name, variants_json, confidence, pipeline_run_id, "
        " chunk_id, quote) "
        "VALUES (?, '申侯', ?, 0.7, ?, 'chk:test', '...')",
        (cand_id, json.dumps([{"variant": "申侯"}, {"variant": "申伯"}]), run_id),
    )
    conn.commit()
    return canonical_id, run_id


def _open_mc_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM merge_candidates WHERE status = 'open'"
    ).fetchone()[0]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c, CANONICAL_SCHEMA)
    yield c
    c.close()


def test_link_then_reject_then_link_does_not_reflag(conn: sqlite3.Connection) -> None:
    canonical_id, run_id = _seed_minimal_world(conn)

    stats1 = link_run(conn, run_id)
    assert stats1["queued"] == 1
    assert _open_mc_count(conn) == 1

    mc_id = conn.execute(
        "SELECT id FROM merge_candidates WHERE status = 'open'"
    ).fetchone()["id"]
    reject_merge(conn, mc_id, note="test rejection")
    conn.commit()

    # Re-link the same run. The linker should now skip the previously-rejected pair.
    stats2 = link_run(conn, run_id)
    assert stats2["queued"] == 0, "linker re-flagged a rejected pair"
    assert stats2.get("rejected_filter_skipped", 0) >= 1


def test_ignore_rejections_bypasses_filter(conn: sqlite3.Connection) -> None:
    canonical_id, run_id = _seed_minimal_world(conn)

    link_run(conn, run_id)
    mc_id = conn.execute(
        "SELECT id FROM merge_candidates WHERE status = 'open'"
    ).fetchone()["id"]
    reject_merge(conn, mc_id)
    conn.commit()

    # With ignore_rejections=True the filter is bypassed and the pair is re-emitted.
    stats = link_run(conn, run_id, ignore_rejections=True)
    assert stats["queued"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_link_rejection_loop.py -v`
Expected: FAIL — both tests fail because `link_run` doesn't accept `ignore_rejections` and doesn't filter.

- [ ] **Step 3: Add filter to `link_run`**

Open `pipeline/stage5_link/linker.py`. Find `link_run` at line 58. Modify the signature and body. Show the full updated `link_run`:

```python
def link_run(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    *,
    ignore_rejections: bool = False,
) -> dict[str, int]:
    """For each candidate_persons row in the run, find plausible match targets and
    dispatch by score:
      - score >= LINKER_AUTO_MERGE_THRESHOLD  → write match_target_id + audit_log
      - LINKER_QUEUE_THRESHOLD <= score < auto → write merge_candidates row
      - score < LINKER_QUEUE_THRESHOLD         → no action

    Phase 6: pairs previously dispositioned as rejected (rejected_merges) are
    skipped at the queue stage unless ignore_rejections=True.

    Returns stats: {candidates_processed, auto_merges, queued, skipped,
                    rejected_filter_skipped}.
    """
    from pipeline.stage5_link.fingerprint import candidate_fingerprint

    _denormalize_variants(conn, pipeline_run_id)

    stats: dict[str, int] = {
        "candidates_processed": 0,
        "auto_merges": 0,
        "queued": 0,
        "skipped": 0,
        "rejected_filter_skipped": 0,
    }

    rejected: set[tuple[str, str]] = set()
    if not ignore_rejections:
        rejected = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT canonical_id, candidate_fingerprint FROM rejected_merges"
            )
        }

    candidate_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM candidate_persons WHERE pipeline_run_id = ? ORDER BY id",
            (pipeline_run_id,),
        )
    ]

    already_matched: set[str] = set()

    for cand_id in candidate_ids:
        stats["candidates_processed"] += 1

        if cand_id in already_matched:
            stats["skipped"] += 1
            continue

        me = _load_candidate(conn, cand_id)
        if me is None:
            stats["skipped"] += 1
            continue

        pool = candidate_pool(conn, cand_id, pipeline_run_id)
        if not pool:
            stats["skipped"] += 1
            continue

        best_target: dict[str, Any] | None = None
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
            conn.execute(
                "UPDATE candidate_persons SET match_target_id = ? WHERE id = ?",
                (best_target["target_id"], cand_id),
            )
            conn.execute(
                "INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, "
                "before_json, after_json, actor, at, pipeline_run_id) "
                "VALUES (?, 'candidate_persons', ?, 'match_target_id', 'set', "
                "?, ?, 'link@v1', datetime('now'), ?)",
                (
                    f"audit:{uuid.uuid4()}",
                    cand_id,
                    json.dumps({"value": None}),
                    json.dumps(
                        {
                            "value": best_target["target_id"],
                            "score": best_score,
                            "features": best_features,
                        },
                        ensure_ascii=False,
                    ),
                    pipeline_run_id,
                ),
            )
            stats["auto_merges"] += 1
            if best_target.get("target_kind") == "candidate":
                already_matched.add(best_target["target_id"])
        else:
            # Queue case — apply Phase 6 reject-memory filter.
            if best_target.get("target_kind") == "canonical":
                fp = candidate_fingerprint(
                    me["canonical_name"],
                    [v["variant"] for v in (me.get("variants") or [])],
                )
                if (best_target["target_id"], fp) in rejected:
                    stats["rejected_filter_skipped"] += 1
                    continue

            conn.execute(
                "INSERT INTO merge_candidates "
                "(id, kind, candidate_a_id, candidate_b_id, score, surface_features_json, status) "
                "VALUES (?, 'person', ?, ?, ?, ?, 'open')",
                (
                    f"mc:{uuid.uuid4()}",
                    cand_id,
                    best_target["target_id"],
                    best_score,
                    json.dumps(
                        {"features": best_features, "score": best_score},
                        ensure_ascii=False,
                    ),
                ),
            )
            stats["queued"] += 1

    conn.commit()
    return stats
```

**Important:** the spec scopes the filter to canonical-side targets only — same-run candidate-vs-candidate pre-link pairs are not filtered. This is intentional (rejected_merges.canonical_id FK is to persons). The `if best_target.get("target_kind") == "canonical"` guard encodes this. If `_load_candidate` returns `me` without a top-level `variants` key, fall back gracefully (the `me.get("variants") or []` handles it).

**Inspect `_load_candidate`** (likely in `linker.py` or a sibling) to confirm the shape of `me`. If `me["canonical_name"]` is not exposed under that exact key, read the file and adapt — match the field name used by `me["…"]` elsewhere in the function. The key requirement is reading the same `(name, variants)` that `reject_merge` hashed.

- [ ] **Step 4: Run the new integration test**

Run: `uv run pytest tests/integration/test_link_rejection_loop.py -v`
Expected: both PASS.

- [ ] **Step 5: Run the wider stage-5 suite**

Run: `uv run pytest tests/integration/test_link_ch01.py tests/integration/test_link_regression.py -v`
Expected: PASS (no regression on chapter-1 linker behavior — those tests pre-date Phase 6 and ran with no `rejected_merges` rows; filter is a no-op when the table is empty).

- [ ] **Step 6: Commit**

Three-article touch: `concepts/pipeline/linking.md` (document the filter + `ignore_rejections` parameter), `concepts/data-model/knowledge-graph.md` (one-line cross-link), `concepts/runtime/configuration.md` (one-line note that the linker now reads rejected_merges).

Append to `knowledge/log.md`: `- Phase 6 Task A4: linker filters rejected pairs; ignore_rejections kwarg added.`

```bash
git add pipeline/stage5_link/linker.py tests/integration/test_link_rejection_loop.py \
        knowledge/concepts/pipeline/linking.md \
        knowledge/concepts/data-model/knowledge-graph.md \
        knowledge/concepts/runtime/configuration.md \
        knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(stage5): linker filters rejected (canonical_id, fingerprint) pairs (Phase 6 Track A)

link_run loads the rejected_merges set once per run and skips the queue
emission for previously-rejected canonical-side targets. Adds
ignore_rejections kwarg for the "I changed my mind" path. Filter is
scoped to canonical targets only (same-run candidate-candidate pairs
remain unfiltered).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A5: CLI `--ignore-rejections` flag

**Files:**
- Modify: `pipeline/cli.py` — `link` at line 696
- Test: extend `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing CLI test**

Append to `tests/unit/test_cli.py`:

```python
def test_link_accepts_ignore_rejections_flag(tmp_path, monkeypatch) -> None:
    """Phase 6: link verb exposes --ignore-rejections (default False)."""
    from typer.testing import CliRunner
    from pipeline.cli import app

    runner = CliRunner()
    # --help should mention the new flag
    result = runner.invoke(app, ["link", "--help"])
    assert result.exit_code == 0
    assert "--ignore-rejections" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::test_link_accepts_ignore_rejections_flag -v`
Expected: FAIL — string not present.

- [ ] **Step 3: Add the flag**

Open `pipeline/cli.py` line 696. Replace the `link` function with:

```python
@app.command()
def link(
    pipeline_run_id: str = typer.Argument(
        ..., help="Pipeline run id to link (matches candidate_persons.pipeline_run_id)."
    ),
    ignore_rejections: bool = typer.Option(
        False,
        "--ignore-rejections",
        help=(
            "Re-emit pairs previously dispositioned as rejected. Use when "
            "the curator wants to revisit prior rejections (Phase 6)."
        ),
    ),
    repo_root: Path = typer.Option(Path.cwd(), "--repo-root", exists=True, file_okay=False),
) -> None:
    """Run Stage 5 (linker) for the given pipeline_run_id.

    Walks candidate_persons, scores against the canonical + same-run pool, and
    dispatches by threshold: auto-merge writes match_target_id + audit_log;
    mid-score writes a merge_candidates row; low-score skips. See
    concepts/pipeline/linking.md for the full picture.

    Phase 6: by default, pairs previously rejected by the curator (rejected_merges
    table) are filtered out at the queue stage. --ignore-rejections bypasses
    that filter.
    """
    from pipeline.stage5_link import link_run

    canonical = open_canonical_db(repo_root / "data" / "changjuan.sqlite")
    stats = link_run(canonical, pipeline_run_id, ignore_rejections=ignore_rejections)
    typer.echo(
        f"link {pipeline_run_id}: processed={stats['candidates_processed']} "
        f"auto-merged={stats['auto_merges']} queued={stats['queued']} "
        f"skipped={stats['skipped']} rejected-filter-skipped={stats.get('rejected_filter_skipped', 0)}"
        + (" (ignore-rejections=ON)" if ignore_rejections else "")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Update `concepts/runtime/cli.md` — add a `link` row entry (or expand the existing one) documenting `--ignore-rejections`.

Append to `knowledge/log.md`: `- Phase 6 Task A5: changjuan link --ignore-rejections flag.`

```bash
git add pipeline/cli.py tests/unit/test_cli.py \
        knowledge/concepts/runtime/cli.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
feat(cli): changjuan link --ignore-rejections flag (Phase 6 Track A)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Track C — person_relations bug fix

### Task C1: Fix the field-name bug + add backfill test

**Files:**
- Modify: `pipeline/stage3_extract.py:377`
- Create: `tests/integration/test_person_relations_backfill.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_person_relations_backfill.py`:

```python
"""End-to-end: ch01 extraction YAML produces non-empty candidate_person_relations.

Phase 6 Track C: the stage3 loader previously read r["relation_kind"], which the
extractor does not emit. The actual field is kind_detail. After the fix, replaying
the extraction populates candidate_person_relations with real kinds (which stage 7
can then promote).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import open_canonical_db, open_corpus_db
from pipeline.stage3_extract import load_extraction

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTION = REPO_ROOT / "data" / "extractions" / "ch01" / "extract-v2.yaml"
CORPUS = REPO_ROOT / "data" / "corpus.sqlite"


@pytest.mark.skipif(
    not (EXTRACTION.exists() and CORPUS.exists()),
    reason="ch01 extraction YAML or corpus.sqlite missing",
)
def test_kind_detail_populates_candidate_person_relations(tmp_path) -> None:
    canonical_db = tmp_path / "canonical.sqlite"
    canonical = open_canonical_db(canonical_db)
    corpus = open_corpus_db(CORPUS)
    run_id = "run:test-c1"
    try:
        load_extraction(
            canonical,
            corpus_conn=corpus,
            chapter_num=1,
            extraction_file=EXTRACTION,
            prompt_version="v2",
            pipeline_run_id=run_id,
        )
        canonical.commit()

        rows = canonical.execute(
            "SELECT kind FROM candidate_person_relations WHERE pipeline_run_id = ?",
            (run_id,),
        ).fetchall()
    finally:
        canonical.close()
        corpus.close()

    assert rows, "no candidate_person_relations rows produced"
    kinds = {r[0] for r in rows}
    expected_subset = {"parent", "ally", "mentor", "spouse", "killed_by"}
    assert kinds & expected_subset, f"expected one of {expected_subset}; got {kinds}"
    assert "" not in kinds, "empty kind leaked through"
```

The signature mirrors `pipeline/stage3_extract.py:111` — keyword-only after `canonical_conn`. If the file's signature has drifted since plan-writing, match the current source.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_person_relations_backfill.py -v`
Expected: FAIL — either `assert "" not in kinds` (current bug) or the kinds set is empty.

- [ ] **Step 3: Fix the bug**

Open `pipeline/stage3_extract.py` line 377. Change:

```python
r.get("relation_kind", ""),
```

to:

```python
r.get("kind_detail", ""),
```

This is the only line change in stage3_extract.py.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_person_relations_backfill.py -v`
Expected: PASS.

- [ ] **Step 5: Run the wider extract-load suite**

Run: `uv run pytest tests/unit/test_extract_load.py tests/integration/test_golden_ch01.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

Touch `knowledge/concepts/pipeline/extraction.md` — add a short subsection (`### kind_detail vs kind`) noting the extractor emits `kind_detail` for person_relation entries; the canonical CHECK constraint vocabulary uses that value as `person_relations.kind`. Also touch `knowledge/concepts/pipeline/load-and-merge.md` — note that `person_relations` is now populated.

Append to `knowledge/log.md`: `- Phase 6 Task C1: stage3 loader reads kind_detail (was relation_kind); person_relations no longer 0.`

```bash
git add pipeline/stage3_extract.py tests/integration/test_person_relations_backfill.py \
        knowledge/concepts/pipeline/extraction.md \
        knowledge/concepts/pipeline/load-and-merge.md \
        knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
fix(stage3): read kind_detail (not relation_kind) for person_relations (Phase 6 Track C)

The extractor emits kind_detail; the loader was reading a non-existent
relation_kind, dropping every person_relation to "" which stage 7
silently skipped. person_relations was at 0 rows. With this one-line
fix the candidate rows carry real kinds; stage 7 promotes them.

Backfill of the live DB happens in a separate step.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C2: Backfill the live DB

**Files:**
- Live DB at `data/changjuan.sqlite` (mutated; back it up first)

- [ ] **Step 1: Pre-backfill snapshot of live counts**

Run:

```bash
sqlite3 data/changjuan.sqlite \
  "SELECT 'person_relations', COUNT(*) FROM person_relations
   UNION ALL SELECT 'candidate_person_relations', COUNT(*) FROM candidate_person_relations
   UNION ALL SELECT 'conflicts', COUNT(*) FROM conflicts;"
```

Expected baseline: `person_relations=0`, `candidate_person_relations>0` but with `kind=""`, `conflicts=12`.

- [ ] **Step 2: Snapshot the DB**

```bash
cp data/changjuan.sqlite data/changjuan.sqlite.pre-phase6c-bak
```

The .bak gives us rollback if backfill produces unexpected results.

- [ ] **Step 3: Re-load extractions through stage 3**

The cleanest way is to re-run the existing `extract-load` CLI for each chapter (Ch.1-5), which writes into `candidate_person_relations` with the fixed loader. Then re-link, then re-load stage 7.

For each chapter 1..5, in one block:

```bash
for N in 1 2 3 4 5; do
  RUN_ID="run:phase6c-ch${N}-$(date +%s)"
  uv run changjuan extract-load \
    --chapter $N \
    --extraction-file data/extractions/ch0${N}/extract-v2.yaml \
    --prompt-version v2 \
    --pipeline-run-id "$RUN_ID"
  echo "extract-load done: $RUN_ID"
  uv run changjuan link "$RUN_ID"
  uv run changjuan load "$RUN_ID"
done
```

CLI verbs and arg shapes confirmed against `pipeline/cli.py` (`extract-load` at line 721, `link` at line 696 takes `pipeline_run_id` positional, `load` at line 70 takes `pipeline_run_id` positional). If something fails mid-loop, capture the error and stop — don't blindly continue.

- [ ] **Step 5: Verify post-backfill counts**

Run the same query as Step 1:

```bash
sqlite3 data/changjuan.sqlite \
  "SELECT 'person_relations', COUNT(*) FROM person_relations
   UNION ALL SELECT 'candidate_person_relations', COUNT(*) FROM candidate_person_relations
   UNION ALL SELECT 'conflicts', COUNT(*) FROM conflicts;"
```

Expected: `person_relations > 0` (likely several dozen across Ch.1-5). `conflicts` may be ≥ 12 (Phase 7 will triage; Phase 6 just notes the new count).

- [ ] **Step 6: Sanity-spotcheck a few rows**

```bash
sqlite3 -header data/changjuan.sqlite \
  "SELECT from_person_id, to_person_id, kind FROM person_relations LIMIT 10;"
```

Expected: each row has a non-empty kind in the canonical set (`parent`, `child`, `spouse`, `sibling`, `mentor`, `ruler`, `minister`, `ally`, `rival`, `killed_by`, `clan_member`).

- [ ] **Step 7: Commit the backfilled DB metadata change**

The live DB itself is gitignored. The commit captures the operational record: append a paragraph to `knowledge/log.md`:

```
- Phase 6 Task C2: backfilled person_relations from cached Ch.1-5 YAMLs.
  Counts before → after:
  person_relations: 0 → <N>
  candidate_person_relations kind != '': 0 → <M>
  conflicts: 12 → <K>
```

```bash
git add knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
chore(data): backfill person_relations from cached extractions (Phase 6 Track C)

no knowledge impact: operational log entry only; behavior already documented in Task C1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Track B — Walk the 31

> Track B is curator work, not coding work. The subagent-driven runner should pause here and hand control back to the human curator. The runner's role is: prepare the snapshot, capture the friction notes, write the retro.

### Task B1: Pre-walk snapshot

- [ ] **Step 1: Snapshot the DB**

```bash
cp data/changjuan.sqlite data/changjuan.sqlite.phase6-walk-bak
ls -la data/changjuan.sqlite*
```

Expected: snapshot file exists alongside the live DB.

- [ ] **Step 2: Baseline counts**

```bash
sqlite3 data/changjuan.sqlite \
  "SELECT status, COUNT(*) FROM merge_candidates GROUP BY status;"
```

Expected at walk start: `open=31` (or whatever the current count is after any A4 test mutations — should still be 31 if A4 only used `:memory:`).

- [ ] **Step 3: Open knowledge/log.md and start the walk entry**

Append:

```
- Phase 6 Track B walk started <date> <time>. Baseline: open=31, merged=0, rejected=0.
```

(Subsequent step in Task B3 writes the closing entry.)

### Task B2: Curator walks the 31 (human-driven)

> **No automation here.** The user runs the UI and disposes of each candidate. The agent's job during this period is: (a) sit ready to fix friction items within the ≤3 budget; (b) keep a running friction list in `docs/superpowers/retros/2026-05-23-phase6-walk.md` as observations come in.

- [ ] **Step 1: Launch the curator UI**

```bash
uv run changjuan curator
```

The user navigates to "🔗 Merge candidates" and disposes of each candidate.

- [ ] **Step 2: Maintain the friction list**

Each time the user reports an ergonomic issue, append it (with a one-line description and a "fix budget: 0/3 used" counter) to `docs/superpowers/retros/2026-05-23-phase6-walk.md` (create if not present — see Task B3 step 1 for the template).

When the user explicitly asks for a fix during the walk:
- Confirm it fits the budget (<100 LOC, no schema change, doesn't touch `merge.py` public API).
- Implement, test, commit as its own bite-sized task (TDD where the fix is testable; for pure UX tweaks, a smoke run of the page is enough).
- Decrement the budget counter.

- [ ] **Step 3: Walk-completion check**

When the user reports the walk is done, run:

```bash
sqlite3 data/changjuan.sqlite \
  "SELECT status, COUNT(*) FROM merge_candidates GROUP BY status;"
```

DoD: `open = 0`. Any remaining `open` rows are defers that must be converted to a real disposition before Phase 6 closes.

### Task B3: Retrospective

**File:**
- Create: `docs/superpowers/retros/2026-05-23-phase6-walk.md`

- [ ] **Step 1: Create the retro skeleton (do this at walk start, fill in at walk end)**

```markdown
# Phase 6 Track B — Walk the 31 Retrospective

**Walk dates:** YYYY-MM-DD — YYYY-MM-DD
**Curator:** kun.lu
**Baseline:** open=31, merged=0, rejected=0

## Disposition summary

| Disposition | Count |
|---|---|
| Accepted | _ |
| Edit-accepted | _ |
| Rejected | _ |
| Split | _ |
| Deferred (resolved before close) | _ |

## Time

- Total elapsed: _ minutes / hours
- Mean seconds per candidate: _

## What worked

- _

## Friction observed (ranked, most-painful first)

For each item: what happened, why it slowed the walk, whether fixed in-budget or deferred.

1. **<friction item title>** — <description>. *Status:* fixed in commit `<sha>` / deferred to Phase 7.
2. ...

## Friction-fix budget usage

| # | Fix | Commit | LOC | Budget used |
|---|---|---|---|---|
| 1 | _ | _ | _ | 1/3 |
| 2 | _ | _ | _ | 2/3 |
| 3 | _ | _ | _ | 3/3 |

## Recommended next moves (Phase 7 input)

- _
```

- [ ] **Step 2: Fill in the retro at walk end**

Populate every section. Numbers come from the SQL summary; commentary comes from the running friction list and any user observations.

- [ ] **Step 3: Append closing log entry**

```
- Phase 6 Track B walk completed <date> <time>. Final: open=0, merged=<X>, rejected=<Y>, split=<Z>. Retro at docs/superpowers/retros/2026-05-23-phase6-walk.md.
```

- [ ] **Step 4: Commit the retro**

```bash
git add docs/superpowers/retros/2026-05-23-phase6-walk.md knowledge/log.md
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
docs(phase6): walk-the-31 retrospective (Phase 6 Track B)

no knowledge impact: retrospective only; any friction fixes were
committed separately as they were made.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Cross-cutting

### Task X1: `scripts/phase6-prep.sh`

**Files:**
- Create: `scripts/phase6-prep.sh`

- [ ] **Step 1: Create the script**

Mirror the pattern from `scripts/phase5-prep.sh`. Write:

```bash
#!/usr/bin/env bash
# Phase 6 acceptance check. Mirrors phase5-prep.sh structure.
set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
WARN=0
LOGDIR="data/logs/phase6-prep"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%Y%m%dT%H%M%S).log"
exec > >(tee "$LOG") 2>&1

section() { echo; echo "==== $* ===="; }
pass()    { echo "  ✓ PASS $*"; PASS=$((PASS+1)); }
fail()    { echo "  ✗ FAIL $*"; FAIL=$((FAIL+1)); }
warn()    { echo "  ! $*"; WARN=$((WARN+1)); }

section "1. Git tree clean"
if [[ -z "$(git status --porcelain | grep -v -E 'data/exports/|data/changjuan\.sqlite|\.claude/settings\.local\.json')" ]]; then
  pass "git status clean"
else
  warn "uncommitted changes present"
fi

section "2. Older phase-prep scripts still green"
for s in phase2-prep phase3-prep phase4-prep phase5-prep; do
  if ./scripts/${s}.sh >/dev/null 2>&1; then
    pass "${s} green"
  else
    fail "${s} failed; run ./scripts/${s}.sh for details"
  fi
done

section "3. pytest"
if uv run pytest -q >/dev/null 2>&1; then
  pass "pytest green"
else
  fail "pytest failures; run uv run pytest -q for details"
fi

section "4. rejected_merges table present"
if sqlite3 data/changjuan.sqlite ".schema rejected_merges" 2>/dev/null | grep -q "CREATE TABLE.*rejected_merges"; then
  pass "rejected_merges table present in live DB"
else
  fail "rejected_merges missing from live DB; run apply_schema or re-run extract-load to migrate"
fi

section "5. merge_candidates queue closed (Track B DoD)"
OPEN=$(sqlite3 data/changjuan.sqlite "SELECT COUNT(*) FROM merge_candidates WHERE status = 'open';" 2>/dev/null || echo "ERR")
if [[ "$OPEN" == "0" ]]; then
  pass "all merge_candidates resolved"
elif [[ "$OPEN" == "ERR" ]]; then
  fail "could not query merge_candidates"
else
  warn "merge_candidates open=${OPEN} (Track B incomplete)"
fi

section "6. person_relations populated (Track C DoD)"
PR=$(sqlite3 data/changjuan.sqlite "SELECT COUNT(*) FROM person_relations;" 2>/dev/null || echo "ERR")
if [[ "$PR" != "0" && "$PR" != "ERR" ]]; then
  pass "person_relations rows=${PR}"
else
  fail "person_relations still 0 (or query failed)"
fi

section "7. Walk retrospective present"
if [[ -f docs/superpowers/retros/2026-05-23-phase6-walk.md ]]; then
  pass "walk retro present"
else
  warn "walk retro missing (Track B not yet complete)"
fi

section "8. Drift check"
if ./scripts/drift-check >/dev/null 2>&1; then
  pass "drift-check passes"
else
  fail "drift-check failed"
fi

section "Summary"
echo "  ${PASS} passed   ${WARN} warn   ${FAIL} failed"
echo
echo "Full log: ${LOG}"
exit $FAIL
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/phase6-prep.sh
```

- [ ] **Step 3: Run it (after A and C are done; Track B may still warn at this point)**

```bash
./scripts/phase6-prep.sh
```

Expected after A+C: sections 1-4 + 6 + 8 PASS; section 5 WARN until walk done; section 7 WARN until retro written.

After B: all 8 PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/phase6-prep.sh
PATH=".venv/bin:$PATH" git commit -m "$(cat <<'EOF'
test: phase6-prep.sh acceptance check (Phase 6)

no knowledge impact: scripts/ tooling, mirrors phase5-prep.sh.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task X2: Final verification gate

- [ ] **Step 1: Run all four prior phase-prep scripts**

```bash
./scripts/phase2-prep.sh
./scripts/phase3-prep.sh
./scripts/phase4-prep.sh
./scripts/phase5-prep.sh
```

Expected: all green.

- [ ] **Step 2: Run the new phase6-prep**

```bash
./scripts/phase6-prep.sh
```

Expected: all PASS (after Tracks A, C, B and X1 are complete).

- [ ] **Step 3: Final pytest sweep**

```bash
uv run pytest -q
```

Expected: ≥ 265 + new tests, all green.

- [ ] **Step 4: Git status check**

```bash
git status
git log --oneline e91bc8e..HEAD
```

Expected: clean tree (only the gitignored noise), and the Phase 6 commits form a coherent narrative.

---

## Out of scope (Phase 7 candidates — do not implement here)

From spec §9, reproduced for the executor's discipline:
- Undo button.
- Conflicts queue UI.
- Low-confidence extractions queue UI.
- Re-extract button.
- Search box.
- Headline counter widgets.
- Coverage grid per-chapter detail view.
- Prefetch ergonomics.
- `chapter_citation_context` ±N paragraph window.
- Atomicity tests for accept/reject/split error branches.
- LLM judge for ambiguous merges.
- Linker breadth: events / places / states / relations.

If a Track B friction item *looks like* one of these, log it in the retro — do not implement.
