"""Genre-profile registry.

A profile is declarative data selecting which *capabilities* the ETL mines for a
book. It drives: the extraction prompt-pack, which capability-specific stages run,
the relation-kind vocabulary the loader validates against, and (via
derive_reader_capabilities) the coarse reader-tab capabilities written to the
export manifest.

Two capability vocabularies (see spec §3.4):
  - ETL (fine): persons, relations, events, chronology, geography, groups, themes
  - Reader (coarse tabs): cast, timeline, groups, themes
"""

from __future__ import annotations


class UnknownProfileError(KeyError):
    """Raised when a profile name is not in PROFILES."""


_HISTORY_PERSON_KINDS = {
    "parent",
    "child",
    "spouse",
    "sibling",
    "mentor",
    "ruler",
    "minister",
    "ally",
    "rival",
    "killed_by",
    "clan_member",
}
_HISTORY_EVENT_KINDS = {"causes", "precedes", "related"}

PROFILES: dict[str, dict[str, object]] = {
    "history": {
        "capabilities": ["persons", "relations", "events", "chronology", "geography", "groups"],
        "person_relation_kinds": _HISTORY_PERSON_KINDS,
        "event_relation_kinds": _HISTORY_EVENT_KINDS,
        "default_group_type": "state",
    },
    # "cast" profile lands in Plan 3 (red-chamber slice).
}

# ETL capability → reader tab. Order here defines canonical tab order.
_READER_TAB_RULES: list[tuple[str, str]] = [
    ("cast", "persons"),  # relations render inside the cast tab
    ("timeline", "chronology"),  # a dateless event list is not a timeline
    ("groups", "groups"),
    ("themes", "themes"),
]


def default_group_type(profile: str) -> str:
    """Return the collective kind that the loader stamps on every group for this profile.

    Raises UnknownProfileError for an unrecognised profile (consistent with
    relation_kinds_for).  Falls back to 'state' if the profile entry omits the key
    (future-proofing for profiles added before the key was mandatory).
    """
    if profile not in PROFILES:
        raise UnknownProfileError(profile)
    return str(PROFILES[profile].get("default_group_type", "state"))


def relation_kinds_for(profile: str, relation: str) -> set[str]:
    """Return a copy of the allowed relation `kind` vocabulary for a profile.

    relation must be 'person' or 'event'. Raises UnknownProfileError on an unknown
    profile, ValueError on an unknown relation kind.
    """
    if profile not in PROFILES:
        raise UnknownProfileError(profile)
    if relation not in ("person", "event"):
        raise ValueError(f"relation must be 'person' or 'event', got {relation!r}")
    return set(PROFILES[profile][f"{relation}_relation_kinds"])  # type: ignore


def derive_reader_capabilities(etl_capabilities: list[str]) -> list[str]:
    """Map fine-grained ETL capabilities to coarse reader-tab capabilities."""
    have = set(etl_capabilities)
    return [tab for tab, required in _READER_TAB_RULES if required in have]
