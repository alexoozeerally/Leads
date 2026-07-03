"""Polite Playwright crawler.

Fetches and renders a business website, classifies its state (ok / no-site /
broken / parked / redirect loop / invalid SSL / under construction), extracts
text/metadata/links, and captures desktop + mobile screenshots.

Compliance: respects robots.txt, sends a truthful identifying User-Agent,
rate-limits per host, and times out gracefully.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.crawler.politeness import RateLimiter, RobotsCache
from app.schemas.audit import WebsiteState
from app.schemas.context import CrawlResult

log = get_logger(__name__)


def _autodetect_chromium() -> str | None:
    """Return a pre-installed Chromium path if the managed one exists."""
    candidate = Path("/opt/pw-browsers/chromium")
    return str(candidate) if candidate.exists() else None


_PARKED_MARKERS = (
    "domain is for sale",
    "buy this domain",
    "parked",
    "this domain may be for sale",
    "godaddy",
    "sedoparking",
)
_CONSTRUCTION_MARKERS = (
    "under construction",
    "coming soon",
    "site is being built",
    "launching soon",
)


class WebsiteCrawler:
    """Renders one website and returns a :class:`CrawlResult`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._rate = RateLimiter(self._settings.crawler_rate_limit_per_host)
        self._robots = RobotsCache(
            self._settings.crawler_user_agent,
            respect=self._settings.crawler_respect_robots,
            verify_tls=self._settings.crawler_verify_tls,
        )
        self._shot_dir = Path(self._settings.screenshot_dir)
        self._shot_dir.mkdir(parents=True, exist_ok=True)

    def _launch_kwargs(self) -> dict:
        """Browser launch options, honouring an external Chromium + proxy."""
        kwargs: dict = {"headless": True}
        exe = self._settings.playwright_executable_path or _autodetect_chromium()
        if exe:
            kwargs["executable_path"] = exe
        if self._settings.crawler_proxy:
            kwargs["proxy"] = {"server": self._settings.crawler_proxy}
        return kwargs

    @staticmethod
    def _normalise_url(url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "https://" + url
        return url

    @staticmethod
    def _slug(url: str) -> str:
        """A filesystem-safe, URL-unique slug for screenshot filenames."""
        parsed = urlparse(url)
        base = f"{parsed.netloc}{parsed.path}".lower()
        slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "site"
        digest = hashlib.sha1(url.encode()).hexdigest()[:8]
        return f"{slug[:60]}-{digest}"

    def _classify_body(self, text: str, title: str | None) -> WebsiteState | None:
        low = f"{title or ''} {text}".lower()
        if any(m in low for m in _PARKED_MARKERS):
            return WebsiteState.PARKED
        if any(m in low for m in _CONSTRUCTION_MARKERS) and len(text.strip()) < 800:
            return WebsiteState.UNDER_CONSTRUCTION
        return None

    async def crawl(self, website: str | None) -> CrawlResult:
        if not website or not website.strip():
            return CrawlResult(url="", state=WebsiteState.NO_SITE)

        url = self._normalise_url(website.strip())
        host = urlparse(url).netloc

        if not await self._robots.allowed(url):
            log.info("crawl.robots_disallow", url=url)
            return CrawlResult(
                url=url, state=WebsiteState.UNKNOWN, error="Disallowed by robots.txt"
            )

        await self._rate.acquire(host)
        return await self._render(url)

    async def _render(self, url: str) -> CrawlResult:
        # Imported lazily so the package imports without Playwright installed.
        from playwright.async_api import async_playwright

        result = CrawlResult(url=url)
        timeout_ms = int(self._settings.crawler_timeout_seconds * 1000)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**self._launch_kwargs())
                context = await browser.new_context(
                    user_agent=self._settings.crawler_user_agent,
                    viewport={"width": 1366, "height": 900},
                    # When verifying TLS, a bad cert surfaces as a navigation
                    # error and is classified as INVALID_SSL below.
                    ignore_https_errors=not self._settings.crawler_verify_tls,
                )
                page = await context.new_page()
                try:
                    response = await page.goto(
                        url, wait_until="domcontentloaded", timeout=timeout_ms
                    )
                except Exception as exc:  # navigation/SSL/timeout failures
                    await browser.close()
                    return self._classify_navigation_error(url, exc)

                result.status_code = response.status if response else None
                result.final_url = page.url
                result.has_https = page.url.startswith("https://")
                result.ssl_valid = result.has_https  # reached over TLS without hard error

                html = await page.content()
                title = await page.title()
                result.html = html
                result.title = title
                result.load_ms = None

                soup = BeautifulSoup(html, "html.parser")
                meta = soup.find("meta", attrs={"name": "description"})
                result.meta_description = meta.get("content") if meta else None
                text = soup.get_text(separator=" ", strip=True)
                result.text = text[:20000]
                result.links = self._extract_links(soup, page.url)

                # Screenshots (desktop already sized; mobile via a second viewport).
                slug = self._slug(url)
                desktop_path = self._shot_dir / f"{slug}-desktop.png"
                await page.screenshot(path=str(desktop_path), full_page=False)
                result.desktop_screenshot = str(desktop_path)

                await page.set_viewport_size({"width": 390, "height": 844})
                mobile_path = self._shot_dir / f"{slug}-mobile.png"
                await page.screenshot(path=str(mobile_path), full_page=False)
                result.mobile_screenshot = str(mobile_path)

                await browser.close()

            result.state = self._final_state(result)
        except Exception as exc:  # pragma: no cover - environment/browser failure
            log.warning("crawl.render_failed", url=url, error=str(exc))
            result.state = WebsiteState.BROKEN
            result.error = str(exc)
        return result

    def _final_state(self, result: CrawlResult) -> WebsiteState:
        if result.status_code and result.status_code >= 500:
            return WebsiteState.BROKEN
        if result.status_code and result.status_code >= 400:
            return WebsiteState.BROKEN
        body_state = self._classify_body(result.text or "", result.title)
        if body_state:
            return body_state
        if not (result.text or "").strip():
            return WebsiteState.UNDER_CONSTRUCTION
        return WebsiteState.OK

    def _classify_navigation_error(self, url: str, exc: Exception) -> CrawlResult:
        msg = str(exc).lower()
        state = WebsiteState.BROKEN
        if "err_too_many_redirects" in msg or "redirect" in msg:
            state = WebsiteState.REDIRECT_LOOP
        elif "ssl" in msg or "cert" in msg or "err_cert" in msg:
            state = WebsiteState.INVALID_SSL
        elif "name_not_resolved" in msg or "enotfound" in msg or "err_connection" in msg:
            state = WebsiteState.BROKEN
        log.info("crawl.nav_error", url=url, state=state.value, error=str(exc)[:200])
        return CrawlResult(url=url, state=state, error=str(exc)[:500])

    @staticmethod
    def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if href.startswith(("http://", "https://")) and href not in seen:
                seen.add(href)
                links.append(href)
            if len(links) >= 200:
                break
        return links
