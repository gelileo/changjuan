#!/usr/bin/env bash
# ============================================================================
# scripts/phase2-prep.sh — Phase 2 readiness checks for changjuan
# ============================================================================
#
# WHAT THIS DOES
#   Runs a sequence of checks and small actions to confirm Phase 1's
#   deterministic foundation is healthy, the source corpus is ingested
#   and chunked, the export contract round-trips, and the project is in
#   a known-good state before Phase 2 (LLM extraction) work begins.
#
#   Every run writes a timestamped log to:
#       data/logs/phase2-prep/YYYYMMDDTHHMMSS.log
#   plus a `latest.log` symlink for grep-friendliness across sessions.
#
# WHY THIS EXISTS
#   Phase 2 introduces real LLM calls (token cost, network), agentic
#   extraction prompts, and a manual golden-chapter annotation step.
#   The margin for "is my env even healthy?" should be zero by then.
#   The log also gives a future session (or future-you) a snapshot of
#   the world right before the LLM stages went live — useful when
#   debugging Phase 2 regressions weeks later.
#
# WHEN TO RUN
#   - Right before starting Phase 2 work.
#   - After pulling on a different machine.
#   - After a long pause between sessions.
#   - Whenever a Phase 2 step fails and you suspect the environment.
#
# USAGE
#   ./scripts/phase2-prep.sh                # full prep run
#   ./scripts/phase2-prep.sh --skip-corpus  # skip the 108-chapter ingest
#                                           # (useful for fast sanity checks)
#
# EXIT CODES
#   0  — all checks passed; the project is Phase-2-ready
#   1  — at least one check failed; review the log
#
# WHAT IT DOES NOT DO
#   - Doesn't start Phase 2 itself (next step: brainstorm + writing-plans
#     for the golden-chapter + stage 3 extract plan).
#   - Doesn't fix issues it finds; it surfaces them.
#   - Doesn't install dependencies; it verifies they exist.
# ============================================================================

set -u
# Intentionally NOT using `set -e`: we want every check to run even if an
# earlier one fails, so the user sees the whole picture in one execution.
# Each check tracks its own pass/fail and aggregates at the bottom.

# ---------------------------------------------------------------------------
# Phase 1 deferred items (baked into the script — git tracks when each lands)
# ---------------------------------------------------------------------------
# When a deferred item is implemented and tested, remove its line.
# When you start Phase 2, the surviving lines below are your starter backlog.
PHASE1_DEFERRED=(
  "BUG: _PARA_SEP regex requires blank lines, but upstream JSON uses single \\n — every chapter becomes one ~5KB mega-chunk. Fix _PARA_SEP to '\\r?\\n+' and add a regression test seeded with single-newline-separated text. HIGH PRIORITY: blocks stage 3 effectiveness."
  "Reign-year boundary tests (鲁僖公33年→627, 鲁文公1年→626, 鲁庄公32年→662)"
  "stage1_ingest return value: count actual inserts, not len(rows)"
  "Date parser: explicit_reign_other (晋/齐/楚 reigns)"
  "stage7_load module split — do BEFORE adding load_candidate_events/places/states"
  "pipeline/confidence.py stub (referenced by confidence-and-invariants.md)"
  "Citation accumulation in stage 7 (entity_citations population)"
  "re-extract CLI verb (changjuan re-extract --chapter N --prompt-version M)"
  "Chunking edge case tests (empty paragraphs; oversized single paragraph)"
  "test_load_updates_scalar_when_new_confidence_higher actually exercises the >+δ branch"
)

# ---------------------------------------------------------------------------
# Setup: paths, logging, colors
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

LOG_DIR="${REPO_ROOT}/data/logs/phase2-prep"
mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%dT%H%M%S)"
LOG_FILE="${LOG_DIR}/${TS}.log"
ln -sfn "${TS}.log" "${LOG_DIR}/latest.log"

SKIP_CORPUS=0
for arg in "$@"; do
  case "$arg" in
    --skip-corpus) SKIP_CORPUS=1 ;;
    -h|--help)
      # Print the top docstring only (lines 1 through the second '# ===' marker)
      awk '/^# ===/{n++; if(n==3) exit} {print}' "${BASH_SOURCE[0]}" \
        | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown arg: $arg (use -h for help)" >&2; exit 2 ;;
  esac
