"""The normalised ``Business`` contract and its discovery query.

Every business provider must emit ``Business`` objects. Unknown fields stay
``None`` — a provider never invents data it did not observe.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryQuery(BaseModel):
    """Parameters describing which businesses to discover.

    Providers translate this into their own native query. Not every provider
    honours every field (e.g. a CSV provider ignores ``radius_km``); providers
    document what they support.
    """

    model_config = ConfigDict(frozen=True)

    industry: str = Field(..., description="Target industry/category, e.g. 'plumber'.")
    town: str | None = None
    county: str | None = None
    postcode: str | None = None
    radius_km: float = Field(default=5.0, ge=0)
    limit: int = Field(default=25, ge=1, le=500)


class Business(BaseModel):
    """Normalised shape every provider emits and the rest of the app consumes.

    Optional fields that are unknown MUST remain ``None``. ``data_confidence``
    expresses how much the provider trusts this record (0–1).
    """

    name: str
    category: str | None = None
    address: str | None = None
    postcode: str | None = None
    phone: str | None = None
    website: str | None = None
    email: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    opening_hours: str | None = None
    social_links: dict[str, str] = Field(default_factory=dict)
    latitude: float | None = None
    longitude: float | None = None
    source_provider: str = Field(..., description="Which provider produced this record.")
    source_url: str | None = None
    data_confidence: float = Field(default=1.0, ge=0, le=1)

    def dedupe_key(self) -> str:
        """A stable key for de-duplicating the same business across providers.

        Prefers website host, then phone, then name+postcode.
        """
        if self.website:
            host = self.website.lower().replace("https://", "").replace("http://", "")
            return "site:" + host.split("/")[0].removeprefix("www.")
        if self.phone:
            return "tel:" + "".join(ch for ch in self.phone if ch.isdigit())
        pc = (self.postcode or "").replace(" ", "").lower()
        return f"name:{self.name.strip().lower()}|{pc}"
