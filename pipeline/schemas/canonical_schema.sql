-- changjuan.sqlite — canonical knowledge graph + candidate staging.
-- Schema follows the 2026-05-20 design spec §5.

-- =========================================================
-- ENTITY TABLES
-- =========================================================

CREATE TABLE IF NOT EXISTS persons (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    gender          TEXT,
    birth_date_json TEXT,
    death_date_json TEXT,
    notes           TEXT,
    state_id        TEXT REFERENCES states(id),
    clan_name       TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS person_variants (
    id          TEXT PRIMARY KEY,
    person_id   TEXT NOT NULL REFERENCES persons(id),
    variant     TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('本名','字','谥号','封号','别名')),
    UNIQUE (person_id, variant, kind)
);

CREATE TABLE IF NOT EXISTS states (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    founded_date_json   TEXT,
    ended_date_json     TEXT,
    ruling_clan         TEXT,
    type                TEXT,
    confidence          REAL NOT NULL,
    provenance          TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS places (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT,
    lat             REAL,
    lon             REAL,
    coord_confidence REAL,
    modern_equiv    TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS state_capitals (
    id                  TEXT PRIMARY KEY,
    state_id            TEXT NOT NULL REFERENCES states(id),
    place_id            TEXT NOT NULL REFERENCES places(id),
    from_date_json      TEXT,
    to_date_json        TEXT,
    citation_id         TEXT,
    confidence          REAL NOT NULL,
    provenance          TEXT NOT NULL CHECK (provenance IN ('auto','curated'))
);

CREATE TABLE IF NOT EXISTS events (
    id                  TEXT PRIMARY KEY,
    type                TEXT NOT NULL,
    date_json           TEXT,
    outcome             TEXT,
    summary             TEXT,
    primary_place_id    TEXT REFERENCES places(id),
    confidence          REAL NOT NULL,
    provenance          TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    pipeline_run_id     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- RELATION TABLES
-- =========================================================

CREATE TABLE IF NOT EXISTS event_participants (
    event_id        TEXT NOT NULL REFERENCES events(id),
    person_id       TEXT NOT NULL REFERENCES persons(id),
    role            TEXT NOT NULL,
    role_detail     TEXT,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (event_id, person_id, role)
);

CREATE TABLE IF NOT EXISTS event_places (
    event_id        TEXT NOT NULL REFERENCES events(id),
    place_id        TEXT NOT NULL REFERENCES places(id),
    role            TEXT NOT NULL,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (event_id, place_id, role)
);

CREATE TABLE IF NOT EXISTS event_relations (
    from_event_id   TEXT NOT NULL REFERENCES events(id),
    to_event_id     TEXT NOT NULL REFERENCES events(id),
    kind            TEXT NOT NULL CHECK (kind IN ('causes','precedes','related')),
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (from_event_id, to_event_id, kind)
);

CREATE TABLE IF NOT EXISTS person_relations (
    from_person_id  TEXT NOT NULL REFERENCES persons(id),
    to_person_id    TEXT NOT NULL REFERENCES persons(id),
    kind            TEXT NOT NULL CHECK (kind IN (
        'parent','child','spouse','sibling','mentor','ruler','minister',
        'ally','rival','killed_by','clan_member'
    )),
    date_json       TEXT,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (from_person_id, to_person_id, kind)
);

CREATE TABLE IF NOT EXISTS person_states (
    person_id       TEXT NOT NULL REFERENCES persons(id),
    state_id        TEXT NOT NULL REFERENCES states(id),
    role            TEXT NOT NULL CHECK (role IN ('ruler','minister','exile','defector','citizen','other')),
    from_date_json  TEXT,
    to_date_json    TEXT,
    citation_id     TEXT,
    confidence      REAL NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN ('auto','curated')),
    PRIMARY KEY (person_id, state_id, role, from_date_json)
);

CREATE TABLE IF NOT EXISTS entity_citations (
    entity_kind     TEXT NOT NULL CHECK (entity_kind IN ('person','state','place','event')),
    entity_id       TEXT NOT NULL,
    citation_id     TEXT NOT NULL,
    PRIMARY KEY (entity_kind, entity_id, citation_id)
);
