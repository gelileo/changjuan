"""Post-snapshot enrichment passes for the export bundle (stage 9).

Each function mutates the already-copied graph.sqlite in place. Kept separate
from stage9_export.py orchestration so each pass has one responsibility and is
unit-testable without building a full bundle.
"""

from __future__ import annotations

import math
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


def deed_importance(
    *, event_type: str, participants: int, citations: int, person_type_fraction: float
) -> float:
    """Blended importance of one participation.

    global component: type weight scaled by how many people were involved and
    how often it is attested. within-person salience: deeds whose type is rare
    in *this person's* record (small fraction) are boosted, so a minor figure's
    single defining act is not buried by global weighting.
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
        g.executemany("INSERT OR REPLACE INTO deed_importance VALUES (?,?,?);", rows)


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
