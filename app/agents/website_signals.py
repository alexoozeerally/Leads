"""Deterministic extraction of technical signals from a crawled page.

Everything here is *observed* from the HTML/crawl — nothing is inferred or
invented. The :class:`WebsiteAuditor` turns these signals into scored categories
with evidence-based explanations. Keeping extraction pure (HTML in, dataclass
out) makes it fully unit-testable offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.schemas.context import CrawlResult

_CTA_PHRASES = (
    "book",
    "get a quote",
    "get quote",
    "contact us",
    "call now",
    "buy now",
    "order",
    "enquire",
    "sign up",
    "subscribe",
    "get started",
    "request",
    "shop now",
    "learn more",
    "download",
)
_TRUST_PHRASES = (
    "review",
    "testimonial",
    "rated",
    "trustpilot",
    "google reviews",
    "accredited",
    "certified",
    "guarantee",
    "insured",
    "award",
    "member of",
    "years of experience",
    "established",
)
_SOCIAL_HOSTS = ("facebook.", "instagram.", "twitter.", "x.com", "linkedin.", "youtube.", "tiktok.")


@dataclass
class WebsiteSignals:
    """Observed technical facts about a page. Counts are exact; never guessed."""

    has_https: bool = False
    has_viewport_meta: bool = False
    has_title: bool = False
    title_length: int = 0
    has_meta_description: bool = False
    meta_description_length: int = 0
    h1_count: int = 0
    heading_count: int = 0
    nav_present: bool = False
    internal_link_count: int = 0
    external_link_count: int = 0
    img_count: int = 0
    img_with_alt: int = 0
    form_count: int = 0
    input_count: int = 0
    labelled_input_count: int = 0
    has_tel_link: bool = False
    has_mailto_link: bool = False
    phone_in_text: bool = False
    address_signal: bool = False
    cta_hits: list[str] = field(default_factory=list)
    trust_hits: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    has_structured_data: bool = False
    has_favicon: bool = False
    word_count: int = 0
    inline_style_count: int = 0
    script_count: int = 0
    stylesheet_count: int = 0
    uses_tables_for_layout: bool = False
    deprecated_tags: list[str] = field(default_factory=list)

    @property
    def alt_coverage(self) -> float | None:
        if self.img_count == 0:
            return None
        return self.img_with_alt / self.img_count

    @property
    def label_coverage(self) -> float | None:
        if self.input_count == 0:
            return None
        return self.labelled_input_count / self.input_count


_DEPRECATED_TAGS = ("font", "center", "marquee", "blink", "frameset", "big", "strike")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")


def extract_signals(crawl: CrawlResult) -> WebsiteSignals:
    """Parse a crawl result into observed technical signals."""
    sig = WebsiteSignals()
    html = crawl.html or ""
    if not html.strip():
        # Nothing rendered; still record HTTPS from the crawl if known.
        sig.has_https = bool(crawl.has_https)
        return sig

    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(crawl.final_url or crawl.url).netloc

    sig.has_https = bool(crawl.has_https) or (crawl.final_url or crawl.url).startswith("https://")

    title = soup.find("title")
    sig.has_title = title is not None and bool(title.get_text(strip=True))
    sig.title_length = len(title.get_text(strip=True)) if title else 0

    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = (meta_desc.get("content") or "").strip() if meta_desc else ""
    sig.has_meta_description = bool(desc)
    sig.meta_description_length = len(desc)

    sig.has_viewport_meta = soup.find("meta", attrs={"name": "viewport"}) is not None
    sig.has_favicon = soup.find("link", rel=lambda v: v and "icon" in v.lower()) is not None

    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    sig.heading_count = len(headings)
    sig.h1_count = len(soup.find_all("h1"))
    sig.nav_present = (
        soup.find("nav") is not None or soup.find(attrs={"role": "navigation"}) is not None
    )

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.startswith("tel:"):
            sig.has_tel_link = True
        elif low.startswith("mailto:"):
            sig.has_mailto_link = True
        elif low.startswith(("http://", "https://")):
            host = urlparse(href).netloc
            if any(s in host for s in _SOCIAL_HOSTS):
                sig.social_links.append(href)
            if base_host and host and host != base_host:
                sig.external_link_count += 1
            else:
                sig.internal_link_count += 1
        elif not low.startswith(("javascript:", "#")):
            sig.internal_link_count += 1

    imgs = soup.find_all("img")
    sig.img_count = len(imgs)
    sig.img_with_alt = sum(1 for i in imgs if i.get("alt") is not None and i.get("alt").strip())

    forms = soup.find_all("form")
    sig.form_count = len(forms)
    inputs = soup.find_all(["input", "textarea", "select"])
    real_inputs = [
        i for i in inputs if (i.get("type") or "text").lower() not in ("hidden", "submit")
    ]
    sig.input_count = len(real_inputs)
    labels = soup.find_all("label")
    labelled_ids = {label.get("for") for label in labels if label.get("for")}
    sig.labelled_input_count = sum(
        1
        for i in real_inputs
        if i.get("id") in labelled_ids
        or i.get("aria-label")
        or i.get("aria-labelledby")
        or i.get("placeholder")
    )

    text = crawl.text or soup.get_text(separator=" ", strip=True)
    low_text = text.lower()
    sig.word_count = len(text.split())
    sig.phone_in_text = _PHONE_RE.search(text) is not None
    sig.address_signal = any(
        k in low_text for k in ("street", "road", "avenue", "lane", "postcode")
    ) or bool(re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", text))

    sig.cta_hits = sorted({p for p in _CTA_PHRASES if p in low_text})
    sig.trust_hits = sorted({p for p in _TRUST_PHRASES if p in low_text})

    sig.has_structured_data = (
        soup.find("script", attrs={"type": "application/ld+json"}) is not None
        or soup.find(attrs={"itemscope": True}) is not None
    )

    sig.script_count = len(soup.find_all("script"))
    sig.stylesheet_count = len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower()))
    sig.inline_style_count = len(soup.find_all(style=True))
    sig.deprecated_tags = sorted({t.name for t in soup.find_all(_DEPRECATED_TAGS)})
    # Heuristic: many nested layout tables with no semantic role.
    tables = soup.find_all("table")
    sig.uses_tables_for_layout = len(tables) > 0 and sig.heading_count <= 1 and len(tables) >= 1

    return sig
