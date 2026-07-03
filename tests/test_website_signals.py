"""Tests for deterministic signal extraction from crawled HTML."""

from __future__ import annotations

from app.agents.website_signals import extract_signals
from app.schemas.context import CrawlResult

_GOOD_HTML = """
<!doctype html><html><head>
<title>Acme Plumbers — Emergency Plumbing in Bristol</title>
<meta name="description" content="Fast, friendly emergency plumbers in Bristol. Free quote.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/favicon.ico">
<script type="application/ld+json">{"@type":"LocalBusiness"}</script>
</head><body>
<nav><a href="/services">Services</a><a href="/about">About</a><a href="/contact">Contact</a></nav>
<h1>Emergency Plumbers in Bristol</h1>
<h2>Why choose us</h2>
<p>We are rated 5 stars on Trustpilot and fully insured. Book now for a free quote.
Our team has 20 years of experience serving 12 Corn Street, Bristol BS1 1HQ.</p>
<img src="team.jpg" alt="Our friendly team">
<form><label for="name">Name</label><input id="name" type="text"></form>
<a href="tel:01179000000">Call us</a>
<a href="mailto:hi@acme.example">Email</a>
<a href="https://facebook.com/acme">Facebook</a>
</body></html>
"""

_POOR_HTML = """
<html><head><title>welcome</title></head>
<body bgcolor="#000"><center><font size="7">MY SHOP</font>
<marquee>welcome!!!</marquee>
<img src="x.gif">
<table><tr><td>some text here</td></tr></table>
</center></body></html>
"""


def _crawl(html: str, url: str = "https://acme.example/") -> CrawlResult:
    return CrawlResult(url=url, final_url=url, html=html, has_https=True)


def test_extracts_positive_signals():
    s = extract_signals(_crawl(_GOOD_HTML))
    assert s.has_https and s.has_viewport_meta and s.has_favicon
    assert s.has_title and s.has_meta_description
    assert s.h1_count == 1 and s.heading_count >= 2
    assert s.nav_present and s.internal_link_count >= 3
    assert s.img_count == 1 and s.img_with_alt == 1
    assert s.form_count == 1 and s.labelled_input_count == 1
    assert s.has_tel_link and s.has_mailto_link
    assert "facebook.com/acme" in s.social_links[0]
    assert s.has_structured_data
    assert s.address_signal  # postcode present
    assert "book" in s.cta_hits
    assert any("rated" in t or "insured" in t for t in s.trust_hits)


def test_alt_and_label_coverage():
    s = extract_signals(_crawl(_GOOD_HTML))
    assert s.alt_coverage == 1.0
    assert s.label_coverage == 1.0


def test_extracts_poor_signals():
    s = extract_signals(_crawl(_POOR_HTML, url="http://shop.example/"))
    assert not s.has_viewport_meta
    assert not s.has_meta_description
    assert s.img_with_alt == 0
    assert "font" in s.deprecated_tags and "marquee" in s.deprecated_tags
    assert s.cta_hits == []


def test_empty_html_is_safe():
    s = extract_signals(CrawlResult(url="x", html=""))
    assert s.word_count == 0
    assert s.alt_coverage is None
    assert s.label_coverage is None
