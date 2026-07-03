"""Tests for crawler logic that doesn't require launching a browser.

The browser render path is exercised live by `run-sample`; here we unit-test the
pure classification/extraction logic so the suite stays fast and offline.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from app.crawler.crawler import WebsiteCrawler
from app.schemas.audit import WebsiteState
from app.schemas.context import CrawlResult


@pytest.fixture
def crawler(tmp_path, monkeypatch):
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    get_settings.cache_clear()
    c = WebsiteCrawler()
    get_settings.cache_clear()
    return c


def test_normalise_url_adds_scheme(crawler):
    assert crawler._normalise_url("acme.co.uk") == "https://acme.co.uk"
    assert crawler._normalise_url("http://acme.co.uk") == "http://acme.co.uk"


def test_slug_is_url_unique(crawler):
    a = crawler._slug("http://127.0.0.1:5000/modern.html")
    b = crawler._slug("http://127.0.0.1:5000/dated.html")
    assert a != b  # different pages -> different screenshot filenames


def test_final_state_ok_for_normal_page(crawler):
    r = CrawlResult(url="x", status_code=200, text="Welcome to our lovely shop with lots of info.")
    assert crawler._final_state(r) == WebsiteState.OK


def test_final_state_broken_for_5xx(crawler):
    r = CrawlResult(url="x", status_code=503, text="oops")
    assert crawler._final_state(r) == WebsiteState.BROKEN


def test_final_state_parked(crawler):
    r = CrawlResult(url="x", status_code=200, text="This domain is for sale. Buy this domain now.")
    assert crawler._final_state(r) == WebsiteState.PARKED


def test_final_state_under_construction(crawler):
    r = CrawlResult(url="x", status_code=200, text="Coming soon", title="Coming soon")
    assert crawler._final_state(r) == WebsiteState.UNDER_CONSTRUCTION


def test_classify_navigation_error_ssl(crawler):
    r = crawler._classify_navigation_error("https://x", Exception("net::ERR_CERT_DATE_INVALID"))
    assert r.state == WebsiteState.INVALID_SSL


def test_classify_navigation_error_redirect_loop(crawler):
    r = crawler._classify_navigation_error("https://x", Exception("net::ERR_TOO_MANY_REDIRECTS"))
    assert r.state == WebsiteState.REDIRECT_LOOP


def test_extract_links_absolute_and_deduped(crawler):
    html = (
        '<a href="/a">a</a><a href="/a">dup</a>'
        '<a href="https://other.example/b">b</a><a href="mailto:x@y.z">mail</a>'
    )
    soup = BeautifulSoup(html, "html.parser")
    links = WebsiteCrawler._extract_links(soup, "https://site.example/")
    assert "https://site.example/a" in links
    assert "https://other.example/b" in links
    assert links.count("https://site.example/a") == 1
    assert not any(link.startswith("mailto:") for link in links)


@pytest.mark.asyncio
async def test_crawl_no_website_returns_no_site(crawler):
    result = await crawler.crawl(None)
    assert result.state == WebsiteState.NO_SITE
    result2 = await crawler.crawl("   ")
    assert result2.state == WebsiteState.NO_SITE
