"""OpenStreetMap / Overpass API provider.

Data source / ToS: OpenStreetMap via the Overpass API + Nominatim geocoder. OSM
data is licensed under the Open Database Licence (ODbL) — you must attribute
"© OpenStreetMap contributors" wherever you display or redistribute it. Both
services are shared, free, and rate-limited: they REQUIRE a truthful identifying
User-Agent and ask you to query sparingly and cache. This provider only reads
what OSM publishes and leaves anything absent as ``None`` — it invents nothing.

Search strategy: the location (postcode/town/county) is geocoded to coordinates
via Nominatim, then Overpass runs an ``around:radius`` search — this works for
postcodes, which are not named areas in OSM.
"""

from __future__ import annotations

import httpx

from app.business_providers.base import BusinessProvider
from app.config.logging import get_logger
from app.exceptions import ProviderError
from app.schemas.business import Business, DiscoveryQuery

log = get_logger(__name__)

# Maps a free-text industry to an OSM tag filter. Extend as needed.
_INDUSTRY_TAGS: dict[str, str] = {
    "plumber": '["craft"="plumber"]',
    "barber": '["shop"="hairdresser"]',
    "hairdresser": '["shop"="hairdresser"]',
    "dentist": '["amenity"="dentist"]',
    "bakery": '["shop"="bakery"]',
    "cafe": '["amenity"="cafe"]',
    "restaurant": '["amenity"="restaurant"]',
    "electrician": '["craft"="electrician"]',
    "builder": '["craft"="builder"]',
    "bicycle": '["shop"="bicycle"]',
}

_DEFAULT_UA = "LeadFinderBot/0.1 (OpenStreetMap client; contact: hello@example.com)"


class OSMBusinessProvider(BusinessProvider):
    name = "osm"

    def __init__(
        self,
        overpass_url: str,
        *,
        nominatim_url: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = _DEFAULT_UA,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = overpass_url
        self._nominatim_url = nominatim_url
        self._user_agent = user_agent
        self._client = client

    def _tag_filter(self, industry: str) -> str:
        key = industry.strip().lower()
        for needle, tag in _INDUSTRY_TAGS.items():
            if needle in key:
                return tag
        # Fall back to a name search so unknown industries still return something.
        return f'["name"~"{industry}",i]'

    def _headers(self) -> dict[str, str]:
        # Both Nominatim and Overpass require a real User-Agent (they 403/406 without).
        return {"User-Agent": self._user_agent, "Accept": "application/json"}

    async def _geocode(self, client: httpx.AsyncClient, location: str) -> tuple[float, float]:
        """Resolve a location string to (lat, lon) via Nominatim."""
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
            reraise=True,
        )
        async def _call() -> list[dict]:
            resp = await client.get(
                self._nominatim_url,
                params={
                    "q": location,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "gb",
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

        results = await _call()
        if not results:
            raise ProviderError(f"Could not geocode location: {location!r}")
        return float(results[0]["lat"]), float(results[0]["lon"])

    def _build_query(self, query: DiscoveryQuery, lat: float, lon: float) -> str:
        """Build an Overpass QL 'around' query centred on (lat, lon)."""
        tag = self._tag_filter(query.industry)
        radius_m = int(query.radius_km * 1000)
        return (
            "[out:json][timeout:25];"
            "("
            f"node{tag}(around:{radius_m},{lat},{lon});"
            f"way{tag}(around:{radius_m},{lat},{lon});"
            ");"
            f"out center {query.limit};"
        )

    async def _post_with_retry(self, client: httpx.AsyncClient, overpass_query: str) -> dict:
        """POST to Overpass with bounded exponential-backoff retries (transient errors)."""
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
            reraise=True,
        )
        async def _call() -> dict:
            resp = await client.post(
                self._url, data={"data": overpass_query}, headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json()

        return await _call()

    def _element_to_business(self, el: dict) -> Business | None:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            return None  # unnamed nodes are useless as leads

        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")

        social = {}
        for net in ("facebook", "instagram", "twitter", "linkedin"):
            if f"contact:{net}" in tags:
                social[net] = tags[f"contact:{net}"]

        addr_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:city"),
        ]
        address = " ".join(p for p in addr_parts if p) or None

        return Business(
            name=name,
            category=tags.get("shop") or tags.get("craft") or tags.get("amenity"),
            address=address,
            postcode=tags.get("addr:postcode"),
            phone=tags.get("phone") or tags.get("contact:phone"),
            website=tags.get("website") or tags.get("contact:website"),
            email=tags.get("email") or tags.get("contact:email"),
            opening_hours=tags.get("opening_hours"),
            social_links=social,
            latitude=lat,
            longitude=lon,
            source_provider="osm",
            source_url=f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
            data_confidence=0.7,  # community data; treat as moderately confident
        )

    async def search(self, query: DiscoveryQuery) -> list[Business]:
        location = query.postcode or query.town or query.county
        if not location:
            raise ProviderError(
                "OSM provider needs a postcode, town or county to anchor the search."
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        try:
            lat, lon = await self._geocode(client, location)
            overpass_query = self._build_query(query, lat, lon)
            payload = await self._post_with_retry(client, overpass_query)
        except httpx.HTTPError as exc:
            raise ProviderError(f"OSM request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        businesses: list[Business] = []
        for el in payload.get("elements", []):
            biz = self._element_to_business(el)
            if biz is not None:
                businesses.append(biz)
            if len(businesses) >= query.limit:
                break
        log.info("osm.search", location=location, returned=len(businesses))
        return businesses
