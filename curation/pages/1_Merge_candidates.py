"""Merge candidates review screen."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit_shortcuts import add_shortcuts

from curation.components.records import render_pair
from curation.components.shell import render_shell
from curation.db import MergeCandidateRow, chapter_citation_context, open_merge_candidates
from pipeline.stage5_link.merge import (
    MergeConflictError,
    MergeError,
    StaleMergeCandidateError,
    accept_merge,
    defer_merge,
    reject_merge,
    split_person,
)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "changjuan.sqlite"
CORPUS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "corpus.sqlite"


def _write_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _load_queue() -> list[MergeCandidateRow]:
    if "mc_queue" not in st.session_state:
        st.session_state["mc_queue"] = open_merge_candidates(DB_PATH)
        st.session_state["mc_cursor"] = 0
    queue: list[MergeCandidateRow] = st.session_state["mc_queue"]
    return queue


def _advance() -> None:
    st.session_state["mc_cursor"] = st.session_state.get("mc_cursor", 0) + 1


def _retreat() -> None:
    st.session_state["mc_cursor"] = max(0, st.session_state.get("mc_cursor", 0) - 1)


def _reload() -> None:
    st.session_state.pop("mc_queue", None)
    st.session_state.pop("mc_cursor", None)
    st.rerun()


def _load_person(conn: sqlite3.Connection, person_id: str) -> dict[str, Any]:
    """Load a person row from either canonical persons or candidate_persons.

    Phase 5.1 dual-table reality: a merge_candidates.candidate_a_id typically
    references candidate_persons.id (not persons.id). The original Phase 5 UI
    only queried persons, so A-side fields all rendered as '-'. Mirror the same
    dual-table fallback used by pipeline.stage5_link.merge._load_reject_payload.
    """
    row = conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM candidate_persons WHERE id = ?", (person_id,)).fetchone()
    return dict(row) if row else {"id": person_id}


def _do_accept(mc_id: str, edits: dict[str, Any] | None = None) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            result = accept_merge(conn, mc_id, edits=edits)
        st.success(
            f"Merged. variants_added={result.variants_added}, "
            f"relations_retargeted={result.relations_retargeted}, "
            f"collisions_resolved={result.collisions_resolved}"
        )
        _advance()
    except StaleMergeCandidateError as e:
        st.warning(f"Already resolved, skipping: {e}")
        _advance()
    except MergeConflictError as e:
        st.error(f"Field disagreement: {e}. Use Edit & accept or Reject.")
    except MergeError as e:
        st.error(f"Merge failed: {e}")
    finally:
        conn.close()


def _do_reject(mc_id: str, note: str | None = None) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            reject_merge(conn, mc_id, note=note)
        st.info("Rejected.")
        _advance()
    except StaleMergeCandidateError as e:
        st.warning(f"Already resolved, skipping: {e}")
        _advance()
    except MergeError as e:
        st.error(f"Reject failed: {e}")
    finally:
        conn.close()


def _do_defer(mc_id: str) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            defer_merge(conn, mc_id)
        _advance()
    finally:
        conn.close()


def _do_split(person_id: str, variants_to_extract: list[str], note: str | None) -> None:
    conn = _write_connect(DB_PATH)
    try:
        with conn:
            result = split_person(
                conn, person_id, variants_to_extract=variants_to_extract, note=note
            )
        st.success(
            f"Split — new person {result.new_person_id} with variants {result.variants_moved}"
        )
        _advance()
    except MergeError as e:
        st.error(f"Split failed: {e}")
    finally:
        conn.close()


def _render_history_sidebar(limit: int = 20) -> None:
    """Render a sidebar panel listing recent merge-related decisions.

    Reads audit_log directly (no schema change), filters to the change_kinds
    written by accept_merge / reject_merge / split_person, and shows the
    most recent rows newest-first. Useful for confirming what just happened
    and for spotting accidental wrong-target decisions during a long walk.
    """
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT entity_kind, entity_id, change_kind, after_json, "
            "       datetime(at, 'localtime') as when_local "
            "FROM audit_log "
            "WHERE change_kind IN ('merge', 'merge_rejected', 'split', 'edit') "
            "ORDER BY at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    with st.sidebar:
        st.subheader(f"Recent decisions ({len(rows)})")
        if not rows:
            st.caption("No decisions yet.")
            return
        for r in rows:
            note = ""
            if r["change_kind"] == "merge_rejected" and r["after_json"]:
                try:
                    parsed = json.loads(r["after_json"])
                    if parsed.get("note"):
                        note = f" — {parsed['note'][:40]}"
                except json.JSONDecodeError:
                    pass
            st.caption(f"`{r['when_local']}` · **{r['change_kind']}** · " f"{r['entity_id']}{note}")


def main() -> None:
    st.set_page_config(page_title="Merge candidates · changjuan curator", layout="wide")
    _render_history_sidebar()
    queue = _load_queue()
    cursor = st.session_state.get("mc_cursor", 0)

    if not queue:
        st.title("Merge candidates")
        st.info("No open merge candidates. The queue is empty.")
        return
    if cursor >= len(queue):
        st.title("Merge candidates")
        st.success(f"Queue empty — {cursor} triaged this session.")
        if st.button("Reload queue"):
            _reload()
        return

    current = queue[cursor]
    st.title(f"Merge candidates · {cursor + 1} / {len(queue)}")

    edit_mode = st.session_state.get("edit_mode", False)
    edits_captured: dict[str, Any] | None = None

    def render_left() -> None:
        # Phase 5.1 read-side: candidate_a_id is typically a candidate_persons row
        # which carries chunk_id + quote directly. entity_citations is canonical-only
        # and won't have rows for candidate ids, so try the candidate row first.
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cp = conn.execute(
                "SELECT chunk_id, quote FROM candidate_persons WHERE id = ?",
                (current.candidate_a_id,),
            ).fetchone()
        if cp is not None:
            st.write(cp["quote"])
            with sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True) as corpus_conn:
                corpus_conn.row_factory = sqlite3.Row
                chunk_row = corpus_conn.execute(
                    "SELECT text FROM chunks WHERE id = ?",
                    (cp["chunk_id"],),
                ).fetchone()
            if chunk_row is not None:
                with st.expander("± 2 paragraphs"):
                    st.write(chunk_row["text"])
            return

        # Escape-hatch: candidate_a is in persons (Phase 5.1) — use entity_citations.
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            cit_id_row = conn.execute(
                "SELECT citation_id FROM entity_citations "
                "WHERE entity_kind = 'person' AND entity_id = ? LIMIT 1",
                (current.candidate_a_id,),
            ).fetchone()
        if cit_id_row is None:
            st.write("(no citation linked to candidate)")
            return
        ctx = chapter_citation_context(cit_id_row[0], corpus_path=CORPUS_PATH)
        st.write(ctx.text)
        if ctx.paragraphs:
            with st.expander("± 2 paragraphs"):
                for p in ctx.paragraphs:
                    st.write(p)

    def render_center() -> None:
        nonlocal edits_captured
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            candidate = _load_person(conn, current.candidate_a_id)
            canonical = _load_person(conn, current.candidate_b_id)
        edits_captured = render_pair(
            candidate,
            canonical,
            edit_mode=edit_mode,
            surface_features_json=current.surface_features_json,
            llm_judgment_json=current.llm_judgment_json,
        )

    def render_right() -> None:
        if st.button("a · Accept merge", use_container_width=True):
            _do_accept(current.mc_id)
            st.rerun()
        # Two-stage button: first click enters edit mode, second click commits with edits.
        # Label flips to make the active mode obvious — without this, the same "Edit & accept"
        # label appears for both states and curators don't realize the second click commits.
        edit_label = "e · ✓ Confirm edits" if edit_mode else "e · Edit & accept"
        if st.button(edit_label, use_container_width=True):
            if edit_mode and edits_captured is not None:
                _do_accept(current.mc_id, edits=edits_captured)
                st.session_state["edit_mode"] = False
                st.rerun()
            else:
                st.session_state["edit_mode"] = True
                st.rerun()
        if edit_mode:
            st.caption("✏️ Edit mode active — modify the center column, then click ✓ Confirm.")
        if st.button("r · Reject", use_container_width=True):
            _do_reject(current.mc_id)
            st.rerun()
        if st.button("d · Defer", use_container_width=True):
            _do_defer(current.mc_id)
            st.rerun()
        with st.expander("s · Split"):
            split_target = st.radio(
                "split which side",
                ("A (candidate)", "B (canonical)"),
                horizontal=True,
                key="split-target",
            )
            variants_text = st.text_input("variants to peel off (comma-separated)")
            split_note = st.text_input("note (optional)", key="split-note")
            if st.button("Confirm split"):
                variants = [v.strip() for v in variants_text.split(",") if v.strip()]
                target_id = (
                    current.candidate_a_id
                    if split_target.startswith("A")
                    else current.candidate_b_id
                )
                _do_split(target_id, variants, split_note or None)
                st.rerun()
        st.divider()
        col_prev, col_next = st.columns(2)
        if col_prev.button("◀ k", use_container_width=True):
            _retreat()
            st.rerun()
        if col_next.button("j ▶", use_container_width=True):
            _advance()
            st.rerun()

    render_shell(
        render_left=render_left,
        render_center=render_center,
        render_right=render_right,
    )

    # streamlit-shortcuts >= 1.3 renamed add_keyboard_shortcuts → add_shortcuts and
    # changed the signature from a single dict to **kwargs mapping key → button label.
    add_shortcuts(
        a="a · Accept merge",
        e="e · Edit & accept",
        r="r · Reject",
        d="d · Defer",
        j="j ▶",
        k="◀ k",
    )


main()
