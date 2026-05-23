"""Side-by-side candidate-vs-canonical renderer with diff coloring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import streamlit as st

_FIELDS = ("canonical_name", "gender", "clan_name", "state_id", "notes")


@dataclass(frozen=True)
class FieldDiff:
    field: str
    candidate_value: Any
    canonical_value: Any
    badge: str


def _badge(cand: Any, can: Any) -> str:
    if cand == can:
        return "same"
    if cand is None or can is None:
        return "one_null"
    return "disagree"


def render_pair(
    candidate: dict[str, Any],
    canonical: dict[str, Any],
    *,
    edit_mode: bool = False,
    surface_features_json: str | None = None,
    llm_judgment_json: str | None = None,
) -> dict[str, Any] | None:
    """Render the candidate-vs-canonical pair. Returns edits dict if edit_mode."""
    diffs = [
        FieldDiff(
            f,
            candidate.get(f),
            canonical.get(f),
            _badge(candidate.get(f), canonical.get(f)),
        )
        for f in _FIELDS
    ]
    col_a, col_b = st.columns(2)
    edits: dict[str, Any] = {}
    with col_a:
        st.caption(f"A · candidate · {candidate.get('id', '?')}")
        for d in diffs:
            _render_field_readonly(d.field, d.candidate_value, d.badge)
    with col_b:
        st.caption(f"B · canonical · {canonical.get('id', '?')}")
        for d in diffs:
            if edit_mode:
                new_value = st.text_input(
                    d.field,
                    value=str(d.canonical_value or ""),
                    key=f"edit-{canonical.get('id')}-{d.field}",
                )
                if new_value != (d.canonical_value or ""):
                    edits[d.field] = new_value or None
            else:
                _render_field_readonly(d.field, d.canonical_value, d.badge)
    if surface_features_json:
        try:
            features = json.loads(surface_features_json)
            st.caption(f"features: {features}")
        except (ValueError, TypeError):
            pass
    if llm_judgment_json:
        with st.expander("LLM judgment"):
            st.code(llm_judgment_json, language="json")
    return edits if edit_mode else None


def _render_field_readonly(field: str, value: Any, badge: str) -> None:
    badge_color = {"same": "#2f7f3f", "one_null": "#7a7a3a", "disagree": "#7f3f3f"}.get(
        badge, "#444"
    )
    display = value if value is not None else "—"
    inner = (
        f'<span style="background:{badge_color};padding:1px 6px;border-radius:2px">{display}</span>'
    )
    st.markdown(
        f'<div style="padding:4px 0"><span style="color:#888">{field}</span> {inner}</div>',
        unsafe_allow_html=True,
    )
