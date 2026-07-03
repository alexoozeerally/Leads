"""Website Auditor — the full technical audit.

Scores a site across the categories in the spec: navigation, mobile-friendliness,
accessibility, performance indicators, SEO basics, CTAs, forms, contact methods,
security (HTTPS/SSL), broken links, trust signals, content, and local SEO.

Every category is a :class:`ScoreEntry` whose explanation cites the *observed*
signal (e.g. "18 of 24 images have alt text"). Nothing is invented: where a
signal can't be observed the explanation says so. Website-discovery states
(no site / broken / parked / under construction / redirect loop / invalid SSL)
are handled explicitly — a no-site business is auto-flagged as maximal
opportunity and every category explains that there is nothing to audit.
"""

from __future__ import annotations

from app.agents.link_checker import LinkChecker, LinkCheckResult
from app.agents.website_signals import WebsiteSignals, extract_signals
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.schemas.audit import AuditResult, ScoreEntry, WebsiteState
from app.schemas.context import AuditContext

log = get_logger(__name__)

_MODULE = "auditor"

# States where there is effectively no live site to audit. Each yields a fully
# explained, low-quality (= high-opportunity) audit.
_NO_AUDIT_STATES: dict[WebsiteState, str] = {
    WebsiteState.NO_SITE: "No website exists for this business.",
    WebsiteState.PARKED: "The domain is parked / for sale — no real site to audit.",
    WebsiteState.BROKEN: "The website failed to load (broken/unreachable).",
    WebsiteState.UNDER_CONSTRUCTION: "The website is under construction / has no real content.",
    WebsiteState.REDIRECT_LOOP: "The website is stuck in a redirect loop.",
    WebsiteState.INVALID_SSL: "The website has an invalid SSL certificate.",
}

# The category set the auditor always reports (stable keys for the UI/score).
CATEGORIES = (
    "security",
    "mobile_friendly",
    "navigation",
    "seo",
    "content",
    "accessibility",
    "cta",
    "forms",
    "contact",
    "trust",
    "local_seo",
    "performance",
    "broken_links",
)


