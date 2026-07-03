"""Vision analyser agent.

Takes the desktop + mobile home-page screenshots and evaluates design quality:
modernity, professionalism, typography, whitespace, branding, trust, colour,
hierarchy, image quality, consistency — plus an estimated site age and an overall
first-impression score. Output is validated JSON; every score carries an
explanation. When there is no site to look at, it returns a maximal opportunity
signal rather than inventing an assessment.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.llm_client import ImageInput, LLMClient, get_llm_client
from app.agents.prompt_loader import load_prompt
from app.agents.runner import generate_structured
from app.config.logging import get_logger
from app.schemas.audit import AuditResult, ScoreEntry, WebsiteState
from app.schemas.context import AuditContext

log = get_logger(__name__)

_MODULE = "vision"

# Design dimensions the model scores (each 0-10). Kept here so the mapping to
# ScoreEntry is explicit and testable.
VISION_DIMENSIONS = (
    "modernity",
    "professionalism",
    "typography",
    "whitespace",
    "branding",
    "trust",
    "colour",
    "hierarchy",
    "image_quality",
    "consistency",
)


class DimensionScore(BaseModel):
    score: float = Field(..., ge=0, le=10)
    explanation: str = Field(..., min_length=1)


class VisionAnalysis(BaseModel):
    """Validated structured output from the vision model."""

    first_impression: float = Field(..., ge=0, le=10)
    estimated_site_age_years: float | None = Field(default=None, ge=0)
    dimensions: dict[str, DimensionScore]
    summary: str = Field(..., min_length=1)


class VisionAgent:
    """AuditModule that scores a site's visual design from screenshots."""

    name = _MODULE

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client or get_llm_client()

    async def run(self, ctx: AuditContext) -> AuditResult:
        crawl = ctx.crawl
        state = ctx.website_state

        # No usable site -> maximal design opportunity, stated honestly.
        if state in (WebsiteState.NO_SITE, WebsiteState.PARKED) or crawl is None:
            return self._no_site_result(state)
        if not crawl.desktop_screenshot:
            return self._no_screenshot_result(state)

        images = [ImageInput(path=crawl.desktop_screenshot, label="desktop")]
        if crawl.mobile_screenshot:
            images.append(ImageInput(path=crawl.mobile_screenshot, label="mobile"))

        system = load_prompt("vision")
        user = self._build_user_prompt(ctx)
        analysis = await generate_structured(
            self._client, system=system, user=user, schema=VisionAnalysis, images=images
        )
        return self._to_audit_result(analysis)

    def _build_user_prompt(self, ctx: AuditContext) -> str:
        biz = ctx.business
        return (
            f"Business: {biz.name}\n"
            f"Category: {biz.category or 'unknown'}\n"
            f"Website: {biz.website or 'unknown'}\n"
            "Two screenshots follow (desktop, then mobile if present). "
            "Assess the visual design as instructed and return the JSON object."
        )

    def _to_audit_result(self, analysis: VisionAnalysis) -> AuditResult:
        scores: dict[str, ScoreEntry] = {}
        for dim in VISION_DIMENSIONS:
            entry = analysis.dimensions.get(dim)
            if entry is None:
                scores[dim] = ScoreEntry(
                    value=0, max=10, explanation="Model did not assess this dimension."
                )
            else:
                scores[dim] = ScoreEntry(value=entry.score, max=10, explanation=entry.explanation)
        scores["first_impression"] = ScoreEntry(
            value=analysis.first_impression,
            max=10,
            explanation=analysis.summary,
        )
        return AuditResult(
            module=_MODULE,
            scores=scores,
            notes=analysis.summary,
            raw=analysis.model_dump(),
        )

    def _no_site_result(self, state: WebsiteState) -> AuditResult:
        reason = (
            "No website found for this business."
            if state == WebsiteState.NO_SITE
            else "The domain is parked / for sale — no real site to evaluate."
        )
        # Design quality is effectively zero; opportunity is maximal.
        scores = {dim: ScoreEntry(value=0, max=10, explanation=reason) for dim in VISION_DIMENSIONS}
        scores["first_impression"] = ScoreEntry(value=0, max=10, explanation=reason)
        return AuditResult(module=_MODULE, scores=scores, notes=reason, raw={"state": state.value})

    def _no_screenshot_result(self, state: WebsiteState) -> AuditResult:
        reason = f"Site state '{state.value}' — no screenshot captured, so design is unknown."
        scores = {dim: ScoreEntry(value=0, max=10, explanation=reason) for dim in VISION_DIMENSIONS}
        scores["first_impression"] = ScoreEntry(value=0, max=10, explanation=reason)
        return AuditResult(module=_MODULE, scores=scores, notes=reason, raw={"state": state.value})
