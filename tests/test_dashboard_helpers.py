"""Tests for the dashboard's pure export + filter helpers."""

from __future__ import annotations

import csv
import io

from app.dashboard.data_access import LeadRow
from app.dashboard.export import EXPORT_COLUMNS, leads_to_csv
from app.dashboard.filters import LeadFilter, apply_filter


def _lead(name, score, priority="Warm", category="Dentist", postcode="BS8 2QN", draft=None):
    return LeadRow(
        business_id=1,
        name=name,
        category=category,
        website=f"https://{name.lower().replace(' ', '')}.example",
        postcode=postcode,
        website_state="ok",
        opportunity_score=score,
        notes="",
        desktop_screenshot=None,
        mobile_screenshot=None,
        module_results={},
        lead_score={"priority": priority, "likelihood_of_purchase": score / 100, "summary": "s"},
        draft=draft,
    )


def _leads():
    return [
        _lead("Alpha Dental", 80, "Hot"),
        _lead("Beta Barbers", 55, "Warm", category="Barber", postcode="BS1 1HQ"),
        _lead("Gamma Cafe", 30, "Cold", category="Cafe", draft={"approved": True}),
    ]


def test_csv_has_header_and_all_rows():
    text = leads_to_csv(_leads())
    reader = list(csv.DictReader(io.StringIO(text)))
    assert len(reader) == 3
    assert list(reader[0].keys()) == EXPORT_COLUMNS
    assert reader[0]["name"] == "Alpha Dental"
    assert reader[0]["priority"] == "Hot"
    assert reader[2]["draft_approved"] == "True"


def test_search_filters_by_name_category_postcode():
    out = apply_filter(_leads(), LeadFilter(search="barber"))
    assert [le.name for le in out] == ["Beta Barbers"]
    out = apply_filter(_leads(), LeadFilter(search="BS8"))
    names = {le.name for le in out}
    assert "Alpha Dental" in names  # BS8 postcode matches
    assert "Beta Barbers" not in names  # BS1 postcode excluded


def test_priority_and_min_score_filters():
    out = apply_filter(_leads(), LeadFilter(priorities=("Hot", "Warm")))
    assert {le.name for le in out} == {"Alpha Dental", "Beta Barbers"}
    out = apply_filter(_leads(), LeadFilter(min_score=60))
    assert [le.name for le in out] == ["Alpha Dental"]


def test_only_with_draft_filter():
    out = apply_filter(_leads(), LeadFilter(only_with_draft=True))
    assert [le.name for le in out] == ["Gamma Cafe"]


def test_sort_orders():
    asc = apply_filter(_leads(), LeadFilter(sort="Opportunity (low→high)"))
    assert [le.opportunity_score for le in asc] == [30, 55, 80]
    by_name = apply_filter(_leads(), LeadFilter(sort="Name (A→Z)"))
    assert [le.name for le in by_name] == ["Alpha Dental", "Beta Barbers", "Gamma Cafe"]
