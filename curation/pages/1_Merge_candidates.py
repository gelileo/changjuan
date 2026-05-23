"""Merge candidates review screen."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit_shortcuts import add_keyboard_shortcuts

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
    row = conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
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


def main() -> None:
    st.set_page_config(page_title="Merge candidates · changjuan curator", layout="wide")
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
        cit_id_row = (
            sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            .execute(
                "SELECT citation_id FROM entity_citations "
                "WHERE entity_kind = 'person' AND entity_id = ? LIMIT 1",
                (current.candidate_a_id,),
            )
            .fetchone()
        )
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
        if st.button("e · Edit & accept", use_container_width=True):
            if edit_mode and edits_captured is not None:
                _do_accept(current.mc_id, edits=edits_captured)
                st.session_state["edit_mode"] = False
                st.rerun()
            else:
                st.session_state["edit_mode"] = True
                st.rerun()
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

    add_keyboard_shortcuts(
        {
            "a": "a · Accept merge",
            "e": "e · Edit & accept",
            "r": "r · Reject",
            "d": "d · Defer",
            "j": "j ▶",
            "k": "◀ k",
        }
    )


main()
