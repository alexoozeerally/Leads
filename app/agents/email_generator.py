"""Outreach email generator.

Selects a genuine compliment and exactly two grounded opportunities from the
lead's analysis, then asks the LLM to phrase them into a subject, email,
follow-up, and LinkedIn message — validated against :class:`OutreachContent`.
Behind the `LLMClient` interface (real Anthropic or deterministic mock).

Nothing is sent here — this only drafts. Approval and sending are human steps.
"""

from __future__ import annotations

from app.agents.auditor import _NO_AUDIT_STATES
from app.agents.llm_client import LLMClient, get_llm_client
from app.agents.prompt_loader import load_prompt
from app.agents.runner import generate_structured
from app.config.logging import get_logger
from app.schemas.audit import AuditResult
from app.schemas.business import Business
from app.schemas.competitor import CompetitorReport
from app.schemas.lead_score import LeadScore
from app.schemas.outreach import OutreachContent

log = get_logger(__name__)

_DEFAULT_CTA = "Would you be open to a quick 15-minute call to talk it through? No obligation."
_NO_AUDIT_STATE_VALUES = {s.value for s in _NO_AUDIT_STATES}


class EmailGenerator:
    """Drafts reviewable outreach from a qualified lead."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client or get_llm_client()

    async def generate(
        self,
        *,
        business: Business,
        lead_score: LeadScore,
        results: dict[str, AuditResult],
        competitor: CompetitorReport | None,
    ) -> OutreachContent:
        compliment = self._pick_compliment(business, results, competitor)
        opportunities = self._pick_opportunities(results, competitor)

        system = load_prompt("email")
        user = self._build_prompt(business, compliment, opportunities)
        content = await generate_structured(
            self._client, system=system, user=user, schema=OutreachContent
        )
        return content

    # -- selection of honest, grounded content --------------------------------

    def _pick_compliment(
        self,
        business: Business,
        results: dict[str, AuditResult],
        competitor: CompetitorReport | None,
    ) -> str:
        # Prefer a real competitive strength, then good reviews, then a neutral,
        # honest observation — never an invented flattery.
        if competitor and competitor.strengths:
            return competitor.strengths[0]
        if business.rating is not None and business.review_count:
            return (
                f"You've clearly built a strong local reputation — {business.rating:.1f}★ across "
                f"{business.review_count} reviews is no small thing."
            )
        if business.category:
            return f"It's clear there's real local demand for a good {business.category.lower()}."
        return "It's obvious you care about doing right by your local customers."

    # Human-facing opportunity phrasing per weak audit category (distinct, concrete).
    _CATEGORY_OPPORTUNITY = {
        "security": "Serving the site over HTTPS would remove the 'Not secure' warning and "
        "build visitor trust.",
        "mobile_friendly": "Making the site mobile-friendly would reach the many customers "
        "searching on their phones.",
        "navigation": "Clearer navigation would help visitors find services and contact details "
        "faster.",
        "seo": "Improving titles, descriptions and headings would help the site show up in local "
        "search.",
        "content": "Fuller service pages would answer customer questions and support local "
        "ranking.",
        "accessibility": "Small accessibility fixes (image alt text, labelled forms) would widen "
        "your audience.",
        "cta": "A clear call-to-action would tell visitors exactly how to book or enquire.",
        "forms": "A simple enquiry form would let visitors reach you without picking up the phone.",
        "contact": "Adding click-to-call and a visible email would make it effortless to get in "
        "touch.",
        "trust": "Showing reviews and accreditations would reassure first-time visitors.",
        "local_seo": "Adding your address and local business markup would strengthen local "
        "search visibility.",
        "performance": "Speeding up the pages would reduce drop-offs, especially on mobile.",
    }
    _NO_SITE_OPPORTUNITIES = [
        "A simple, professional website would let customers find and trust you online.",
        "A mobile-friendly site with click-to-call would turn phone searches into enquiries.",
    ]

    def _pick_opportunities(
        self, results: dict[str, AuditResult], competitor: CompetitorReport | None
    ) -> list[str]:
        auditor = results.get("auditor")
        no_site = bool(auditor and auditor.raw.get("state") in _NO_AUDIT_STATE_VALUES)

        candidates: list[str] = []
        if competitor and competitor.opportunities:
            candidates.extend(competitor.opportunities)
        if no_site:
            candidates.extend(self._NO_SITE_OPPORTUNITIES)
        elif auditor:
            # Map the weakest audited categories to concrete, distinct opportunities.
            weakest = sorted(auditor.scores.items(), key=lambda kv: kv[1].ratio)
            for name, entry in weakest:
                if entry.ratio >= 0.7:
                    break  # only surface genuine weaknesses
                phrase = self._CATEGORY_OPPORTUNITY.get(name)
                if phrase:
                    candidates.append(phrase)
        candidates.extend(self._NO_SITE_OPPORTUNITIES)  # last-resort, always valid

        # Deduplicate (case-insensitive) and take the first two distinct.
        seen: set[str] = set()
        chosen: list[str] = []
        for c in candidates:
            key = c.strip().lower()
            if key and key not in seen:
                seen.add(key)
                chosen.append(c)
            if len(chosen) == 2:
                break
        return chosen

    @staticmethod
    def _build_prompt(business: Business, compliment: str, opportunities: list[str]) -> str:
        # Clear, parseable markers so both the real model and the deterministic
        # mock use exactly this grounded content.
        return (
            f"BUSINESS: {business.name}\n"
            f"CATEGORY: {business.category or 'local business'}\n"
            f"COMPLIMENT: {compliment}\n"
            f"OPPORTUNITY_1: {opportunities[0]}\n"
            f"OPPORTUNITY_2: {opportunities[1]}\n"
            f"CALL_TO_ACTION: {_DEFAULT_CTA}\n"
            "Write the outreach draft as instructed."
        )