done

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

# Run a command, append its output to the log, return its exit code.
# Stdout/stderr of the command go to the log only (keeps terminal tidy).
run_quiet() {
  {
    echo "--- $ $* ---"
    "$@" 2>&1
    echo "--- exit: $? ---"
  } >> "${LOG_FILE}"
  # Re-run to recover the exit code (executescript-style; cheap for our checks).
  "$@" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
log "${C_CYAN}changjuan — Phase 2 readiness check${C_RESET}  ${C_DIM}(${TS})${C_RESET}"
log "${C_DIM}repo:${C_RESET} ${REPO_ROOT}"
log "${C_DIM}log: ${C_RESET} ${LOG_FILE}"
log "${C_DIM}     ${C_RESET} ${LOG_DIR}/latest.log → ${TS}.log"

# ---------------------------------------------------------------------------
# Section 1 — Environment (uv, python, .venv)
# ---------------------------------------------------------------------------
section "1. Environment"
why "Phase 2 will lean hard on Python tooling. uv + a synced .venv is the precondition."

if command -v uv >/dev/null 2>&1; then
  UV_VERSION="$(uv --version 2>/dev/null | head -1)"
  pass "uv installed (${UV_VERSION})"
else
  fail "uv not found on PATH — install from https://docs.astral.sh/uv/ and re-run"
fi

if [[ -d ".venv" ]]; then
  PY_VERSION="$(uv run python --version 2>/dev/null || echo 'unknown')"
  pass ".venv exists (${PY_VERSION})"
else
  fail ".venv missing — run: uv sync --extra dev"
fi

if uv sync --extra dev --frozen >/dev/null 2>>"${LOG_FILE}"; then
  pass "dependencies up-to-date with uv.lock"
else
  warn "uv sync reported drift between .venv and uv.lock — see log for details"
fi

# ---------------------------------------------------------------------------
# Section 2 — Repo state
# ---------------------------------------------------------------------------
section "2. Repo state"
why "Phase 2 work happens on a new feature branch off main. Start clean."

BRANCH="$(git branch --show-current)"
if [[ "${BRANCH}" == "main" ]]; then
  pass "on main"
else
  warn "on branch '${BRANCH}', not main — Phase 2 plan assumes branching from main"
fi

if [[ -z "$(git status --porcelain)" ]]; then
  pass "working tree clean"
else
  warn "working tree has uncommitted changes — commit, stash, or discard before Phase 2"
  git status --short | sed 's/^/    /' | tee -a "${LOG_FILE}" >/dev/null
fi

LAST_PHASE1_COMMIT="$(git log --format='%h %s' --grep='Merge phase1' -1 2>/dev/null || true)"
if [[ -n "${LAST_PHASE1_COMMIT}" ]]; then
  pass "Phase 1 merge present: ${LAST_PHASE1_COMMIT}"
else
  warn "no 'Merge phase1' commit found — verify Phase 1 actually landed on this branch"
fi

# ---------------------------------------------------------------------------
# Section 3 — Pre-commit hooks
# ---------------------------------------------------------------------------
section "3. Pre-commit hooks"
why "Phase 2 will commit a lot. Hooks must work before the work starts, not after a 20-minute investigation."

if uv run pre-commit run --all-files >>"${LOG_FILE}" 2>&1; then
  pass "all hooks clean (drift-check, ruff, ruff-format, mypy)"
else
  fail "pre-commit hooks reported issues — see log"
fi

# ---------------------------------------------------------------------------
# Section 4 — Test suite
# ---------------------------------------------------------------------------
section "4. Test suite"
why "Regressions in the deterministic foundation will silently corrupt every Phase 2 extraction."

TEST_OUT="$(uv run pytest -q 2>&1)"
echo "${TEST_OUT}" >> "${LOG_FILE}"
TEST_SUMMARY="$(echo "${TEST_OUT}" | tail -1)"
if echo "${TEST_OUT}" | grep -qE '[0-9]+ passed' && ! echo "${TEST_OUT}" | grep -qE '[0-9]+ failed'; then
  pass "pytest: ${TEST_SUMMARY}"
else
  fail "pytest reported failures: ${TEST_SUMMARY}"
fi

# ---------------------------------------------------------------------------
# Section 5 — Living-docs validators
# ---------------------------------------------------------------------------
section "5. Living-docs"
why "Articles drifting from code is the failure mode the methodology exists to prevent. Catch it here, not at PR time."

if ./scripts/validate-articles >>"${LOG_FILE}" 2>&1; then
  ART_COUNT="$(grep -oE '[0-9]+ article' "${LOG_FILE}" | tail -1 || echo '?')"
  pass "validate-articles: all frontmatter valid (${ART_COUNT})"
else
  fail "validate-articles found issues — see log"
fi

if ./scripts/drift-check --base-ref HEAD >>"${LOG_FILE}" 2>&1; then
  pass "drift-check against HEAD: no uncommitted code/article drift"
else
  warn "drift-check found something — review log; safe if no commits pending"
fi

# ---------------------------------------------------------------------------
# Section 6 — Corpus availability
# ---------------------------------------------------------------------------
section "6. Corpus availability"
why "Stage 3 (Phase 2) reads from corpus.sqlite. If the source symlink is broken, nothing downstream works."

CORPUS_SRC="corpora/dongzhoulieguozhi/json/东周列国志.json"
if [[ -L "corpora/dongzhoulieguozhi" ]]; then
  if [[ -f "${CORPUS_SRC}" ]]; then
    SIZE="$(wc -c < "${CORPUS_SRC}" | tr -d ' ')"
    pass "dongzhoulieguozhi symlink resolves; JSON is ${SIZE} bytes"
  else
    fail "symlink exists but target JSON missing at ${CORPUS_SRC}"
  fi
else
  fail "corpora/dongzhoulieguozhi is not a symlink — re-create via 'ln -s ../../dongzhoulieguozhi corpora/dongzhoulieguozhi'"
fi

# ---------------------------------------------------------------------------
# Section 7 — Real corpus ingest + chunk
# ---------------------------------------------------------------------------
if [[ ${SKIP_CORPUS} -eq 1 ]]; then
  section "7. Corpus ingest + chunk  (SKIPPED via --skip-corpus)"
else
  section "7. Corpus ingest + chunk"
  why "Confirms Phase 1's stages 1+2 work end-to-end against the real 108-chapter corpus, not just fixtures."

  rm -f data/corpus.sqlite data/corpus.sqlite-journal data/corpus.sqlite-wal data/corpus.sqlite-shm 2>/dev/null || true

  if uv run changjuan ingest >>"${LOG_FILE}" 2>&1; then
    DOC_COUNT="$(uv run sqlite3 data/corpus.sqlite 'SELECT COUNT(*) FROM documents WHERE corpus="dongzhoulieguozhi";' 2>/dev/null || echo 0)"
    if [[ "${DOC_COUNT}" == "108" ]]; then
      pass "ingest: 108 chapters loaded into corpus.sqlite"
    else
      fail "ingest: expected 108 documents, got ${DOC_COUNT}"
    fi
  else
    fail "changjuan ingest failed — see log"
  fi

  if uv run changjuan chunk >>"${LOG_FILE}" 2>&1; then
    CHUNK_COUNT="$(uv run sqlite3 data/corpus.sqlite 'SELECT COUNT(*) FROM chunks;' 2>/dev/null || echo 0)"
    if [[ "${CHUNK_COUNT}" -ge 200 ]]; then
      pass "chunk: ${CHUNK_COUNT} chunks produced (healthy splitting)"
    elif [[ "${CHUNK_COUNT}" -eq 108 ]]; then
      warn "chunk: exactly 108 chunks (one per chapter) — _PARA_SEP regex is treating each chapter as one giant paragraph; see deferred item #1"
    else
      warn "chunk: ${CHUNK_COUNT} chunks — fewer than the ~300+ expected; investigate paragraph splitting"
    fi
  else
    fail "changjuan chunk failed — see log"
  fi
fi

# ---------------------------------------------------------------------------
# Section 8 — Export contract round-trip
# ---------------------------------------------------------------------------
section "8. Export contract"
why "Phase 2's extractor output flows through this contract. Confirm the bundle path works before producing real data."

EXPORT_DIR="data/exports/changjuan-export-phase2-prep-${TS}"
rm -rf "${EXPORT_DIR}" 2>/dev/null || true

# Need a canonical_db with at least the schema applied
if uv run changjuan load run:phase2-prep-noop >>"${LOG_FILE}" 2>&1 || true; then
  # No candidates to load is fine; the schema gets applied by the CLI.
  :
fi

if uv run changjuan export "phase2-prep-${TS}" >>"${LOG_FILE}" 2>&1; then
  if [[ -f "${EXPORT_DIR}/manifest.json" ]] && [[ -f "${EXPORT_DIR}/changjuan.sqlite" ]]; then
    pass "export produced manifest.json + changjuan.sqlite at ${EXPORT_DIR}"
    # Confirm no candidate_* tables leaked
    LEAKED="$(uv run sqlite3 "${EXPORT_DIR}/changjuan.sqlite" "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candidate_%';" 2>/dev/null || echo 'query-failed')"
    if [[ -z "${LEAKED}" ]]; then
      pass "export: no candidate_* tables leaked into snapshot"
    else
      fail "export: candidate_* tables present in snapshot — ${LEAKED}"
    fi
  else
    fail "export: bundle missing expected files at ${EXPORT_DIR}"
  fi
else
  fail "changjuan export failed — see log"
fi

# ---------------------------------------------------------------------------
# Section 9 — Phase 2 prerequisites (LLM key, golden chapter selection)
# ---------------------------------------------------------------------------
section "9. Phase 2 prerequisites"
why "Stage 3 extraction needs an LLM key and a manually-annotated golden chapter to validate against."

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  pass "ANTHROPIC_API_KEY is set in the environment (length ${#ANTHROPIC_API_KEY})"
else
  warn "ANTHROPIC_API_KEY not set — Phase 2 stage 3 will fail until you export it (or use a .env file)"
fi

if [[ -d "tests/fixtures/golden" ]] && [[ -n "$(find tests/fixtures/golden -name '*.json' 2>/dev/null | head -1)" ]]; then
  pass "golden chapter fixtures present under tests/fixtures/golden/"
else
  warn "no golden chapter annotations found — Phase 2 plan recommends Ch.1 + Ch.~40 (城濮之战); pick and hand-annotate before stage 3 lands"
fi

# ---------------------------------------------------------------------------
# Section 10 — Phase 1 review backlog (deferred items)
# ---------------------------------------------------------------------------
section "10. Phase 1 review backlog"
why "Items from the final Phase 1 review that were deferred to Phase 2. Remove a line from PHASE1_DEFERRED in this script when each lands."

if [[ ${#PHASE1_DEFERRED[@]} -eq 0 ]]; then
  pass "all Phase 1 review items addressed (nothing in PHASE1_DEFERRED)"
else
  log "  ${C_DIM}${#PHASE1_DEFERRED[@]} items remaining:${C_RESET}"
  for item in "${PHASE1_DEFERRED[@]}"; do
    log "    ${C_YELLOW}•${C_RESET} ${item}"
  done
fi

# ---------------------------------------------------------------------------
# Summary + next steps
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
log "${C_CYAN}Next steps:${C_RESET}"
if [[ ${N_FAIL} -gt 0 ]]; then
  log "  1. Fix the failures above. Re-run this script."
  log "  2. When green, proceed to Phase 2 brainstorming."
else
  log "  1. Open a Claude session in this repo."
  log "  2. Invoke /brainstorming to scope Phase 2 (golden chapter + stage 3 extract)."
  log "  3. When the plan is approved, invoke /writing-plans, then /subagent-driven-development."
  log "  4. Reference this log (${LOG_FILE}) when describing the starting state."
fi

log ""
log "${C_DIM}Full log: ${LOG_FILE}${C_RESET}"

if [[ ${N_FAIL} -gt 0 ]]; then exit 1; else exit 0; fi
