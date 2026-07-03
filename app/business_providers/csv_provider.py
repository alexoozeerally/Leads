"""CSV import provider.

Data source / ToS: a local CSV supplied by the operator (e.g. exported from a
licensed dataset, a purchased list, or their own CRM). The operator is
responsible for having the right to use it. This provider fabricates nothing —
columns absent from the file map to ``None``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.business_providers.base import BusinessProvider
from app.config.logging import get_logger
from app.exceptions import ProviderError
from app.schemas.business import Business, DiscoveryQuery

log = get_logger(__name__)

# Recognised CSV headers -> Business fields. Missing columns simply stay None.
_FLOAT_FIELDS = {"rating", "latitude", "longitude", "data_confidence"}
_INT_FIELDS = {"review_count"}
_STR_FIELDS = {
    "name",
    "category",
    "address",
    "postcode",
    "phone",
    "website",
    "email",
    "opening_hours",
    "source_url",
}


class CSVBusinessProvider(BusinessProvider):
    name = "csv"

    def __init__(self, path: str, source: str = "csv") -> None:
        self._path = Path(path)
        self._source = source

    def _row_to_business(self, row: dict[str, str]) -> Business | None:
        data: dict = {"source_provider": self._source, "social_links": {}}
        for key, raw in row.items():
            if key is None:
                continue
            field = key.strip().lower()
            value = (raw or "").strip()
            if not value:
                continue  # unknown stays None — never invented
            try:
                if field in _FLOAT_FIELDS:
                    data[field] = float(value)
                elif field in _INT_FIELDS:
                    data[field] = int(value)
                elif field in _STR_FIELDS:
                    data[field] = value
            except ValueError:
                log.warning("csv.bad_value", field=field, value=value)
        if "name" not in data:
            return None
        return Business(**data)

    @staticmethod
    def _outward_code(postcode: str | None) -> str:
        """The UK postcode 'outward code' (area+district), e.g. 'BS8 2QN' -> 'bs8'."""
        if not postcode:
            return ""
        return postcode.strip().split(" ")[0].lower()

    def _matches(self, biz: Business, query: DiscoveryQuery) -> bool:
        """Light client-side filter: industry substring + optional postcode/town.

        Postcode is matched by *outward code* (the area), which is the sensible
        interpretation of "near postcode X" for a flat dataset — a full-postcode
        exact match would wrongly exclude neighbouring businesses.
        """
        hay = " ".join(filter(None, [biz.category, biz.name, biz.address, biz.postcode])).lower()
        if query.industry and query.industry.lower() not in hay:
            return False
        if query.postcode and self._outward_code(query.postcode) != self._outward_code(
            biz.postcode
        ):
            return False
        if query.town and query.town.lower() not in hay:
            return False
        return True

    async def search(self, query: DiscoveryQuery) -> list[Business]:
        if not self._path.exists():
            raise ProviderError(f"CSV file not found: {self._path}")

        results: list[Business] = []
        with self._path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                biz = self._row_to_business(row)
                if biz is None:
                    continue
                # An empty industry means "return everything in the file".
                if query.industry and not self._matches(biz, query):
                    continue
                results.append(biz)
                if len(results) >= query.limit:
                    break
        log.info("csv.search", path=str(self._path), returned=len(results))
        return results
