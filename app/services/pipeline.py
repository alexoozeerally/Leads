"""Orchestration: discover -> crawl -> audit -> score -> persist.

This service wires the provider, crawler, and agents to the repositories. It is
the single place that knows the end-to-end flow; everything it depends on is an
interface (provider, crawler, audit modules, LLM client), so pieces can be
swapped without touching this code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.auditor import WebsiteAuditor
from app.agents.base import AuditModule
from app.agents.email_generator import EmailGenerator
from app.agents.gbp import GBPAgent
from app.agents.llm_client import LLMClient, get_llm_client
from app.agents.social import SocialAgent
from app.agents.vision import VisionAgent
from app.business_providers.base import BusinessProvider
from app.business_providers.factory import get_provider
from app.config.logging import get_logger
from app.crawler.crawler import WebsiteCrawler
from app.database.repositories.audit_repo import AuditRepository
from app.database.repositories.business_repo import BusinessRepository
from app.database.repositories.lead_repo import LeadRepository, SuppressionRepository
from app.database.session import session_scope
from app.schemas.audit import AuditResult, WebsiteState
from app.schemas.business import Business, DiscoveryQuery
from app.schemas.competitor import CompetitorReport
from app.schemas.context import AuditContext, CrawlResult
from app.schemas.lead_score import LeadScore
from app.schemas.outreach import OutreachContent
from app.services.competitor import CompetitorService
from app.services.lead_scoring import LeadScorer
from app.services.scoring import apply_competitive_pressure, opportunity_from_results

log = get_logger(__name__)


@dataclass
class LeadOutcome:
    """Summary of processing one business (returned to the CLI / callers)."""

    business: Business
    state: WebsiteState
    opportunity_score: float
    audit_id: int | None = None
    notes: str = ""
    priority: str = ""
    has_draft: bool = False


@dataclass
class PipelineResult:
    outcomes: list[LeadOutcome] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = []
        for o in sorted(self.outcomes, key=lambda x: x.opportunity_score, reverse=True):
            draft = "✍ draft" if o.has_draft else "—"
            lines.append(
                f"  [{o.opportunity_score:5.1f}] {o.priority or '?':4s}  {o.business.name}  "
                f"— {o.state.value}  ({draft})"
            )
        return lines


class LeadPipeline:
    """Runs discovery through persistence for a batch of businesses."""

    def __init__(
        self,
        *,
        provider: BusinessProvider | None = None,
        crawler: WebsiteCrawler | None = None,
        modules: list[AuditModule] | None = None,
        llm_client: LLMClient | None = None,
        competitor_service: CompetitorService | None = None,
        scorer: LeadScorer | None = None,
        email_generator: EmailGenerator | None = None,
        generate_outreach: bool = True,
    ) -> None:
        self._provider = provider or get_provider()
        self._crawler = crawler or WebsiteCrawler()
        client = llm_client or get_llm_client()
        # Default audit modules: technical audit + visual (vision) analysis +
        # data-available-only GBP and social presence.
        self._modules = modules or [
            WebsiteAuditor(),
            VisionAgent(client=client),
            GBPAgent(),
            SocialAgent(),
        ]
        self._competitor_service = competitor_service
        self._scorer = scorer or LeadScorer()
        if email_generator is not None:
            self._email_generator: EmailGenerator | None = email_generator
        elif generate_outreach:
            self._email_generator = EmailGenerator(client=client)
        else:
            self._email_generator = None

    async def discover(self, query: DiscoveryQuery) -> list[Business]:
        businesses = await self._provider.search(query)
        log.info("pipeline.discovered", count=len(businesses), provider=self._provider.name)
        return businesses

    async def process_business(self, business: Business) -> LeadOutcome:
        crawl: CrawlResult = await self._crawler.crawl(business.website)
        ctx = AuditContext(business=business, crawl=crawl)

        results: dict[str, AuditResult] = {}
        for module in self._modules:
            result = await module.run(ctx)
            results[module.name] = result

        opportunity = opportunity_from_results(crawl.state, results)

        # Competitor analysis (optional) — compares the lead to nearby rivals and
        # measurably influences the opportunity score via competitive pressure.
        competitor_report: CompetitorReport | None = None
        if self._competitor_service is not None:
            lead_quality = self._quality_ratio(results.get("auditor"))
            competitor_report = await self._competitor_service.analyse(business, lead_quality)
            results["competitor"] = self._competitor_service.to_audit_result(competitor_report)
            opportunity = apply_competitive_pressure(
                opportunity, competitor_report.competitive_pressure
            )

        # Qualify the lead (aggregate everything into a LeadScore).
        lead_score = self._scorer.score(
            business=business,
            website_state=crawl.state,
            opportunity_score=opportunity,
            results=results,
            competitor=competitor_report,
        )

        # Draft outreach (never sent). Skipped if the contact is suppressed.
        draft, suppressed = await self._draft_outreach(
            business, lead_score, results, competitor_report
        )

        notes = self._combined_notes(results)
        audit_id, _ = await self._persist(
            business, crawl, results, opportunity, notes, lead_score, draft, suppressed
        )
        return LeadOutcome(
            business=business,
            state=crawl.state,
            opportunity_score=opportunity,
            audit_id=audit_id,
            notes=notes,
            priority=lead_score.priority.value,
            has_draft=draft is not None,
        )

    async def _draft_outreach(self, business, lead_score, results, competitor):
        """Generate an outreach draft unless the contact is on the suppression list."""
        if self._email_generator is None:
            return None, False
        async with session_scope() as session:
            suppressed = await SuppressionRepository(session).is_suppressed(
                email=business.email, phone=business.phone, website=business.website
            )
        if suppressed:
            log.info("outreach.suppressed", business=business.name)
            return None, True
        try:
            content = await self._email_generator.generate(
                business=business,
                lead_score=lead_score,
                results=results,
                competitor=competitor,
            )
            return content, False
        except Exception as exc:  # a draft failure must not sink the lead
            log.warning("outreach.generate_failed", business=business.name, error=str(exc))
            return None, False

    @staticmethod
    def _lawful_basis_note(business: Business) -> str:
        return (
            "Lawful basis: legitimate interest (Art. 6(1)(f) UK GDPR) for B2B marketing to a "
            f"business contact ({business.source_provider} data). PECR: corporate subscriber. "
            "Human approval required before sending; suppression list honoured; every template "
            "includes an unsubscribe option."
        )

    @staticmethod
    def _quality_ratio(result: AuditResult | None) -> float | None:
        if result is None:
            return None
        value, mx = result.total()
        return (value / mx) if mx else None

    @staticmethod
    def _combined_notes(results: dict[str, AuditResult]) -> str:
        parts = []
        for name in ("auditor", "vision"):
            r = results.get(name)
            if r and r.notes:
                parts.append(r.notes)
        return "  ".join(parts)

    async def _persist(
        self,
        business: Business,
        crawl: CrawlResult,
        results: dict[str, AuditResult],
        opportunity: float,
        notes: str,
        lead_score: LeadScore,
        draft: OutreachContent | None,
        suppressed: bool,
    ) -> tuple[int, int]:
        async with session_scope() as session:
            biz_repo = BusinessRepository(session)
            audit_repo = AuditRepository(session)
            lead_repo = LeadRepository(session)

            biz_record = await biz_repo.upsert(business)
            await session.flush()

            module_results = {name: r.model_dump() for name, r in results.items()}
            crawl_summary = crawl.model_dump(exclude={"html", "text", "links"})  # keep the row lean
            audit = await audit_repo.create(
                business_id=biz_record.id,
                website_state=crawl.state.value,
                final_url=crawl.final_url,
                opportunity_score=opportunity,
                module_results=module_results,
                crawl_summary=crawl_summary,
                notes=notes,
            )
            if crawl.desktop_screenshot:
                await audit_repo.add_screenshot(audit.id, "desktop", crawl.desktop_screenshot)
            if crawl.mobile_screenshot:
                await audit_repo.add_screenshot(audit.id, "mobile", crawl.mobile_screenshot)

            score_record = await lead_repo.create_score(
                business_id=biz_record.id,
                audit_id=audit.id,
                opportunity_score=lead_score.opportunity_score,
                priority=lead_score.priority.value,
                likelihood_of_purchase=lead_score.likelihood_of_purchase,
                estimated_budget=lead_score.estimated_budget,
                estimated_project_value=lead_score.estimated_project_value,
                summary=lead_score.summary,
                payload=lead_score.model_dump(),
            )
            if draft is not None:
                await lead_repo.add_draft(
                    lead_score_id=score_record.id,
                    subject=draft.subject,
                    email_body=draft.email_body,
                    follow_up=draft.follow_up,
                    linkedin_message=draft.linkedin_message,
                    lawful_basis_note=self._lawful_basis_note(business),
                    payload={**draft.model_dump(), "suppressed": suppressed},
                )
            return audit.id, score_record.id

    async def process_all(self, businesses: list[Business]) -> PipelineResult:
        result = PipelineResult()
        for business in businesses:
            try:
                outcome = await self.process_business(business)
                result.outcomes.append(outcome)
                log.info(
                    "pipeline.processed",
                    business=business.name,
                    state=outcome.state.value,
                    opportunity=outcome.opportunity_score,
                )
            except Exception as exc:  # one bad site must not sink the batch
                log.error("pipeline.business_failed", business=business.name, error=str(exc))
        return result

    async def run(self, query: DiscoveryQuery) -> PipelineResult:
        businesses = await self.discover(query)
        return await self.process_all(businesses)
