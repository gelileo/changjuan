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
