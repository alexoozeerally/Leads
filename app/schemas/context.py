"""``AuditContext`` — the input every :class:`AuditModule` receives.

It carries everything an agent might need: the business, the crawl result (if
any), and screenshot paths. Agents read only what they need and never require
fields to be populated — absent data is handled explicitly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.audit import WebsiteState
from app.schemas.business import Business


class CrawlResult(BaseModel):
    """What the crawler observed for one website."""

    url: str
    final_url: str | None = None
    state: WebsiteState = WebsiteState.UNKNOWN
    status_code: int | None = None
    html: str | None = None
    text: str | None = None
    title: str | None = None
    meta_description: str | None = None
    has_https: bool | None = None
    ssl_valid: bool | None = None
    robots_allowed: bool | None = None
    load_ms: int | None = None
    links: list[str] = Field(default_factory=list)
    desktop_screenshot: str | None = None
    mobile_screenshot: str | None = None
    error: str | None = None


class AuditContext(BaseModel):
    """Immutable-ish bundle passed to every audit module's ``run``."""

    business: Business
    crawl: CrawlResult | None = None
    extras: dict = Field(default_factory=dict, description="Cross-agent scratch space.")

    @property
    def website_state(self) -> WebsiteState:
        return self.crawl.state if self.crawl else WebsiteState.NO_SITE
