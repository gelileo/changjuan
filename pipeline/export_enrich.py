"""Post-snapshot enrichment passes for the export bundle (stage 9).

Each function mutates the already-copied graph.sqlite in place. Kept separate
from stage9_export.py orchestration so each pass has one responsibility and is
unit-testable without building a full bundle.
"""

from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path

from pypinyin import Style, lazy_pinyin

# Curated high-salience event types; everything else gets DEFAULT_WEIGHT.
# Tunable — see reader spec open questions. Matched against events.type exactly.
TYPE_WEIGHTS: dict[str, float] = {
    "战": 3.0,
    "会盟": 3.0,
    "盟": 2.5,
    "弑": 3.0,
    "灭": 3.0,
    "即位": 2.5,
    "立": 2.0,
    "出奔": 2.5,
    "奔": 2.5,
    "伐": 2.0,
    "围": 2.0,
    "薨": 2.0,
    "卒": 2.0,
    "处死": 2.0,
    "杀": 2.0,
}
DEFAULT_WEIGHT = 1.0
SALIENCE_WEIGHT = 1.5  # how strongly within-person rarity boosts a deed

# Prominence tiering (default reader-list membership). Rank-based on the
# aggregate deed_importance score; tunable. Reader defaults to {major, notable}.
PROMINENCE_MAJOR_TOP = 40  # ranks 1..40        -> 'major'
PROMINENCE_NOTABLE_TOP = 250  # ranks 41..250    -> 'notable' (rest -> 'minor')

# Event prominence tiering. Rank-based on the per-event aggregate deed_importance;
# tunable. Reader timeline defaults to {major, notable}.
EVENT_MAJOR_TOP = 80  # ranks 1..80           -> 'major'
EVENT_NOTABLE_TOP = 280  # ranks 81..280       -> 'notable' (rest -> 'minor')
# Reign/state-boundary event types: narratively pivotal even when participant
# scores are low (accession, succession, regicide, ruler death, state end).
# Any 'minor' event of one of these types is promoted to 'notable' (always
# default-visible). Structural constant, like TYPE_WEIGHTS.
EVENT_BOUNDARY_TYPES = frozenset({"即位", "继位", "嗣位", "立君", "弑君", "薨", "灭国"})


def deed_importance(
    *, event_type: str, participants: int, citations: int, person_type_fraction: float
) -> float:
    """Blended importance of one participation.

    global component: type weight scaled by how many people were involved and
    how often it is attested. within-person salience: deeds whose type is rare
    in *this person's* record (small fraction) are boosted, so a minor figure's
    single defining act is not buried by global weighting.

    Note: when a person has only a single deed (person_type_fraction=1.0),
    rarity=1 and salience=1, so the within-person component gives no boost at
    all — the global component alone ranks such minor figures.
    """
    weight = TYPE_WEIGHTS.get(event_type, DEFAULT_WEIGHT)
    global_component = weight * (1 + math.log1p(participants)) * (1 + math.log1p(citations))
    rarity = 1.0 / person_type_fraction if person_type_fraction > 0 else 1.0
    salience = 1 + SALIENCE_WEIGHT * math.log1p(rarity - 1)
    return global_component * salience


def build_deed_importance(graph_db: Path) -> None:
    """Create `deed_importance(event_id, person_id, score)` over every
    participation, using deed_importance()."""
    with sqlite3.connect(graph_db) as g:
        parts = g.execute(
            "SELECT ep.event_id, ep.person_id, e.type "
            "FROM event_participants ep JOIN events e ON e.id = ep.event_id;"
        ).fetchall()
        # participant count per event
        pcount: dict[str, int] = {}
        for eid, _pid, _t in parts:
            pcount[eid] = pcount.get(eid, 0) + 1
        # citation count per event (via entity_citations on the event)
        ccount = dict(
            g.execute(
                "SELECT entity_id, COUNT(*) FROM entity_citations "
                "WHERE entity_kind='event' GROUP BY entity_id;"
            )
        )
        # per-person deed total and per-(person,type) counts
        ptype: dict[tuple[str, str], int] = {}
        ptotal: dict[str, int] = {}
        for _eid, pid, t in parts:
            ptotal[pid] = ptotal.get(pid, 0) + 1
            ptype[(pid, t)] = ptype.get((pid, t), 0) + 1

        g.execute("DROP TABLE IF EXISTS deed_importance;")
        g.execute(
            "CREATE TABLE deed_importance ("
            " event_id TEXT, person_id TEXT, score REAL,"
            " PRIMARY KEY (event_id, person_id));"
        )
        rows = []
        for eid, pid, t in parts:
            frac = ptype[(pid, t)] / ptotal[pid]
            score = deed_importance(
                event_type=t,
                participants=pcount.get(eid, 1),
                citations=ccount.get(eid, 0),
                person_type_fraction=frac,
            )
            rows.append((eid, pid, score))
        # A person appearing in one event under multiple roles yields multiple participation rows
        # that collapse to one (event_id, person_id) score row here (known v1 limitation; the
        # per-person type counts double-count such events — tunable later).
        g.executemany("INSERT OR REPLACE INTO deed_importance VALUES (?,?,?);", rows)


