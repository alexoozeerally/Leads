"""Lead qualification — aggregate every signal into a :class:`LeadScore`.

Combines the website audit, vision, GBP, social, and competitor outputs into a
single qualified lead: opportunity, likelihood, budget/value bands, priority, and
a **per-deduction rationale**. Estimates (budget, value, likelihood) are derived
from *observed evidence* via documented heuristics and every one carries its
reasoning — nothing is guessed from thin air. Where a signal is absent it simply
doesn't contribute, and the rationale says why.
"""

from __future__ import annotations

from app.schemas.audit import AuditResult, WebsiteState
from app.schemas.business import Business
from app.schemas.competitor import CompetitorReport
from app.schemas.lead_score import Deduction, LeadScore, Priority

# Budget/value bands keyed by the kind of engagement the evidence implies.
# These are transparent estimates, not quotes — each is attached to a rationale.
_BUDGET_BANDS = {
    "new_site": ("£2,000–£5,000", "£3,000–£8,000"),
    "rebuild": ("£2,500–£6,000", "£3,500–£9,000"),
    "redesign": ("£1,500–£4,000", "£2,500–£6,000"),
    "improve": ("£800–£2,000", "£1,500–£3,500"),
}


class LeadScorer:
    """Turns the audit bundle into a qualified :class:`LeadScore`."""

    def score(
        self,
        *,
        business: Business,
        website_state: WebsiteState,
        opportunity_score: float,
        results: dict[str, AuditResult],
        competitor: CompetitorReport | None = None,
    ) -> LeadScore:
        rationale: list[Deduction] = []

        # --- Need / urgency from the website state + audit quality -----------
        quality = self._quality_ratio(results.get("auditor"))
        self._explain_need(website_state, quality, rationale)

        # --- Competitive pressure -------------------------------------------
        pressure = competitor.competitive_pressure if competitor else 0.0
        if competitor and competitor.competitors_found and pressure > 0:
            rationale.append(
                Deduction(
                    dimension="competition",
                    points=round(pressure * 15, 1),
                    rationale=(
                        f"Behind {competitor.competitors_found} nearby competitor(s) on "
                        "website quality and/or reviews — a redesign is more compelling."
                    ),
                )
            )

        # --- Reachability (affects likelihood, not need) ---------------------
        contactable = self._is_contactable(business, results)

        # --- Budget / project value bands ------------------------------------
        band_key, band_reason = self._budget_band(website_state, quality)
        budget, project_value = _BUDGET_BANDS[band_key]

        # --- Likelihood of purchase ------------------------------------------
        likelihood, likelihood_reason = self._likelihood(
            opportunity_score, contactable, business, pressure
        )

        priority = self._priority(opportunity_score)
        summary = self._summarise(
            business, website_state, opportunity_score, priority, budget, band_reason
        )

        return LeadScore(
            dimension_scores=self._dimension_scores(results),
            opportunity_score=round(opportunity_score, 1),
            estimated_budget=budget,
            estimated_project_value=project_value,
            likelihood_of_purchase=round(likelihood, 2),
            priority=priority,
            rationale=rationale
            + [
                Deduction(dimension="budget", points=0.0, rationale=band_reason),
                Deduction(dimension="likelihood", points=0.0, rationale=likelihood_reason),
            ],
            summary=summary,
        )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _quality_ratio(result: AuditResult | None) -> float | None:
        if result is None:
            return None
        value, mx = result.total()
        return (value / mx) if mx else None

    @staticmethod
    def _dimension_scores(results: dict[str, AuditResult]) -> dict:
        """Flatten module scores into a single dimension map for the record."""
        out = {}
        for module, result in results.items():
            for name, entry in result.scores.items():
                out[f"{module}.{name}"] = entry
        return out

    def _explain_need(
        self, state: WebsiteState, quality: float | None, rationale: list[Deduction]
    ) -> None:
        if state == WebsiteState.NO_SITE:
            rationale.append(
                Deduction(
                    dimension="need",
                    points=45.0,
                    rationale="No website at all — the clearest possible web-design need.",
                )
            )
        elif state in (
            WebsiteState.BROKEN,
            WebsiteState.PARKED,
            WebsiteState.UNDER_CONSTRUCTION,
            WebsiteState.REDIRECT_LOOP,
            WebsiteState.INVALID_SSL,
        ):
            rationale.append(
                Deduction(
                    dimension="need",
                    points=40.0,
                    rationale=f"Website is '{state.value}' — effectively no working site.",
                )
            )
        elif quality is not None:
            deficit = round((1 - quality) * 100)
            rationale.append(
                Deduction(
                    dimension="need",
                    points=round((1 - quality) * 45, 1),
                    rationale=(
                        f"Live site scores {quality:.0%} on the technical+visual audit — "
                        f"~{deficit}% headroom to improve."
                    ),
                )
            )

    @staticmethod
    def _is_contactable(business: Business, results: dict[str, AuditResult]) -> bool:
        if business.email or business.phone:
            return True
        signals = (results.get("auditor") or AuditResult(module="auditor")).raw.get("signals", {})
        return bool(signals.get("has_tel_link") or signals.get("has_mailto_link"))

    @staticmethod
    def _budget_band(state: WebsiteState, quality: float | None) -> tuple[str, str]:
        if state == WebsiteState.NO_SITE:
            return "new_site", (
                "No existing site, so the estimate is for a new small-business website "
                "(evidence: website state = no_site)."
            )
        if state in (
            WebsiteState.BROKEN,
            WebsiteState.PARKED,
            WebsiteState.UNDER_CONSTRUCTION,
            WebsiteState.REDIRECT_LOOP,
            WebsiteState.INVALID_SSL,
        ):
            return "rebuild", (
                f"Site is '{state.value}', so the estimate is for a rebuild "
                "(evidence: website state)."
            )
        if quality is not None and quality < 0.5:
            return "redesign", (
                f"Live but weak site ({quality:.0%} audit score) — estimate is for a full "
                "redesign."
            )
        return "improve", (
            "Live and reasonably solid site — estimate is for targeted improvements rather "
            "than a rebuild."
        )

    @staticmethod
    def _likelihood(
        opportunity: float, contactable: bool, business: Business, pressure: float
    ) -> tuple[float, str]:
        base = 0.25 + 0.4 * (opportunity / 100)
        reasons = [f"need {opportunity:.0f}/100"]
        if contactable:
            base += 0.15
            reasons.append("reachable (email/phone found)")
        else:
            reasons.append("no contact method found — harder to reach")
        if business.review_count:
            base += 0.1
            reasons.append(f"active business ({business.review_count} reviews)")
        if pressure > 0:
            base += 0.1
            reasons.append("under competitive pressure")
        return min(1.0, base), "Likelihood from: " + ", ".join(reasons) + "."

    @staticmethod
    def _priority(opportunity: float) -> Priority:
        if opportunity >= 75:
            return Priority.HOT
        if opportunity >= 50:
            return Priority.WARM
        return Priority.COLD

    @staticmethod
    def _summarise(
        business: Business,
        state: WebsiteState,
        opportunity: float,
        priority: Priority,
        budget: str,
        band_reason: str,
    ) -> str:
        return (
            f"{priority.value} lead: {business.name} scores {opportunity:.0f}/100 opportunity "
            f"(website state: {state.value}). Estimated budget {budget}. {band_reason}"
        )
