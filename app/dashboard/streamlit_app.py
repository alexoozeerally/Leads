"""Streamlit dashboard — Phase 1.

Lists discovered businesses with their opportunity score, website state, and the
captured home-page screenshot. Later phases add search/filter, full reports,
competitor comparison, draft review/approval, and CSV export.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# `streamlit run app/dashboard/app.py` executes this file as a script, so the
# repo root is not on sys.path. Add it before importing the app package.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.dashboard.data_access import LeadRow, fetch_latest_leads  # noqa: E402

st.set_page_config(page_title="AI Web-Design Lead Finder", layout="wide")

STATE_BADGES = {
    "no_site": "🚫 No website",
    "parked": "🅿️ Parked domain",
    "broken": "💥 Broken",
    "under_construction": "🚧 Under construction",
    "redirect_loop": "🔁 Redirect loop",
    "invalid_ssl": "🔒 Invalid SSL",
    "ok": "✅ Live site",
    "unknown": "❔ Unknown",
}


def _priority_colour(score: float | None) -> str:
    if score is None:
        return "gray"
    if score >= 75:
        return "red"  # Hot
    if score >= 50:
        return "orange"  # Warm
    return "blue"  # Cold


def _render_lead(lead: LeadRow) -> None:
    left, right = st.columns([2, 3])
    with left:
        st.subheader(lead.name)
        st.caption(f"{lead.category or 'Uncategorised'} · {lead.postcode or ''}")
        score = lead.opportunity_score
        st.markdown(
            f"**Opportunity score:** :{_priority_colour(score)}[{score:.1f} / 100]"
            if score is not None
            else "**Opportunity score:** _n/a_"
        )
        badge = STATE_BADGES.get(lead.website_state, lead.website_state)
        st.markdown(f"**Website state:** {badge}")
        if lead.website:
            st.markdown(f"**Website:** {lead.website}")
        if lead.notes:
            st.markdown(f"> {lead.notes}")
    with right:
        shots = [p for p in (lead.desktop_screenshot, lead.mobile_screenshot) if p]
        if shots:
            cols = st.columns(len(shots))
            for col, path in zip(cols, shots, strict=True):
                if Path(path).exists():
                    col.image(path, use_container_width=True)
                else:
                    col.info("Screenshot file missing.")
        else:
            st.info("No screenshot (no live site to capture).")

    _render_audit_report(lead)
    st.divider()


def _render_audit_report(lead: LeadRow) -> None:
    """Show the full technical + visual audit: every category with its rationale."""
    auditor = (lead.module_results or {}).get("auditor", {})
    vision = (lead.module_results or {}).get("vision", {})
    if not auditor and not vision:
        return
    with st.expander("📋 Full audit report (every score has a rationale)"):
        if auditor.get("scores"):
            st.markdown("**Technical audit**")
            for cat, entry in auditor["scores"].items():
                _render_score_row(cat.replace("_", " ").title(), entry)
        if vision.get("scores"):
            st.markdown("**Visual / design audit** _(vision)_")
            for cat, entry in vision["scores"].items():
                _render_score_row(cat.replace("_", " ").title(), entry)


def _render_score_row(label: str, entry: dict) -> None:
    value, mx = entry.get("value", 0), entry.get("max", 10)
    ratio = value / mx if mx else 0
    colour = "red" if ratio < 0.4 else ("orange" if ratio < 0.7 else "green")
    st.markdown(
        f"- **{label}** · :{colour}[{value:.1f}/{mx:.0f}] — {entry.get('explanation', '')}"
    )


def main() -> None:
    st.title("AI Web-Design Lead Finder")
    st.caption(
        "Discovered UK businesses ranked by web-design opportunity. Drafts are "
        "reviewed by a human before any outreach is sent."
    )

    leads = fetch_latest_leads()
    if not leads:
        st.warning("No leads yet. Run the pipeline first:\n\n" "`uv run leadfinder run-sample`")
        return

    hot = sum(1 for lead in leads if (lead.opportunity_score or 0) >= 75)
    a, b, c = st.columns(3)
    a.metric("Leads", len(leads))
    b.metric("Hot (≥75)", hot)
    c.metric("With a live site", sum(1 for lead in leads if lead.website_state == "ok"))
    st.divider()

    for lead in leads:
        _render_lead(lead)


main()
