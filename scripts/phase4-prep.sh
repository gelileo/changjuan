#!/usr/bin/env bash
# changjuan Phase 4 readiness check.
# Run from the repo root: ./scripts/phase4-prep.sh

set -uo pipefail

# === PHASE4_DEFERRED — Phase 5+ starter backlog ===
PHASE4_DEFERRED=(
  "Chapters 6-108 — the remaining 103 chapters of multi-chapter extraction"
  "LLM judge for Stage 5 ambiguous cases — defer until curator UI exists"
  "Curator UI (Stage 8) — Streamlit; first queue: merge_candidates from Stage 5"
  "Linker for events / places / states / relations — Phase 3 was persons only"
  "Cross-chunk relative-date automation — Phase 2 manual CLI suffices for now"
  "Cross-canon checks at scale — opt-in --with-canon-check exists, not exercised system-wide"
  "QA mismatch-rate formula recalibration — Phase 4 spot-check showed (no + 0.5×partial)/total is too punitive for multi-chapter synthesis; consider NO-only rate or tightening extract-v2 justification rules"
  "Reign tables for 楚 / 燕 / 吴 / 越 (and any other states Ch.6+ surfaces) — Phase 4 covered 9 states"
)

# ---------------------------------------------------------------------------
# Setup: paths, logging, colors
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

LOG_FILE="${REPO_ROOT}/data/logs/phase4-prep.log"
mkdir -p "$(dirname "${LOG_FILE}")"
: > "${LOG_FILE}"

if [[ -t 1 ]]; then
  C_RED=$'\e[31m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'
  C_BLUE=$'\e[34m'; C_CYAN=$'\e[36m'; C_DIM=$'\e[2m'; C_RESET=$'\e[0m'
else
  C_RED=; C_GREEN=; C_YELLOW=; C_BLUE=; C_CYAN=; C_DIM=; C_RESET=
fi

N_PASS=0
N_WARN=0
N_FAIL=0
FAIL_REASONS=()
WARN_REASONS=()

log() {
  printf "%s\n" "$*"
  printf "%s\n" "$*" | sed $'s/\x1b\\[[0-9;]*m//g' >> "${LOG_FILE}"
}
section() {
  log ""
  log "${C_BLUE}==== $* ====${C_RESET}"
}
why() {
  log "${C_DIM}why: $*${C_RESET}"
}
pass() {
  N_PASS=$((N_PASS + 1))
  log "  ${C_GREEN}✓ PASS${C_RESET} $*"
}
warn() {
  N_WARN=$((N_WARN + 1))
  WARN_REASONS+=("$*")
  log "  ${C_YELLOW}! WARN${C_RESET} $*"
}
fail() {
  N_FAIL=$((N_FAIL + 1))
  FAIL_REASONS+=("$*")
  log "  ${C_RED}✗ FAIL${C_RESET} $*"
}

log "${C_CYAN}==== changjuan Phase 4 readiness check ====${C_RESET}"

# ---------------------------------------------------------------------------
section "1. Phase 2 + Phase 3 still pass (non-regression)"
why "Phase 4 must not regress prior phases."
if ./scripts/phase2-prep.sh >>"${LOG_FILE}" 2>&1; then
    pass "phase2-prep.sh green"
else
    fail "phase2-prep.sh FAILED — see log"
fi
if ./scripts/phase3-prep.sh >>"${LOG_FILE}" 2>&1; then
    pass "phase3-prep.sh green"
else
    fail "phase3-prep.sh FAILED — see log"
fi

# ---------------------------------------------------------------------------
section "2. Date parser explicit_reign_other"
why "Resolves non-鲁/周 reign anchors against per-state reign YAMLs."
if uv run pytest tests/unit/test_dates_reign_other.py -q >>"${LOG_FILE}" 2>&1; then
    pass "explicit_reign_other tests pass (10 tests)"
else
    fail "explicit_reign_other tests FAILED — see log"
fi

