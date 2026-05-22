"""Stage 5 — Link & Dedup for Person entities (Phase 3).

Package layout:
  scoring.py        — pure-function scorer: person_match_score(a, b) → {score, features}
  candidate_pool.py — relevance pre-filter for the linker (Task 7)
  linker.py         — link_run(conn, pipeline_run_id) orchestrator (Task 8)
"""

from pipeline.stage5_link.candidate_pool import candidate_pool
from pipeline.stage5_link.linker import link_run
from pipeline.stage5_link.scoring import person_match_score

__all__ = ["candidate_pool", "link_run", "person_match_score"]