def add_prominence(graph_db: Path, overrides_path: Path | None = None) -> None:
    """Add `persons.prominence` (REAL) and `persons.prominence_tier` (TEXT:
    'major' | 'notable' | 'minor') to the snapshot.

    `prominence` = SUM(deed_importance.score) per person — so this MUST run after
    build_deed_importance(). Tier is a rank-based cutoff (PROMINENCE_MAJOR_TOP /
    PROMINENCE_NOTABLE_TOP), then curated overrides are applied last: `promote`
    raises a 'minor' figure to 'notable' (iconic-but-sparse, e.g. 荆轲/卞和);
    `demote` forces 'minor'. Overrides match on canonical_name.

    The reader defaults its person list to tier IN ('major','notable'); an "All"
    toggle drops the filter. Per-user favorites are intentionally NOT stored here
    — graph.sqlite is a read-only shared bundle. Because prominence is keyed on
    the stable persons.id, the reader unions its own local bookmark/favorite ids
    with the prominent set at read time; no export structure is needed for that.
    """
    promote: set[str] = set()
    demote: set[str] = set()
    if overrides_path and overrides_path.exists():
        import yaml

        data = yaml.safe_load(overrides_path.read_text("utf-8")) or {}
        promote = set(data.get("promote") or [])
        demote = set(data.get("demote") or [])

    with sqlite3.connect(graph_db) as g:
        cols = [r[1] for r in g.execute("PRAGMA table_info(persons);")]
        if "prominence" not in cols:
            g.execute("ALTER TABLE persons ADD COLUMN prominence REAL;")
        if "prominence_tier" not in cols:
            g.execute("ALTER TABLE persons ADD COLUMN prominence_tier TEXT;")

        scores = dict(
            g.execute(
                "SELECT person_id, COALESCE(SUM(score),0) FROM deed_importance GROUP BY person_id;"
            )
        )
        persons = g.execute("SELECT id, canonical_name FROM persons;").fetchall()
        # rank by score desc, stable tiebreak by id
        ranked = sorted(persons, key=lambda r: (-scores.get(r[0], 0.0), r[0]))
        tier: dict[str, str] = {}
        for i, (pid, _name) in enumerate(ranked):
            if i < PROMINENCE_MAJOR_TOP:
                tier[pid] = "major"
            elif i < PROMINENCE_NOTABLE_TOP:
                tier[pid] = "notable"
            else:
                tier[pid] = "minor"

        name_to_ids: dict[str, list[str]] = {}
        for pid, name in persons:
            name_to_ids.setdefault(name, []).append(pid)
        for nm in promote:
            for pid in name_to_ids.get(nm, []):
                if tier.get(pid) == "minor":
                    tier[pid] = "notable"
        for nm in demote:
            for pid in name_to_ids.get(nm, []):
                tier[pid] = "minor"

        g.executemany(
            "UPDATE persons SET prominence = ?, prominence_tier = ? WHERE id = ?;",
            [(round(scores.get(pid, 0.0), 2), tier[pid], pid) for pid, _ in persons],
        )


def add_event_prominence(graph_db: Path) -> None:
    """Add `events.prominence` (REAL) + `events.prominence_tier` (TEXT:
    'major' | 'notable' | 'minor') to the snapshot.

    `prominence` = SUM(deed_importance.score) over the event's participations — so
    this MUST run after build_deed_importance(). Tier is a rank-based cutoff
    (EVENT_MAJOR_TOP / EVENT_NOTABLE_TOP); then any 'minor' event whose `type` is a
    reign/state boundary (EVENT_BOUNDARY_TYPES) is promoted to 'notable' so reign
    starts/ends and state ends always survive the reader's default filter.
    """
    with sqlite3.connect(graph_db) as g:
        cols = [r[1] for r in g.execute("PRAGMA table_info(events);")]
        if "prominence" not in cols:
            g.execute("ALTER TABLE events ADD COLUMN prominence REAL;")
        if "prominence_tier" not in cols:
            g.execute("ALTER TABLE events ADD COLUMN prominence_tier TEXT;")

        scores = dict(
            g.execute(
                "SELECT event_id, COALESCE(SUM(score),0) FROM deed_importance GROUP BY event_id;"
            )
        )
        events = g.execute("SELECT id, type FROM events;").fetchall()
        ranked = sorted(events, key=lambda r: (-scores.get(r[0], 0.0), r[0]))
        tier: dict[str, str] = {}
        for i, (eid, _type) in enumerate(ranked):
            if i < EVENT_MAJOR_TOP:
                tier[eid] = "major"
            elif i < EVENT_NOTABLE_TOP:
                tier[eid] = "notable"
            else:
                tier[eid] = "minor"
        for eid, etype in events:
            if tier.get(eid) == "minor" and etype in EVENT_BOUNDARY_TYPES:
                tier[eid] = "notable"
        g.executemany(
            "UPDATE events SET prominence = ?, prominence_tier = ? WHERE id = ?;",
            [(round(scores.get(eid, 0.0), 2), tier[eid], eid) for eid, _ in events],
        )


