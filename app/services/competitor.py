"""Competitor analysis.

For a lead, discovers nearby same-industry competitors **through the same
provider interface** (never a hardcoded source), optionally audits their
websites, compares the lead against them on website quality, reviews, and web
presence, ranks it, surfaces strengths/weaknesses, and generates three concrete,
personalised sales opportunities grounded in the observed gaps.

Nothing is fabricated: a competitor whose website is not assessed contributes
``website_quality = None`` (unknown) and is excluded from quality averages.
"""

from __future__ import annotations

from collections.abc import Callable

from app.agents.auditor import WebsiteAuditor
from app.business_providers.base import BusinessProvider
from app.config.logging import get_logger
from app.crawler.crawler import WebsiteCrawler
from app.schemas.audit import AuditResult
from app.schemas.business import Business, DiscoveryQuery
from app.schemas.competitor import CompetitorEntry, CompetitorReport
from app.schemas.context import AuditContext

log = get_logger(__name__)


def _quality_ratio(result: AuditResult) -> float | None:
    value, mx = result.total()
    return (value / mx) if mx else None


class CompetitorService:
    """Builds a :class:`CompetitorReport` for a lead using the provider interface."""

    def __init__(
        self,
        *,
        provider: BusinessProvider,
        crawler: WebsiteCrawler | None = None,
        auditor: WebsiteAuditor | None = None,
        website_resolver: Callable[[str], str] | None = None,
        max_competitors: int = 4,
        audit_competitor_sites: bool = True,
    ) -> None:
        self._provider = provider
        self._crawler = crawler
        self._auditor = auditor
        self._resolver = website_resolver or (lambda url: url)
        self._max = max_competitors
        self._audit_sites = audit_competitor_sites

    async def analyse(
        self, business: Business, lead_website_quality: float | None
    ) -> CompetitorReport:
        competitors = await self._discover(business)
        if not competitors:
            return CompetitorReport(
                competitors_found=0,
                summary="No same-industry competitors were found nearby to compare against.",
            )

        entries = [await self._to_entry(c) for c in competitors]
        report = self._compare(business, lead_website_quality, entries)
        return report

    async def _discover(self, business: Business) -> list[Business]:
        if not business.category:
            return []
        query = DiscoveryQuery(
            industry=business.category,
            town=None,
            postcode=business.postcode,
            radius_km=10,
            limit=self._max + 3,
        )
        try:
            found = await self._provider.search(query)
        except Exception as exc:
            log.warning("competitor.discover_failed", business=business.name, error=str(exc))
            return []
        # Exclude the business itself (by name — dedupe keys differ once websites
        # are resolved to live URLs).
        own = business.name.strip().lower()
        competitors = [b for b in found if b.name.strip().lower() != own]
        return competitors[: self._max]

    async def _to_entry(self, competitor: Business) -> CompetitorEntry:
        website_quality: float | None = None
        has_website = bool(competitor.website)
        if has_website and self._audit_sites and self._crawler and self._auditor:
            try:
                url = self._resolver(competitor.website)
                crawl = await self._crawler.crawl(url)
                ctx = AuditContext(business=competitor, crawl=crawl)
                result = await self._auditor.run(ctx)
                website_quality = _quality_ratio(result)
            except Exception as exc:  # a competitor's site failing must not break analysis
                log.warning("competitor.audit_failed", competitor=competitor.name, error=str(exc))
        return CompetitorEntry(
            name=competitor.name,
            rating=competitor.rating,
            review_count=competitor.review_count,
            has_website=has_website,
            website_quality=website_quality,
        )

    def _compare(
        self,
        business: Business,
        lead_quality: float | None,
        entries: list[CompetitorEntry],
    ) -> CompetitorReport:
        report = CompetitorReport(competitors_found=len(entries), competitors=entries)

        # --- Reviews standing ------------------------------------------------
        comp_reviews = [e.review_count for e in entries if e.review_count is not None]
        comp_ratings = [e.rating for e in entries if e.rating is not None]
        if comp_reviews:
            report.avg_competitor_reviews = round(sum(comp_reviews) / len(comp_reviews), 1)
        if comp_ratings:
            report.avg_competitor_rating = round(sum(comp_ratings) / len(comp_ratings), 2)

        if business.review_count is not None and comp_reviews:
            better = sum(1 for c in comp_reviews if c > business.review_count)
            report.review_rank = f"{better + 1} of {len(comp_reviews) + 1}"

        # --- Website standing ------------------------------------------------
        comp_quality = [e.website_quality for e in entries if e.website_quality is not None]
        report.competitors_with_website = sum(1 for e in entries if e.has_website)
        report.lead_website_quality = lead_quality
        if comp_quality:
            report.avg_competitor_website_quality = round(sum(comp_quality) / len(comp_quality), 3)

        self._derive_insights(business, report)
        report.summary = self._summarise(business, report)
        return report

    def _derive_insights(self, business: Business, report: CompetitorReport) -> None:
        strengths, weaknesses, opportunities = [], [], []
        pressure = 0.0

        # Website quality gap
        lq, aq = report.lead_website_quality, report.avg_competitor_website_quality
        if lq is None:
            weaknesses.append("You have no assessable website while competitors are online.")
            opportunities.append(
                f"{report.competitors_with_website} of {report.competitors_found} nearby "
                "competitors have a live website — a modern site would let you compete for the "
                "same customers searching online."
            )
            pressure += 0.4
        elif aq is not None:
            if lq + 0.05 < aq:
                gap = round((aq - lq) * 100)
                weaknesses.append(
                    f"Your website scores ~{gap} points below the local competitor average."
                )
                opportunities.append(
                    f"Competitors' sites are meaningfully stronger (avg {aq:.0%} vs your "
                    f"{lq:.0%}). A redesign closing the biggest gaps (mobile, speed, clear "
                    "calls-to-action) would put you level or ahead."
                )
                pressure += min(0.4, (aq - lq))
            elif lq > aq + 0.05:
                strengths.append("Your website is stronger than the local competitor average.")

        # Reviews gap
        if business.review_count is not None and report.avg_competitor_reviews is not None:
            if business.review_count < report.avg_competitor_reviews:
                opportunities.append(
                    f"Competitors average {report.avg_competitor_reviews:.0f} reviews vs your "
                    f"{business.review_count}. Adding review prompts and a testimonials section to "
                    "the site would build trust and improve local ranking."
                )
                pressure += 0.15
            else:
                strengths.append(
                    f"You have more reviews ({business.review_count}) than the local average "
                    f"({report.avg_competitor_reviews:.0f}) — a strong trust asset to showcase."
                )
        if (
            business.rating is not None
            and report.avg_competitor_rating is not None
            and business.rating >= report.avg_competitor_rating
        ):
            strengths.append(
                f"Your {business.rating:.1f}★ rating meets or beats the local average "
                f"({report.avg_competitor_rating:.1f}★)."
            )

        # Ensure exactly three concrete opportunities (top up from generic-but-real gaps).
        backfill = [
            "Add prominent click-to-call and an enquiry form so more visitors convert.",
            "Publish clear service pages targeting local search terms your competitors rank for.",
            "Show trust signals (reviews, accreditations, guarantees) above the fold.",
        ]
        for item in backfill:
            if len(opportunities) >= 3:
                break
            if item not in opportunities:
                opportunities.append(item)

        report.strengths = strengths
        report.weaknesses = weaknesses
        report.opportunities = opportunities[:3]
        report.competitive_pressure = round(min(1.0, pressure), 3)

    @staticmethod
    def _summarise(business: Business, report: CompetitorReport) -> str:
        bits = [f"Compared against {report.competitors_found} nearby competitor(s)."]
        if report.review_rank:
            bits.append(f"Review standing: {report.review_rank} by volume.")
        if (
            report.avg_competitor_website_quality is not None
            and report.lead_website_quality is not None
        ):
            bits.append(
                f"Website quality {report.lead_website_quality:.0%} vs competitor avg "
                f"{report.avg_competitor_website_quality:.0%}."
            )
        return " ".join(bits)

    def to_audit_result(self, report: CompetitorReport) -> AuditResult:
        """Expose the report as an AuditResult so it can be stored uniformly."""
        return AuditResult(
            module="competitor",
            scores={},  # competitor pressure feeds opportunity directly, not as a 0-10 score
            notes=report.summary,
            raw=report.model_dump(),
        )
