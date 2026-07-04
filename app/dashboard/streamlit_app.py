"""Streamlit dashboard.

Lists discovered businesses ranked by web-design opportunity with: search /
filter (priority, score, has-draft) / sort, screenshots, the full technical +
visual audit, GBP + social sections, competitor comparison, the lead-score
breakdown, reviewable outreach drafts with approve/un-approve, CSV export, and
progress tracking. Nothing is sent — a human approves every draft.
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

from app.dashboard.data_access import (  # noqa: E402
    LeadRow,
    fetch_latest_leads,
    set_draft_approved,
)
from app.dashboard.export import leads_to_csv  # noqa: E402
from app.dashboard.filters import SORT_OPTIONS, LeadFilter, apply_filter  # noqa: E402

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
        # Contact details — how you actually reach the lead once approved.
        contact_bits = []
        if lead.email:
            contact_bits.append(f"📧 {lead.email}")
        if lead.phone:
            contact_bits.append(f"📞 {lead.phone}")
        if contact_bits:
            st.markdown("**Contact:** " + "  ·  ".join(contact_bits))
        else:
            st.markdown("**Contact:** _no email/phone published — check their website or call_")
        if lead.notes:
            st.markdown(f"> {lead.notes}")
    with right:
        shots = [p for p in (lead.desktop_screenshot, lead.mobile_screenshot) if p]
        if shots:
            cols = st.columns(len(shots))
            for col, path in zip(cols, shots, strict=True):
                if Path(path).exists():
                    col.image(path, width="stretch")
                else:
                    col.info("Screenshot file missing.")
        else:
            st.info("No screenshot (no live site to capture).")

    _render_lead_score(lead)
    _render_audit_report(lead)
    _render_draft(lead)
    st.divider()


PRIORITY_BADGE = {"Hot": "🔥 Hot", "Warm": "🌤 Warm", "Cold": "❄️ Cold"}


def _render_lead_score(lead: LeadRow) -> None:
    ls = lead.lead_score
    if not ls:
        return
    cols = st.columns(4)
    cols[0].markdown(f"**Priority**\n\n{PRIORITY_BADGE.get(ls['priority'], ls['priority'])}")
    cols[1].markdown(f"**Likelihood**\n\n{ls['likelihood_of_purchase']:.0%}")
    cols[2].markdown(f"**Est. budget**\n\n{ls.get('estimated_budget') or '—'}")
    cols[3].markdown(f"**Est. project value**\n\n{ls.get('estimated_project_value') or '—'}")
    with st.expander("🧮 Lead score rationale (per-deduction, evidence-based)"):
        for d in ls.get("rationale", []):
            pts = f"+{d['points']}" if d["points"] else ""
            st.markdown(f"- **{d['dimension']}** {pts} — {d['rationale']}")


def _render_draft(lead: LeadRow) -> None:
    draft = lead.draft
    if not draft:
        st.caption("No outreach draft (contact suppressed or generation skipped).")
        return
    status = "✅ Approved" if draft["approved"] else "⏳ Awaiting approval"
    with st.expander(f"✉️ Outreach draft — {status} (a human sends; nothing is automatic)"):
        st.text_input("Subject", draft["subject"], key=f"subj_{draft['id']}", disabled=True)
        st.markdown("**Email**")
        st.text_area(
            "email",
            draft["email_body"],
            height=220,
            key=f"em_{draft['id']}",
            label_visibility="collapsed",
            disabled=True,
        )
        st.markdown("**Follow-up**")
        st.text_area(
            "fu",
            draft["follow_up"],
            height=100,
            key=f"fu_{draft['id']}",
            label_visibility="collapsed",
            disabled=True,
        )
        st.markdown("**LinkedIn message**")
        st.text_area(
            "li",
            draft["linkedin_message"],
            height=90,
            key=f"li_{draft['id']}",
            label_visibility="collapsed",
            disabled=True,
        )
        st.caption(f"⚖️ {draft['lawful_basis_note']}")
        col1, col2 = st.columns(2)
        if not draft["approved"]:
            if col1.button("Approve draft", key=f"ap_{draft['id']}", type="primary"):
                set_draft_approved(draft["id"], True)
                st.rerun()
        else:
            if col2.button("Un-approve", key=f"un_{draft['id']}"):
                set_draft_approved(draft["id"], False)
                st.rerun()


def _render_audit_report(lead: LeadRow) -> None:
    """Show the full technical + visual audit: every category with its rationale."""
    mr = lead.module_results or {}
    auditor, vision = mr.get("auditor", {}), mr.get("vision", {})
    gbp, social = mr.get("gbp", {}), mr.get("social", {})
    if not any([auditor, vision, gbp, social]):
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
        _render_context_section("Google Business Profile", gbp)
        _render_context_section("Social presence", social)
        _render_competitor_section(mr.get("competitor", {}))


def _render_competitor_section(result: dict) -> None:
    """Render the competitor comparison: standing, strengths/weaknesses, opportunities."""
    raw = (result or {}).get("raw") or {}
    if not raw or not raw.get("competitors_found"):
        if result:
            st.markdown("**Competitor analysis**")
            st.caption(result.get("notes", "No competitors found."))
        return
    st.markdown("**Competitor analysis**")
    st.caption(raw.get("summary", ""))
    for label in ("strengths", "weaknesses"):
        items = raw.get(label) or []
        if items:
            st.markdown(f"_{label.title()}:_")
            for it in items:
                st.markdown(f"- {it}")
    opps = raw.get("opportunities") or []
    if opps:
        st.markdown("_Three sales opportunities:_")
        for i, o in enumerate(opps, 1):
            st.markdown(f"{i}. {o}")


def _render_context_section(title: str, result: dict) -> None:
    """Render a data-available-only section (GBP / social), showing unknowns."""
    if not result:
        return
    st.markdown(f"**{title}**")
    if result.get("notes"):
        st.caption(result["notes"])
    for cat, entry in (result.get("scores") or {}).items():
        _render_score_row(cat.replace("_", " ").title(), entry)
    unknown = (result.get("raw") or {}).get("unknown") or []
    if unknown:
        st.markdown(
            "- _Unknown (not fabricated): " + ", ".join(u.replace("_", " ") for u in unknown) + "_"
        )


def _render_score_row(label: str, entry: dict) -> None:
    value, mx = entry.get("value", 0), entry.get("max", 10)
    ratio = value / mx if mx else 0
    colour = "red" if ratio < 0.4 else ("orange" if ratio < 0.7 else "green")
    st.markdown(f"- **{label}** · :{colour}[{value:.1f}/{mx:.0f}] — {entry.get('explanation', '')}")


def _sidebar_filter(leads: list[LeadRow]) -> LeadFilter:
    st.sidebar.header("Search & filter")
    search = st.sidebar.text_input("Search (name, category, postcode)")
    priorities = st.sidebar.multiselect("Priority", ["Hot", "Warm", "Cold"])
    min_score = st.sidebar.slider("Minimum opportunity score", 0, 100, 0)
    only_draft = st.sidebar.checkbox("Only leads with a draft", value=False)
    sort = st.sidebar.selectbox("Sort by", list(SORT_OPTIONS))
    return LeadFilter(
        search=search,
        priorities=tuple(priorities),
        min_score=float(min_score),
        only_with_draft=only_draft,
        sort=sort,
    )


def main() -> None:
    st.title("AI Web-Design Lead Finder")
    st.caption(
        "Discovered UK businesses ranked by web-design opportunity. Drafts are "
        "reviewed by a human before any outreach is sent."
    )

    all_leads = fetch_latest_leads()
    if not all_leads:
        st.warning("No leads yet. Run the pipeline first:\n\n" "`uv run leadfinder run-sample`")
        return

    lead_filter = _sidebar_filter(all_leads)
    leads = apply_filter(all_leads, lead_filter)

    # Progress tracking across the full set (not just the filtered view).
    drafts = [le for le in all_leads if le.draft]
    approved = [le for le in drafts if le.draft.get("approved")]
    hot = sum(1 for le in all_leads if (le.opportunity_score or 0) >= 75)
    a, b, c, d = st.columns(4)
    a.metric("Leads", f"{len(leads)}/{len(all_leads)}")
    b.metric("Hot (≥75)", hot)
    c.metric("Drafts", len(drafts))
    d.metric("Approved", f"{len(approved)}/{len(drafts) or 0}")

    st.sidebar.divider()
    st.sidebar.download_button(
        "⬇️ Export filtered leads (CSV)",
        data=leads_to_csv(leads),
        file_name="leads.csv",
        mime="text/csv",
    )
    st.divider()

    if not leads:
        st.info("No leads match the current filters.")
        return
    for lead in leads:
        _render_lead(lead)


main()