def add_narrative_seq(graph_db: Path) -> None:
    """Add `events.narrative_seq` (INTEGER): a sub-year chronological sort key.

    《东周列国志》 narrates chronologically, so an event's position WITHIN a year is
    its earliest chunk citation's chapter, then paragraph. document_id is "dzl:<ch>";
    seq = chapter * 100000 + paragraph_start (paragraphs stay well under 100000 per
    chapter). NULL when an event has no chunk citation. Readers order year-grouped
    lists with `ORDER BY year_bce DESC, COALESCE(narrative_seq, <big>) ASC` instead
    of a per-query min-join over citations. MUST run after build_citations_table().
    """
    with sqlite3.connect(graph_db) as g:
        cols = [r[1] for r in g.execute("PRAGMA table_info(events);")]
        if "narrative_seq" not in cols:
            g.execute("ALTER TABLE events ADD COLUMN narrative_seq INTEGER;")
        g.execute(
            "UPDATE events SET narrative_seq = ("
            "  SELECT MIN("
            "    CAST(substr(c.document_id, instr(c.document_id, ':') + 1) AS INTEGER) * 100000"
            "    + COALESCE(c.paragraph_start, 0))"
            "  FROM entity_citations ec JOIN citations c ON c.citation_id = ec.citation_id"
            "  WHERE ec.entity_kind = 'event' AND ec.entity_id = events.id"
            "    AND ec.citation_id LIKE 'chk:%');"
        )
        g.execute("CREATE INDEX IF NOT EXISTS idx_events_narrative_seq ON events(narrative_seq);")


def add_group_prominence(graph_db: Path, overrides_path: Path | None = None) -> None:
    """Add `groups.prominence` (REAL) + `groups.prominence_tier` (TEXT:
    'major' | 'minor') to the snapshot.

    `prominence` = SUM(deed_importance.score) over the group's persons — used for
    SORT order only (big groups first); MUST run after build_deed_importance().
    `prominence_tier` is 'major' iff the group's name is in the curated allow-list
    under the `states:` key of prominence_overrides.yaml, else 'minor'. Only ~80
    groups, so the default reader list is a curated editorial set, not a rank.

    Note: the `states:` key in prominence_overrides.yaml is a historical name for
    the curated group allow-list; it is intentionally kept as-is (curated data, not
    a schema name).
    """
    major_names: set[str] = set()
    if overrides_path and overrides_path.exists():
        import yaml

        data = yaml.safe_load(overrides_path.read_text("utf-8")) or {}
        # `states:` key is historical (curated data, not a schema name — left as-is)
        major_names = set(data.get("states") or [])

    with sqlite3.connect(graph_db) as g:
        cols = [r[1] for r in g.execute("PRAGMA table_info(groups);")]
        if "prominence" not in cols:
            g.execute("ALTER TABLE groups ADD COLUMN prominence REAL;")
        if "prominence_tier" not in cols:
            g.execute("ALTER TABLE groups ADD COLUMN prominence_tier TEXT;")

        scores = dict(
            g.execute(
                "SELECT p.group_id, COALESCE(SUM(d.score),0) "
                "FROM deed_importance d JOIN persons p ON p.id = d.person_id "
                "WHERE p.group_id IS NOT NULL GROUP BY p.group_id;"
            )
        )
        states = g.execute("SELECT id, name FROM groups;").fetchall()
        g.executemany(
            "UPDATE groups SET prominence = ?, prominence_tier = ? WHERE id = ?;",
            [
                (round(scores.get(sid, 0.0), 2), "major" if name in major_names else "minor", sid)
                for sid, name in states
            ],
        )


