"""Google Business Profile (GBP) analyser — data-available-only.

We do **not** scrape Google (against its terms). Instead this analyses the
GBP-style fields the discovery provider surfaced (rating, review count, opening
hours, phone, address, website, category) plus what the crawl confirmed. Every
field that is absent is reported as **Unknown** — never fabricated. When there is
no GBP-style data at all, the module says so and contributes no scores.
"""

from __future__ import annotations

from app.schemas.audit import AuditResult, ScoreEntry
from app.schemas.context import AuditContext

_MODULE = "gbp"


class GBPAgent:
    """AuditModule assessing the business's Google-Business-Profile-style data."""

    name = _MODULE

    async def run(self, ctx: AuditContext) -> AuditResult:
        biz = ctx.business
        scores: dict[str, ScoreEntry] = {}
        unknown: list[str] = []

        # --- Reviews / rating -------------------------------------------------
        if biz.review_count is not None or biz.rating is not None:
            scores["reviews"] = self._score_reviews(biz.review_count, biz.rating)
        else:
            unknown.append("reviews/rating")

        # --- Opening hours ----------------------------------------------------
        if biz.opening_hours:
            scores["opening_hours"] = ScoreEntry(
                value=10, max=10, explanation="Opening hours are published."
            )
        else:
            unknown.append("opening_hours")

        # --- Contact completeness (NAP: name, address, phone) -----------------
        nap_present = [
            ("name", bool(biz.name)),
            ("address", bool(biz.address)),
            ("phone", bool(biz.phone)),
        ]
        known_nap = [k for k, present in nap_present if present]
        missing_nap = [k for k, present in nap_present if not present]
        if known_nap:
            value = 10 * len(known_nap) / 3
            expl = f"NAP present: {', '.join(known_nap)}."
            if missing_nap:
                expl += f" Missing (unknown): {', '.join(missing_nap)}."
            scores["nap_consistency"] = ScoreEntry(value=round(value, 2), max=10, explanation=expl)

        # --- Website linked from profile -------------------------------------
        if biz.website:
            scores["website_link"] = ScoreEntry(
                value=10, max=10, explanation="A website is associated with the business."
            )
        else:
            unknown.append("website_link")

        # --- Category ---------------------------------------------------------
        if biz.category:
            scores["category"] = ScoreEntry(
                value=10, max=10, explanation=f"Business category is set ('{biz.category}')."
            )
        else:
            unknown.append("category")

        available = bool(scores)
        notes = self._summarise(available, scores, unknown)
        return AuditResult(
            module=_MODULE,
            scores=scores,
            notes=notes,
            raw={
                "available": available,
                "unknown": unknown,
                "source_provider": biz.source_provider,
            },
        )

    @staticmethod
    def _score_reviews(count: int | None, rating: float | None) -> ScoreEntry:
        parts = []
        pts = 0.0
        if count is not None:
            parts.append(f"{count} reviews")
            pts += min(5.0, count / 20 * 5)  # ~100 reviews saturates the volume half
        else:
            parts.append("review count unknown")
        if rating is not None:
            parts.append(f"{rating:.1f}★ rating")
            pts += (rating / 5) * 5
        else:
            parts.append("rating unknown")
        return ScoreEntry(
            value=round(pts, 2), max=10, explanation="GBP reviews: " + ", ".join(parts) + "."
        )

    @staticmethod
    def _summarise(available: bool, scores: dict[str, ScoreEntry], unknown: list[str]) -> str:
        if not available:
            return "No Google Business Profile data available for this business (unknown)."
        known = ", ".join(k.replace("_", " ") for k in scores)
        note = f"GBP-style data available for: {known}."
        if unknown:
            note += f" Unknown (not fabricated): {', '.join(unknown)}."
        return note
