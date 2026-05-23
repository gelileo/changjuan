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
dirty=$(git status --porcelain | grep -v -E '^.. data/exports/|^.. data/changjuan\.sqlite|^.. \.claude/settings\.local\.json' || true)
if [[ -z "$dirty" ]]; then
  pass "git status clean (only expected untracked items)"
else
  warn "uncommitted changes present"
fi

section "2. Older phase-prep scripts still green"
for script in scripts/phase2-prep.sh scripts/phase3-prep.sh scripts/phase4-prep.sh scripts/phase5-prep.sh; do
  if bash "$script" >/dev/null 2>&1; then
    pass "$script exits 0"
  else
    fail "$script non-zero exit"
  fi
done

section "3. pytest"
if uv run pytest -q >/dev/null 2>&1; then
  pass "pytest green"
else
  fail "pytest failures; run 'uv run pytest -q' for details"
fi

section "4. rejected_merges table present in live DB"
schema_out=$(sqlite3 data/changjuan.sqlite ".schema rejected_merges" 2>&1 || true)
if echo "$schema_out" | grep -qi "CREATE TABLE.*rejected_merges"; then
  pass "rejected_merges table exists"
else
  fail "rejected_merges table not found in data/changjuan.sqlite"
fi

section "5. merge_candidates queue status"
open_count=$(sqlite3 data/changjuan.sqlite "SELECT COUNT(*) FROM merge_candidates WHERE status = 'open';" 2>&1)
if [[ $? -ne 0 || "$open_count" == *"error"* || "$open_count" == *"Error"* ]]; then
  fail "query against merge_candidates failed: $open_count"
elif [[ "$open_count" -eq 0 ]]; then
  pass "merge_candidates queue empty (Track B complete)"
else
  warn "WARN merge_candidates has $open_count open rows (Track B not yet complete)"
fi

section "6. person_relations populated"
rel_count=$(sqlite3 data/changjuan.sqlite "SELECT COUNT(*) FROM person_relations;" 2>&1)
if [[ $? -ne 0 || "$rel_count" == *"error"* || "$rel_count" == *"Error"* ]]; then
  fail "query against person_relations failed: $rel_count"
elif [[ "$rel_count" -gt 0 ]]; then
  pass "person_relations has $rel_count rows"
else
  fail "person_relations is empty (expected > 0)"
fi

section "7. Walk retrospective present"
RETRO="docs/superpowers/retros/2026-05-23-phase6-walk.md"
if [[ -f "$RETRO" ]]; then
  pass "walk retrospective found at $RETRO"
else
  warn "WARN walk retrospective missing at $RETRO (Track B not yet complete)"
fi

section "8. Drift check"
if ./scripts/drift-check >/dev/null 2>&1; then
  pass "drift-check passes"
else
  fail "drift-check failed; run './scripts/drift-check' for details"
fi

section "Summary"
echo "  $PASS passed   $WARN warn   $FAIL failed"
echo
echo "Full log: $LOG"
[[ $FAIL -eq 0 ]] || exit 1