def to_pinyin(text: str) -> str:
    """Toneless, joined, lowercased pinyin. Non-Han chars pass through.

    NOTE: polyphonic name characters (e.g. 重 in 重耳) may romanize to their
    most-common reading rather than the name reading; pinyin-quality tuning is
    tracked as an open question in the reader spec, not solved here.
    """
    if not text:
        return ""
    return "".join(lazy_pinyin(text, style=Style.NORMAL)).lower()


def add_pinyin_columns(graph_db: Path) -> None:
    """Add and populate a `pinyin` column on persons.canonical_name and
    person_variants.variant."""
    with sqlite3.connect(graph_db) as g:
        for table, name_col in (
            ("persons", "canonical_name"),
            ("person_variants", "variant"),
        ):
            cols = [r[1] for r in g.execute(f"PRAGMA table_info({table});")]
            if "pinyin" not in cols:
                g.execute(f"ALTER TABLE {table} ADD COLUMN pinyin TEXT;")
            rows = g.execute(f"SELECT rowid, {name_col} FROM {table};").fetchall()
            g.executemany(
                f"UPDATE {table} SET pinyin = ? WHERE rowid = ?;",
                [(to_pinyin(n or ""), rid) for rid, n in rows],
            )


def build_chapter_texts(graph_db: Path, readable_dir: Path) -> None:
    """Fold full chapter prose into the export so a downloaded book is one file.

    Creates `chapter_texts(chapter INTEGER PRIMARY KEY, markdown TEXT)` and
    populates it from `readable_dir/ch[0-9]*.md` (chapter parsed from the
    filename, e.g. ch01.md → 1). The bundled reader keeps using the separate
    `texts/` payload; this table is consumed only by downloaded books (B2).
    Tolerates an absent/empty readable_dir (table created, no rows). Idempotent.
    """
    with sqlite3.connect(graph_db) as g:
        g.execute("DROP TABLE IF EXISTS chapter_texts;")
        g.execute(
            "CREATE TABLE chapter_texts (chapter INTEGER PRIMARY KEY, markdown TEXT NOT NULL);"
        )
        if not readable_dir.is_dir():
            return
        rows: list[tuple[int, str]] = []
        for md in sorted(readable_dir.glob("ch[0-9]*.md")):
            m = re.match(r"ch0*(\d+)\.md$", md.name)
            if not m:
                continue
            rows.append((int(m.group(1)), md.read_text(encoding="utf-8")))
        if rows:
            g.executemany("INSERT INTO chapter_texts VALUES (?,?);", rows)


def build_citations_table(graph_db: Path, corpus_db: Path) -> None:
    """Create `citations` in graph_db, denormalizing each distinct cited chunk's
    passage text from corpus_db's `chunks` table.

    Raises ValueError if any cited chunk id is absent from the corpus (fail loud:
    the reader's one-tap-to-source feature must not silently lose passages).
    """
    with sqlite3.connect(graph_db) as g:
        # entity_citations also holds `run:` pipeline-run provenance ids on edge entities
        # (event_participant, person_state, event_relation, person_relation, event_place).
        # Those are not passage-resolvable — only `chk:` chunk pointers have text in the
        # corpus. Scope the denormalization to chk: ids; run: (and any non-chk:) ids are
        # intentionally ignored here, not treated as missing chunks.
        # distinct chk: ids (~hundreds) stay well under SQLite's bound-variable limit;
        # if a future corpus pushes this into the thousands, switch to ATTACH + INSERT...SELECT.
        cited = [
            r[0]
            for r in g.execute(
                "SELECT DISTINCT citation_id FROM entity_citations "
                "WHERE citation_id LIKE 'chk:%';"
            )
        ]
        g.execute("DROP TABLE IF EXISTS citations;")
        g.execute(
            "CREATE TABLE citations ("
            " citation_id TEXT PRIMARY KEY,"
            " document_id TEXT,"
            " paragraph_start INTEGER,"
            " paragraph_end INTEGER,"
            " text TEXT NOT NULL);"
        )
        if not cited:
            return
        with sqlite3.connect(corpus_db) as cor:
            placeholders = ",".join("?" * len(cited))
            found = {
                cid: (cid, doc, ps, pe, txt)
                for cid, doc, ps, pe, txt in cor.execute(
                    "SELECT id, document_id, paragraph_start, paragraph_end, text "
                    f"FROM chunks WHERE id IN ({placeholders});",
                    cited,
                )
            }
        missing = [c for c in cited if c not in found]
        if missing:
            raise ValueError(
                f"{len(missing)} cited chunk(s) absent from corpus "
                f"(e.g. {missing[:3]}); cannot denormalize citation text."
            )
        g.executemany(
            "INSERT INTO citations VALUES (?,?,?,?,?);",
            [found[c] for c in cited],
        )
