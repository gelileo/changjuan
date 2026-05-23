"""changjuan curator — home screen.

Run with: streamlit run curation/app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from curation.components.coverage_grid import render_coverage_grid
from curation.db import coverage_stats, low_confidence_count, open_merge_candidates

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "changjuan.sqlite"
CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "corpus.sqlite"


def main() -> None:
    st.set_page_config(page_title="changjuan curator", layout="wide")
    st.title("changjuan curator")
    st.caption("Phase 5 — merge-candidates triage. Conflicts and low-confidence are Phase 6.")

    if not DB_PATH.exists():
        st.error(f"DB not found: {DB_PATH}")
        st.stop()

    stats = coverage_stats(DB_PATH, corpus_path=CORPUS_PATH) if CORPUS_PATH.exists() else []
    st.subheader("Chapter coverage")
    if stats:
        render_coverage_grid(stats)
    else:
        st.info("Corpus not loaded — chapter grid unavailable.")

    st.subheader("Queues")
    mc_open = len(open_merge_candidates(DB_PATH))
    st.page_link(
        "pages/1_Merge_candidates.py",
        label=f"🔗 Merge candidates · **{mc_open} open**",
    )
    st.markdown(
        '<div style="opacity:0.5;padding:6px 0">⚖️ Conflicts · '
        '<span style="font-size:0.85em">(Phase 6)</span></div>',
        unsafe_allow_html=True,
    )
    low = low_confidence_count(DB_PATH)
    st.markdown(
        f'<div style="opacity:0.5;padding:6px 0">❓ Low confidence · {low} candidate facts · '
        f'<span style="font-size:0.85em">(Phase 6)</span></div>',
        unsafe_allow_html=True,
    )

    st.subheader("Search")
    st.text_input("search persons / events / places…", disabled=True, help="Phase 6")


if __name__ == "__main__":
    main()
