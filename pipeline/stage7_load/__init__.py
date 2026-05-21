"""Stage 7 — Load candidates into canonical store with field-level merge semantics.

Package layout:
  persons.py    — load_candidate_persons (Phase 1 + Phase 2)
  events.py     — load_candidate_events (Phase 2)
  places.py     — load_candidate_places (Phase 2)
  states.py     — load_candidate_states (Phase 2)
  relations.py  — load_candidate_relations (Phase 2)
  audit.py      — _audit helper
  helpers.py    — _slugify, _create_*, merge_date_field, citation FK resolution
  citations.py  — entity_citations accumulator (Phase 2)
"""

from pipeline.stage7_load.events import load_candidate_events
from pipeline.stage7_load.persons import load_candidate_persons
from pipeline.stage7_load.places import load_candidate_places
from pipeline.stage7_load.states import load_candidate_states

__all__ = [
    "load_candidate_events",
    "load_candidate_persons",
    "load_candidate_places",
    "load_candidate_states",
]
