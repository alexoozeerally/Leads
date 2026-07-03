"""Tests for the OSM/Overpass provider — mocked HTTP, no network."""

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


def _mock_client(payload: dict, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_parses_named_elements_and_skips_unnamed():
    provider = OSMBusinessProvider(
        "https://overpass.example/api", client=_mock_client(_OVERPASS_RESPONSE)
    )
    results = await provider.search(DiscoveryQuery(industry="plumber", postcode="BS1", limit=25))
    assert len(results) == 1
    biz = results[0]
    assert biz.name == "Corn Street Plumbers"
    assert biz.phone == "0117 555 0000"
    assert biz.social_links == {"facebook": "https://facebook.com/example"}
    assert biz.source_provider == "osm"
    assert biz.data_confidence == 0.7


@pytest.mark.asyncio
async def test_requires_location_anchor():
    provider = OSMBusinessProvider("https://overpass.example/api", client=_mock_client({}))
    with pytest.raises(ProviderError):
        await provider.search(DiscoveryQuery(industry="plumber", limit=25))


@pytest.mark.asyncio
async def test_http_error_becomes_provider_error():
    provider = OSMBusinessProvider(
        "https://overpass.example/api", client=_mock_client({}, status=500)
    )
    with pytest.raises(ProviderError):
        await provider.search(DiscoveryQuery(industry="plumber", town="Bristol", limit=25))
