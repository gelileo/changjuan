"""108-cell coverage grid for the home screen."""

from __future__ import annotations

import streamlit as st

from curation.db import ChapterStatus

_GRID_CSS = """
<style>
.coverage-grid { display: grid; grid-template-columns: repeat(18, 1fr); gap: 3px; }
.coverage-cell { aspect-ratio: 1; border-radius: 2px; background: #2a2a2a; }
.coverage-cell.extracted { background: #2f7f3f; }
.coverage-cell:hover { outline: 1px solid #6a6a6a; }
</style>
"""


def render_coverage_grid(stats: list[ChapterStatus]) -> None:
    st.markdown(_GRID_CSS, unsafe_allow_html=True)
    cells = "".join(
        f'<div class="coverage-cell {"extracted" if s.extracted else ""}" '
        f'title="第{s.chapter_num}回 · {s.title}"></div>'
        for s in stats
    )
    st.markdown(f'<div class="coverage-grid">{cells}</div>', unsafe_allow_html=True)
    extracted = sum(1 for s in stats if s.extracted)
    st.caption(f"{extracted} / {len(stats)} chapters extracted")
