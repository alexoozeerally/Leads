"""Tests for the CSV business provider."""

from __future__ import annotations

import pytest

from app.business_providers.csv_provider import CSVBusinessProvider
from app.exceptions import ProviderError
from app.schemas.business import DiscoveryQuery

SAMPLE = "tests/fixtures/sample_businesses.csv"


@pytest.mark.asyncio
async def test_reads_all_rows_when_industry_empty():
    provider = CSVBusinessProvider(SAMPLE)
    businesses = await provider.search(DiscoveryQuery(industry="", limit=25))
    assert len(businesses) == 9
    assert {b.name for b in businesses} >= {"Old City Barbers", "Harbourside Plumbing"}


@pytest.mark.asyncio
async def test_unknown_columns_stay_none():
    provider = CSVBusinessProvider(SAMPLE)
    businesses = await provider.search(DiscoveryQuery(industry="", limit=25))
    plumber = next(b for b in businesses if b.name == "Harbourside Plumbing")
    # The CSV has no website/email for the plumber -> must be None, never invented.
    assert plumber.website is None
    assert plumber.email is None
    assert plumber.rating == 4.8


@pytest.mark.asyncio
async def test_industry_filter_matches_category():
    provider = CSVBusinessProvider(SAMPLE)
    businesses = await provider.search(DiscoveryQuery(industry="Dentist", limit=25))
    assert {b.name for b in businesses} == {
        "Clifton Dental Care",
        "Whiteladies Dental Studio",
        "City Smile Dental",
    }


@pytest.mark.asyncio
async def test_postcode_matches_by_outward_code():
    provider = CSVBusinessProvider(SAMPLE)
    # 'BS8 9ZZ' shares the outward code 'BS8' with the three dentists.
    businesses = await provider.search(
        DiscoveryQuery(industry="Dentist", postcode="BS8 9ZZ", limit=25)
    )
    assert len(businesses) == 3
    # A different outward code excludes them.
    none = await provider.search(DiscoveryQuery(industry="Dentist", postcode="BS1 1AA", limit=25))
    assert none == []


@pytest.mark.asyncio
async def test_missing_file_raises():
    provider = CSVBusinessProvider("tests/fixtures/does_not_exist.csv")
    with pytest.raises(ProviderError):
        await provider.search(DiscoveryQuery(industry="", limit=25))