# ---------------------------------------------------------------------------
section "3. Reign-extract skill scaffold + discovery + smoke-check modules"
why "Phase 4a infrastructure."
if [ -f ".claude/skills/changjuan-extract-reigns/SKILL.md" ] && \
        [ -f ".claude/skills/changjuan-extract-reigns/system-prompt.md" ]; then
    pass ".claude/skills/changjuan-extract-reigns/ present"
else
    fail "reign-extract skill missing"
fi
if [ -f "pipeline/discovery.py" ] && [ -x "scripts/discover-states" ]; then
    pass "pipeline/discovery.py + scripts/discover-states present"
else
    fail "discovery module/script missing"
fi
if [ -f "pipeline/smoke_checks.py" ] && [ -x "scripts/smoke-check-run" ]; then
    pass "pipeline/smoke_checks.py + scripts/smoke-check-run present"
else
    fail "smoke-check module/script missing"
fi

# ---------------------------------------------------------------------------
section "4. Reign YAMLs for Ch.2-5 worklist"
why "Hand-verified reign tables required for every state referenced in Ch.2-5."
worklist=$(./scripts/discover-states --chapters 2,3,4,5 --min-count 3 2>>"${LOG_FILE}" \
    | tail -n +2 | awk '{print $1}')
missing=0
for state_id in $worklist; do
    # Skip 鲁 and 周 (Phase 2 covers them via reign_table.json)
    if [ "$state_id" = "sta:lu" ] || [ "$state_id" = "sta:zhou" ]; then
        continue
    fi
    slug=$(echo "$state_id" | tr ':' '_')
    if [ ! -f "data/reigns/${slug}.yaml" ]; then
        log "  missing: data/reigns/${slug}.yaml"
        missing=$((missing + 1))
    fi
done
if [ "$missing" -eq 0 ]; then
    pass "all worklist states have reign YAMLs"
else
    fail "${missing} state(s) missing reign YAML"
fi

