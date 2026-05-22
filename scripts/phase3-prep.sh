#!/usr/bin/env bash
# changjuan Phase 3 readiness check.
# Run from the repo root: ./scripts/phase3-prep.sh

set -uo pipefail

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

# ---------------------------------------------------------------------------
# Setup: paths, logging, colors
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

LOG_FILE="${REPO_ROOT}/data/logs/phase3-prep.log"
mkdir -p "$(dirname "${LOG_FILE}")"
: > "${LOG_FILE}"

if [[ -t 1 ]]; then
  C_RED=$'\e[31m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'
  C_BLUE=$'\e[34m'; C_CYAN=$'\e[36m'; C_DIM=$'\e[2m'; C_RESET=$'\e[0m'
else
  C_RED=; C_GREEN=; C_YELLOW=; C_BLUE=; C_CYAN=; C_DIM=; C_RESET=
fi

# Counters
N_PASS=0
N_WARN=0
N_FAIL=0
FAIL_REASONS=()
WARN_REASONS=()

# log()  — print to terminal (with color) AND to log (color-stripped)
# why()  — print a "Why:" rationale line for the next check
# pass() / warn() / fail() — record a check result
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

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
log "${C_CYAN}==== changjuan Phase 3 readiness check ====${C_RESET}"

section "1. Phase 2 still passes"
why "Phase 3 must not regress anything from Phase 2."
if ./scripts/phase2-prep.sh >>"${LOG_FILE}" 2>&1; then
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
if uv run changjuan link --help >>"${LOG_FILE}" 2>&1; then
    pass "changjuan link --help works"
else
    fail "changjuan link verb missing"
fi

section "4. Merge regression set"
why "Linker validation surface; must have ≥5 same + ≥5 different pairs."
if [ -f "tests/golden/merge_regression.yaml" ]; then
    counts=$(uv run python -c "
from pathlib import Path
from tests.golden.regression_loader import load_regression_set
data = load_regression_set(Path('tests/golden/merge_regression.yaml'))
print(f\"{len(data['same_person_pairs'])} {len(data['different_person_pairs'])}\")
" 2>>"${LOG_FILE}")
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
if uv run pytest -m regression -q >>"${LOG_FILE}" 2>&1; then
    pass "regression test passes"
else
    fail "regression test FAILS — calibrate per pipeline/config.py comment block"
fi

section "6. Ch.1 link-then-load integration test"
why "Confirms link + load on the frozen v2 fixture preserves the 13 golden persons."
if uv run pytest -m golden tests/integration/test_link_ch01.py -q >>"${LOG_FILE}" 2>&1; then
    pass "Ch.1 link-then-load yields 13 persons"
else
    fail "test_link_ch01.py FAILED — see log"
fi

section "7. PHASE3_DEFERRED backlog"
why "Phase 4 starter list. Recorded here so Phase 4 has its starting agenda."
log "  ${#PHASE3_DEFERRED[@]} items deferred to Phase 4:"
for item in "${PHASE3_DEFERRED[@]}"; do
    log "    ${C_YELLOW}•${C_RESET} $item"
done

# ---------------------------------------------------------------------------
# Summary
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

log ""
log "${C_DIM}Full log: ${LOG_FILE}${C_RESET}"

if [[ ${N_FAIL} -gt 0 ]]; then exit 1; else exit 0; fi
