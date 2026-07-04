"""Tests for the OSM/Overpass provider — mocked HTTP, no network.

The provider first geocodes the location via Nominatim (GET), then queries
Overpass (POST). The mock transport routes by URL/method.
"""

from __future__ import annotations

import httpx
import pytest

from app.business_providers.osm_provider import OSMBusinessProvider
from app.exceptions import ProviderError
from app.schemas.business import DiscoveryQuery

_OVERPASS_RESPONSE = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 51.45,
            "lon": -2.59,
            "tags": {
                "name": "Corn Street Plumbers",
                "craft": "plumber",
                "phone": "0117 555 0000",
                "website": "https://cornstplumbers.example",
                "addr:postcode": "BS1 1HQ",
                "contact:facebook": "https://facebook.com/example",
            },
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 51.46, "lon": -2.60},
            "tags": {"craft": "plumber"},  # no name -> skipped
        },
    ]
}

_NOMINATIM_RESPONSE = [{"lat": "51.4545", "lon": "-2.5879"}]


def _client(
    *, overpass=_OVERPASS_RESPONSE, nominatim=_NOMINATIM_RESPONSE, overpass_status=200
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host or "nominatim" in str(request.url):
            return httpx.Response(200, json=nominatim)
        return httpx.Response(overpass_status, json=overpass)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _provider(client: httpx.AsyncClient) -> OSMBusinessProvider:
    return OSMBusinessProvider(
        "https://overpass.example/api",
        nominatim_url="https://nominatim.example/search",
        user_agent="TestBot/1.0 (contact: test@example.com)",
        client=client,
    )


@pytest.mark.asyncio
async def test_geocodes_then_parses_named_elements():
    provider = _provider(_client())
    results = await provider.search(DiscoveryQuery(industry="plumber", postcode="BS1 1AA"))
    assert len(results) == 1
    biz = results[0]
    assert biz.name == "Corn Street Plumbers"
    assert biz.phone == "0117 555 0000"
    assert biz.social_links == {"facebook": "https://facebook.com/example"}
    assert biz.source_provider == "osm"
    assert biz.data_confidence == 0.7


@pytest.mark.asyncio
async def test_requires_location_anchor():
    provider = _provider(_client())
    with pytest.raises(ProviderError):
        await provider.search(DiscoveryQuery(industry="plumber"))


@pytest.mark.asyncio
async def test_geocode_no_result_raises():
    provider = _provider(_client(nominatim=[]))
    with pytest.raises(ProviderError):
        await provider.search(DiscoveryQuery(industry="plumber", postcode="ZZ99 9ZZ"))


@pytest.mark.asyncio
async def test_overpass_http_error_becomes_provider_error():
    provider = _provider(_client(overpass_status=500))
    with pytest.raises(ProviderError):
        await provider.search(DiscoveryQuery(industry="plumber", town="Bristol"))


@pytest.mark.asyncio
async def test_sends_user_agent_header():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[str(request.url)] = request.headers.get("user-agent", "")
        if "nominatim" in str(request.url):
            return httpx.Response(200, json=_NOMINATIM_RESPONSE)
        return httpx.Response(200, json=_OVERPASS_RESPONSE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = _provider(client)
    await provider.search(DiscoveryQuery(industry="plumber", postcode="BS1 1AA"))
    # Every request (geocode + overpass) carries our truthful User-Agent.
    assert seen and all("TestBot" in ua for ua in seen.values())
