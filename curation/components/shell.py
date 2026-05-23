"""40/40/20 review-screen shell."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st


def render_shell(
    *,
    render_left: Callable[[], Any],
    render_center: Callable[[], Any],
    render_right: Callable[[], Any],
) -> None:
    """Render the three-column shell. Each callable owns its column's content."""
    left, center, right = st.columns([40, 40, 20])
    with left:
        st.markdown('<div class="curation-label">EVIDENCE</div>', unsafe_allow_html=True)
        render_left()
    with center:
        st.markdown('<div class="curation-label">CANDIDATE PAIR</div>', unsafe_allow_html=True)
        render_center()
    with right:
        st.markdown('<div class="curation-label">DECISION</div>', unsafe_allow_html=True)
        render_right()
