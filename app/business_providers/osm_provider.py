"""OpenStreetMap / Overpass API provider.

Data source / ToS: OpenStreetMap via the Overpass API. OSM data is licensed under
the Open Database Licence (ODbL) — you must attribute "© OpenStreetMap
contributors" wherever you display or redistribute it. Overpass is a shared free
service: query sparingly, cache, and never hammer it. This provider only reads
what OSM publishes and leaves anything absent as ``None`` — it invents nothing.
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


class OSMBusinessProvider(BusinessProvider):
    name = "osm"

    def __init__(self, overpass_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._url = overpass_url
        self._client = client

    def _tag_filter(self, industry: str) -> str:
        key = industry.strip().lower()
        for needle, tag in _INDUSTRY_TAGS.items():
            if needle in key:
                return tag
        # Fall back to a name search so unknown industries still return something.
        return f'["name"~"{industry}",i]'

    def _build_query(self, query: DiscoveryQuery) -> str:
        """Build an Overpass QL query around a postcode/area within a radius."""
        tag = self._tag_filter(query.industry)
        area = query.postcode or query.town or query.county or ""
        # Use Nominatim-style area name search via Overpass 'area' when we have one;
        # otherwise a bounded search is not possible, so require an anchor.
        if not area:
            raise ProviderError(
                "OSM provider needs a postcode, town or county to anchor the search."
            )
        return f"""
        [out:json][timeout:25];
        area["name"~"{area}",i]->.a;
        (
          node{tag}(area.a);
          way{tag}(area.a);
        );
        out center {query.limit};
        """.strip()
        # NB: query.radius_km is honoured via an 'around' query in a future
        # revision once we resolve the anchor to coordinates.

    async def _post_with_retry(self, client: httpx.AsyncClient, overpass_query: str) -> dict:
        """POST to Overpass with bounded exponential-backoff retries (transient errors)."""
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=15),
            reraise=True,
        )
        async def _call() -> dict:
            resp = await client.post(self._url, data={"data": overpass_query})
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
        overpass_query = self._build_query(query)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            payload = await self._post_with_retry(client, overpass_query)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Overpass request failed: {exc}") from exc
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
        log.info("osm.search", area=query.postcode or query.town, returned=len(businesses))
        return businesses