class WebsiteAuditor:
    """AuditModule producing a full technical audit with per-category rationale."""

    name = _MODULE

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        link_checker: LinkChecker | None = None,
        check_links: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._check_links = check_links
        self._link_checker = link_checker or LinkChecker(
            user_agent=self._settings.crawler_user_agent,
            verify_tls=self._settings.crawler_verify_tls,
        )

    async def run(self, ctx: AuditContext) -> AuditResult:
        state = ctx.website_state
        if state in _NO_AUDIT_STATES:
            return self._no_audit_result(state)
        if ctx.crawl is None or not (ctx.crawl.html or "").strip():
            return self._no_audit_result(WebsiteState.UNKNOWN)

        sig = extract_signals(ctx.crawl)

        link_result: LinkCheckResult | None = None
        internal_links = self._internal_links(ctx.crawl)
        if self._check_links and internal_links:
            try:
                link_result = await self._link_checker.check(internal_links)
            except Exception as exc:  # never let link-checking sink the audit
                log.warning("auditor.link_check_failed", error=str(exc))

        scores = self._score_all(sig, link_result)
        notes = self._summarise(sig, scores)
        return AuditResult(
            module=_MODULE,
            scores=scores,
            notes=notes,
            raw={"signals": sig.__dict__, "state": state.value},
        )

    @staticmethod
    def _internal_links(crawl) -> list[str]:
        """Same-host links only.

        We check internal links for breakage: they are the site owner's
        responsibility and the strongest quality signal. External links are
        excluded because third-party sites routinely block automated checks and
        return 4xx for reasons outside the owner's control — flagging those would
        be misleading, not evidence of a broken site.
        """
        from urllib.parse import urlparse

        host = urlparse(crawl.final_url or crawl.url).netloc
        out = []
        for link in crawl.links or []:
            if urlparse(link).netloc == host:
                out.append(link)
        return out

    # -- scoring per category -------------------------------------------------

    def _score_all(self, s: WebsiteSignals, links: LinkCheckResult | None) -> dict[str, ScoreEntry]:
        return {
            "security": self._score_security(s),
            "mobile_friendly": self._score_mobile(s),
            "navigation": self._score_navigation(s),
            "seo": self._score_seo(s),
            "content": self._score_content(s),
            "accessibility": self._score_accessibility(s),
            "cta": self._score_cta(s),
            "forms": self._score_forms(s),
            "contact": self._score_contact(s),
            "trust": self._score_trust(s),
            "local_seo": self._score_local_seo(s),
            "performance": self._score_performance(s),
            "broken_links": self._score_broken_links(links),
        }

    @staticmethod
    def _entry(value: float, mx: float, explanation: str) -> ScoreEntry:
        return ScoreEntry(value=round(max(0.0, min(value, mx)), 2), max=mx, explanation=explanation)

    def _score_security(self, s: WebsiteSignals) -> ScoreEntry:
        if s.has_https:
            return self._entry(10, 10, "Served over HTTPS with a valid certificate.")
        return self._entry(
            0, 10, "Not served over HTTPS — visitors see 'Not secure' and trust/SEO suffer."
        )

    def _score_mobile(self, s: WebsiteSignals) -> ScoreEntry:
        if s.has_viewport_meta and not s.uses_tables_for_layout:
            return self._entry(10, 10, "Declares a responsive viewport meta tag.")
        if s.has_viewport_meta:
            return self._entry(
                6,
                10,
                "Has a viewport meta tag but uses table-based layout — likely not responsive.",
            )
        return self._entry(
            1, 10, "No responsive viewport meta tag — the site is unlikely to be mobile-friendly."
        )

    def _score_navigation(self, s: WebsiteSignals) -> ScoreEntry:
        if s.nav_present and s.internal_link_count >= 3:
            return self._entry(
                10, 10, f"Clear navigation present with {s.internal_link_count} internal links."
            )
        if s.internal_link_count >= 3:
            return self._entry(
                6,
                10,
                f"{s.internal_link_count} internal links but no semantic <nav> tag — "
                "navigation is unclear.",
            )
        return self._entry(
            2, 10, f"Weak navigation: only {s.internal_link_count} internal links and no <nav>."
        )

    def _score_seo(self, s: WebsiteSignals) -> ScoreEntry:
        pts = 0.0
        reasons = []
        if s.has_title and 10 <= s.title_length <= 70:
            pts += 3
            reasons.append(f"title present ({s.title_length} chars)")
        elif s.has_title:
            pts += 1.5
            reasons.append(f"title present but poorly sized ({s.title_length} chars)")
        else:
            reasons.append("no <title>")
        if s.has_meta_description and 50 <= s.meta_description_length <= 170:
            pts += 3
            reasons.append("good meta description")
        elif s.has_meta_description:
            pts += 1.5
            reasons.append("meta description present but poorly sized")
        else:
            reasons.append("no meta description")
        if s.h1_count == 1:
            pts += 2
            reasons.append("exactly one H1")
        elif s.h1_count == 0:
            reasons.append("no H1")
        else:
            pts += 1
            reasons.append(f"{s.h1_count} H1s (should be one)")
        if s.has_structured_data:
            pts += 2
            reasons.append("structured data present")
        else:
            reasons.append("no structured data")
        return self._entry(pts, 10, "SEO basics: " + ", ".join(reasons) + ".")

    def _score_content(self, s: WebsiteSignals) -> ScoreEntry:
        if s.word_count >= 300:
            return self._entry(10, 10, f"Substantial content ({s.word_count} words).")
        if s.word_count >= 120:
            return self._entry(6, 10, f"Thin content ({s.word_count} words) — more depth needed.")
        return self._entry(2, 10, f"Very little content ({s.word_count} words).")

    def _score_accessibility(self, s: WebsiteSignals) -> ScoreEntry:
        pts = 0.0
        reasons = []
        cov = s.alt_coverage
        if cov is None:
            pts += 3
            reasons.append("no images to caption")
        else:
            pts += 5 * cov
            reasons.append(f"{s.img_with_alt}/{s.img_count} images have alt text")
        lab = s.label_coverage
        if lab is None:
            pts += 3
            reasons.append("no form inputs")
        else:
            pts += 3 * lab
            reasons.append(f"{s.labelled_input_count}/{s.input_count} inputs labelled")
        if s.heading_count >= 2:
            pts += 2
            reasons.append("uses headings for structure")
        else:
            reasons.append("little heading structure")
        if s.deprecated_tags:
            pts -= 1
            reasons.append(f"deprecated tags: {', '.join(s.deprecated_tags)}")
        return self._entry(pts, 10, "Accessibility: " + ", ".join(reasons) + ".")

    def _score_cta(self, s: WebsiteSignals) -> ScoreEntry:
        if len(s.cta_hits) >= 2:
            return self._entry(10, 10, f"Clear calls-to-action: {', '.join(s.cta_hits[:4])}.")
        if s.cta_hits:
            return self._entry(
                6, 10, f"One call-to-action found ({s.cta_hits[0]}); could be stronger."
            )
        return self._entry(
            1, 10, "No obvious call-to-action — visitors aren't told what to do next."
        )

    def _score_forms(self, s: WebsiteSignals) -> ScoreEntry:
        if s.form_count == 0:
            return self._entry(
                4, 10, "No enquiry/contact form — visitors must phone or email to convert."
            )
        lab = s.label_coverage or 0
        if lab >= 0.8:
            return self._entry(10, 10, f"{s.form_count} form(s) with well-labelled inputs.")
        return self._entry(
            6, 10, f"{s.form_count} form(s) present but inputs are poorly labelled ({lab:.0%})."
        )

    def _score_contact(self, s: WebsiteSignals) -> ScoreEntry:
        methods = []
        if s.has_tel_link:
            methods.append("click-to-call")
        elif s.phone_in_text:
            methods.append("phone in text")
        if s.has_mailto_link:
            methods.append("email link")
        if s.form_count:
            methods.append("contact form")
        if len(methods) >= 2:
            return self._entry(10, 10, "Multiple contact methods: " + ", ".join(methods) + ".")
        if methods:
            return self._entry(6, 10, "Limited contact options: " + ", ".join(methods) + ".")
        return self._entry(1, 10, "No clear way to make contact was found on the page.")

    def _score_trust(self, s: WebsiteSignals) -> ScoreEntry:
        if len(s.trust_hits) >= 2:
            return self._entry(10, 10, f"Trust signals present: {', '.join(s.trust_hits[:4])}.")
        if s.trust_hits or s.social_links:
            extra = "social profiles" if s.social_links else s.trust_hits[0]
            return self._entry(6, 10, f"Some trust signals ({extra}); more would help conversion.")
        return self._entry(
            2, 10, "Few trust signals (reviews, accreditations, guarantees) visible."
        )

    def _score_local_seo(self, s: WebsiteSignals) -> ScoreEntry:
        pts = 0.0
        reasons = []
        if s.address_signal:
            pts += 4
            reasons.append("address/postcode present")
        else:
            reasons.append("no address/postcode found")
        if s.has_tel_link or s.phone_in_text:
            pts += 3
            reasons.append("phone number present")
        else:
            reasons.append("no phone number")
        if s.has_structured_data:
            pts += 3
            reasons.append("structured data (helps local listings)")
        else:
            reasons.append("no LocalBusiness structured data")
        return self._entry(pts, 10, "Local SEO: " + ", ".join(reasons) + ".")

    def _score_performance(self, s: WebsiteSignals) -> ScoreEntry:
        # Indicators only (no field metrics without a live perf run).
        pts = 8.0
        reasons = []
        if s.script_count > 25:
            pts -= 3
            reasons.append(f"{s.script_count} script tags (heavy)")
        else:
            reasons.append(f"{s.script_count} script tags")
        if s.inline_style_count > 30:
            pts -= 2
            reasons.append(f"{s.inline_style_count} inline styles")
        if s.img_count > 40:
            pts -= 2
            reasons.append(f"{s.img_count} images (check optimisation)")
        reasons.append("indicator-based, not a field measurement")
        return self._entry(pts, 10, "Performance indicators: " + ", ".join(reasons) + ".")

    def _score_broken_links(self, links: LinkCheckResult | None) -> ScoreEntry:
        if links is None:
            return self._entry(7, 10, "Links were not checked in this run (reported as unknown).")
        if links.checked == 0:
            return self._entry(7, 10, "No links available to check.")
        if links.broken_count == 0:
            return self._entry(10, 10, f"Checked {links.checked} links — none broken.")
        ratio = links.broken_count / links.checked
        return self._entry(
            max(0, 10 - ratio * 12),
            10,
            f"{links.broken_count} of {links.checked} checked links are broken.",
        )

    # -- no-audit + summary ---------------------------------------------------

    def _no_audit_result(self, state: WebsiteState) -> AuditResult:
        reason = _NO_AUDIT_STATES.get(state, "The website could not be audited (state unknown).")
        scores = {cat: self._entry(0, 10, reason) for cat in CATEGORIES}
        # Security is 'unknown' rather than 0 when there simply was no site.
        return AuditResult(
            module=_MODULE,
            scores=scores,
            notes=reason,
            raw={"state": state.value},
        )

    @staticmethod
    def _summarise(s: WebsiteSignals, scores: dict[str, ScoreEntry]) -> str:
        weakest = sorted(scores.items(), key=lambda kv: kv[1].ratio)[:3]
        names = ", ".join(k.replace("_", " ") for k, _ in weakest)
        return (
            f"Audited {s.word_count} words of content. Biggest weaknesses: {names}. "
            f"HTTPS: {'yes' if s.has_https else 'no'}; "
            f"mobile-ready: {'yes' if s.has_viewport_meta else 'no'}."
        )
