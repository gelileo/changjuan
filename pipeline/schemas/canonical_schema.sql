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
    social_category TEXT,
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
    -- qualifier on `kind`; NULL = default/unspecified (e.g. blood sibling).
    -- Tag only exceptions: '结义' (sworn), '异母'/'同母异父' (half), '养' (adoptive), …
    relation_detail TEXT,
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
    entity_kind     TEXT NOT NULL CHECK (entity_kind IN (
        'person','state','place','event',
        'event_participant','event_place','event_relation',
        'person_relation','person_state','state_capital'
    )),
    entity_id       TEXT NOT NULL,
    citation_id     TEXT NOT NULL,
    PRIMARY KEY (entity_kind, entity_id, citation_id)
);

-- =========================================================
-- CANDIDATE TABLES (staging area for unvetted extractor output)
-- =========================================================

CREATE TABLE IF NOT EXISTS candidate_persons (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    gender          TEXT,
    birth_date_json TEXT,
    death_date_json TEXT,
    notes           TEXT,
    state_id        TEXT,
    clan_name       TEXT,
    social_category TEXT,
    variants_json   TEXT,
    match_target_id TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_person_variants (
    id                       TEXT PRIMARY KEY,
    candidate_person_id      TEXT NOT NULL REFERENCES candidate_persons(id),
    variant                  TEXT NOT NULL,
    kind                     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidate_person_variants_variant
    ON candidate_person_variants (variant);

-- Phase 3 fix: index on candidate_person_id (used by _load_candidate per-row lookup)
CREATE INDEX IF NOT EXISTS idx_candidate_person_variants_candidate_id
    ON candidate_person_variants (candidate_person_id);

CREATE TABLE IF NOT EXISTS candidate_events (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    date_json       TEXT,
    outcome         TEXT,
    summary         TEXT,
    primary_place_id TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_places (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT,
    lat             REAL,
    lon             REAL,
    coord_confidence REAL,
    modern_equiv    TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_states (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    founded_date_json TEXT,
    ended_date_json TEXT,
    ruling_clan     TEXT,
    type            TEXT,
    confidence      REAL NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    quote           TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_event_participants (
    candidate_event_id  TEXT NOT NULL,
    candidate_person_id TEXT NOT NULL,
    role                TEXT NOT NULL,
    role_detail         TEXT,
    pipeline_run_id     TEXT NOT NULL,
    PRIMARY KEY (candidate_event_id, candidate_person_id, role)
);

CREATE TABLE IF NOT EXISTS candidate_event_places (
    candidate_event_id  TEXT NOT NULL,
    candidate_place_id  TEXT NOT NULL,
    role                TEXT NOT NULL,
    pipeline_run_id     TEXT NOT NULL,
    PRIMARY KEY (candidate_event_id, candidate_place_id, role)
);

CREATE TABLE IF NOT EXISTS candidate_event_relations (
    from_candidate_event_id TEXT NOT NULL,
    to_candidate_event_id   TEXT NOT NULL,
    kind                    TEXT NOT NULL,
    pipeline_run_id         TEXT NOT NULL,
    PRIMARY KEY (from_candidate_event_id, to_candidate_event_id, kind)
);

CREATE TABLE IF NOT EXISTS candidate_person_relations (
    from_candidate_person_id TEXT NOT NULL,
    to_candidate_person_id   TEXT NOT NULL,
    kind                     TEXT NOT NULL,
    date_json                TEXT,
    relation_detail          TEXT,   -- qualifier on `kind` (see person_relations)
    pipeline_run_id          TEXT NOT NULL,
    PRIMARY KEY (from_candidate_person_id, to_candidate_person_id, kind)
);

CREATE TABLE IF NOT EXISTS candidate_person_states (
    candidate_person_id TEXT NOT NULL,
    candidate_state_id  TEXT NOT NULL,
    role                TEXT NOT NULL,
    from_date_json      TEXT,
    to_date_json        TEXT,
    pipeline_run_id     TEXT NOT NULL,
    PRIMARY KEY (candidate_person_id, candidate_state_id, role)
);

CREATE TABLE IF NOT EXISTS candidate_facts (
    id                      TEXT PRIMARY KEY,
    subject_kind            TEXT NOT NULL,
    subject_candidate_id    TEXT NOT NULL,
    field                   TEXT NOT NULL,
    value_json              TEXT NOT NULL,
    justification_quote     TEXT NOT NULL,
    justification_span      TEXT,
    pipeline_run_id         TEXT NOT NULL
);

-- =========================================================
-- BOOKKEEPING
-- =========================================================

CREATE TABLE IF NOT EXISTS conflicts (
    id                          TEXT PRIMARY KEY,
    subject_kind                TEXT NOT NULL,
    subject_id                  TEXT NOT NULL,
    field                       TEXT NOT NULL,
    variants_json               TEXT NOT NULL,
    current_best_variant_idx    INTEGER NOT NULL,
    resolution_rule             TEXT,
    status                      TEXT NOT NULL CHECK (status IN ('open','resolved')) DEFAULT 'open',
    curator_note                TEXT,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at                 TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              TEXT PRIMARY KEY,
    entity_kind     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    field           TEXT,
    change_kind     TEXT NOT NULL CHECK (change_kind IN ('create','set','delete','merge','split','curator_override','merge_collision_resolved','edit','merge_rejected')),
    before_json     TEXT,
    after_json      TEXT,
    actor           TEXT NOT NULL,
    at              TEXT NOT NULL DEFAULT (datetime('now')),
    citation_id     TEXT,
    pipeline_run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_entity_field ON audit_log(entity_kind, entity_id, field);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                      TEXT PRIMARY KEY,
    stage                   TEXT NOT NULL,
    started_at              TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at                TEXT,
    prompt_version          TEXT,
    model                   TEXT,
    scope_json              TEXT,
    stats_json              TEXT,
    stats_schema_version    INTEGER
);

CREATE TABLE IF NOT EXISTS llm_cache (
    id                          TEXT PRIMARY KEY,
    key_hash                    TEXT NOT NULL UNIQUE,
    model                       TEXT NOT NULL,
    prompt_template_version     TEXT NOT NULL,
    request_json                TEXT NOT NULL,
    response_json               TEXT NOT NULL,
    tokens_in                   INTEGER,
    tokens_out                  INTEGER,
    cost_usd                    REAL,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS merge_candidates (
    id                  TEXT PRIMARY KEY,
    kind                TEXT NOT NULL CHECK (kind IN ('person','state','place','event')),
    candidate_a_id      TEXT NOT NULL,
    candidate_b_id      TEXT NOT NULL,
    score               REAL NOT NULL,
    surface_features_json TEXT,
    llm_judgment_json   TEXT,
    status              TEXT NOT NULL CHECK (status IN ('open','merged','rejected')) DEFAULT 'open',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at         TEXT
);

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

CREATE TABLE IF NOT EXISTS qa_samples (
    id              TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    record_kind     TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    field           TEXT NOT NULL,
    verdict         TEXT NOT NULL CHECK (verdict IN ('yes','no','partial')),
    verifier_model  TEXT NOT NULL,
    at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- VIEWS
-- =========================================================

CREATE VIEW IF NOT EXISTS field_history AS
SELECT
    entity_kind,
    entity_id,
    field,
    json_extract(after_json, '$.value')      AS value_json,
    json_extract(after_json, '$.confidence') AS confidence,
    actor                                    AS source,
    citation_id,
    at,
    pipeline_run_id
FROM audit_log
WHERE field IS NOT NULL
ORDER BY entity_kind, entity_id, field, at;