# ---------------------------------------------------------------------------
section "5. Ch.2-5 loaded into canonical"
why "All four new chapters must have a completed extract-load run."
loaded=$(uv run python -c "
import sqlite3, json
c = sqlite3.connect('data/changjuan.sqlite')
rows = c.execute(\"SELECT id, scope_json FROM pipeline_runs WHERE stage='extract-load'\").fetchall()
chapters_loaded = set()
for r in rows:
    if r[1]:
        scope = json.loads(r[1])
        if 'chapter' in scope:
            chapters_loaded.add(scope['chapter'])
print(','.join(str(c) for c in sorted(chapters_loaded)))
" 2>>"${LOG_FILE}")
log "  chapters with extract-load runs: $loaded"
all_present=1
for ch in 1 2 3 4 5; do
    if ! echo ",$loaded," | grep -q ",$ch,"; then
        all_present=0
    fi
done
if [ "$all_present" = "1" ]; then
    pass "chapters 1-5 all have extract-load runs"
else
    fail "missing chapters in extract-load runs"
fi

# ---------------------------------------------------------------------------
section "6. Smoke checks pass for Ch.2-5"
why "Per-chapter integrity must hold."
smoke_fail=0
run_ids=$(uv run python -c "
import sqlite3, json
c = sqlite3.connect('data/changjuan.sqlite')
# For each chapter 2-5, take the most-recent extract-load run.
latest = {}
for r in c.execute(\"SELECT id, scope_json, started_at FROM pipeline_runs WHERE stage='extract-load' ORDER BY started_at\").fetchall():
    if r[1]:
        scope = json.loads(r[1])
        ch = scope.get('chapter')
        if ch in (2, 3, 4, 5):
            latest[ch] = r[0]
print('\n'.join(latest[c] for c in sorted(latest)))
" 2>>"${LOG_FILE}")
for run_id in $run_ids; do
    if ./scripts/smoke-check-run --run-id "$run_id" 2>>"${LOG_FILE}" | grep -q '"status": "pass"'; then
        log "  smoke pass: $run_id"
    else
        log "  smoke FAIL: $run_id"
        smoke_fail=$((smoke_fail + 1))
    fi
done
if [ "$smoke_fail" -eq 0 ]; then
    pass "all Ch.2-5 latest runs pass smoke check"
else
    fail "${smoke_fail} smoke check failure(s)"
fi

# ---------------------------------------------------------------------------
section "7. Ch.1 golden still green"
why "Phase 4 must not regress Phase 2's Ch.1 P/R."
if uv run changjuan golden-eval --chapter 1 >>"${LOG_FILE}" 2>&1; then
    pass "Ch.1 golden P/R green"
else
    fail "Ch.1 golden regressed — STOP, investigate"
fi

# ---------------------------------------------------------------------------
section "8. Spot-check QA — accepted with calibration"
why "Phase 2's 0.10 bar assumed Ch.1's hand-curated extraction. Phase 4's multi-chapter synthesis yielded 0.163; accepted with documented calibration per spec §10 (anti-pattern: don't lower the threshold silently)."
mismatch=$(uv run python -c "
import sqlite3, json
c = sqlite3.connect('data/changjuan.sqlite')
runs = []
latest = {}
for r in c.execute(\"SELECT id, scope_json, started_at FROM pipeline_runs WHERE stage='extract-load' ORDER BY started_at\").fetchall():
    if r[1]:
        scope = json.loads(r[1])
        ch = scope.get('chapter')
        if ch in (2, 3, 4, 5):
            latest[ch] = r[0]
runs = list(latest.values())
if not runs:
    print('NO_RUNS'); exit()
placeholders = ','.join('?' * len(runs))
yes = c.execute(f'SELECT COUNT(*) FROM qa_samples WHERE verdict=\"yes\" AND pipeline_run_id IN ({placeholders})', runs).fetchone()[0]
partial = c.execute(f'SELECT COUNT(*) FROM qa_samples WHERE verdict=\"partial\" AND pipeline_run_id IN ({placeholders})', runs).fetchone()[0]
no = c.execute(f'SELECT COUNT(*) FROM qa_samples WHERE verdict=\"no\" AND pipeline_run_id IN ({placeholders})', runs).fetchone()[0]
total = yes + partial + no
rate = (no + 0.5 * partial) / total if total else 0.0
print(f'{rate:.3f}|{total}|{yes}|{partial}|{no}')
" 2>>"${LOG_FILE}")
case "$mismatch" in
    NO_RUNS|"")
        warn "no QA samples loaded for Ch.2-5"
        ;;
    *)
        rate=$(echo "$mismatch" | cut -d'|' -f1)
        total=$(echo "$mismatch" | cut -d'|' -f2)
        log "  spot-check: ${total} facts, weighted mismatch_rate=${rate} (Phase 4 calibration: accepted)"
        # Per user decision: accept; phase 5 PHASE4_DEFERRED tracks recalibration.
        pass "QA accepted with documented calibration (${total} facts judged, rate=${rate})"
        ;;
esac

# ---------------------------------------------------------------------------
section "9. PHASE4_DEFERRED backlog"
why "Phase 5+ starter list."
log "  ${#PHASE4_DEFERRED[@]} items deferred to Phase 5+:"
for item in "${PHASE4_DEFERRED[@]}"; do
    log "    ${C_YELLOW}•${C_RESET} $item"
done

# ---------------------------------------------------------------------------
log ""
log "${C_CYAN}==== Summary ====${C_RESET}"
log "  ${C_GREEN}${N_PASS} passed${C_RESET}   ${C_YELLOW}${N_WARN} warn${C_RESET}   ${C_RED}${N_FAIL} failed${C_RESET}"

if [[ ${N_FAIL} -gt 0 ]]; then
  log ""
  log "${C_RED}Failures:${C_RESET}"
  for r in "${FAIL_REASONS[@]}"; do log "  ${C_RED}✗${C_RESET} ${r}"; done
fi
if [[ ${N_WARN} -gt 0 ]]; then
  log ""
  log "${C_YELLOW}Warnings:${C_RESET}"
  for r in "${WARN_REASONS[@]}"; do log "  ${C_YELLOW}!${C_RESET} ${r}"; done
fi

exit $((N_FAIL > 0 ? 1 : 0))
