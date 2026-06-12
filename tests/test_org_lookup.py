"""Your-org identification: EIN lookup and name-search fallback."""

import pytest

from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.db import (
    find_org_by_ein,
    init_db,
    list_filings,
    record_parse_success,
    record_selected_filing,
    search_organizations,
    upsert_organizations,
)
from nonprofit_benchmark.filing_selector import SelectedFiling
from nonprofit_benchmark.gemini_parser import ExecutiveRecord, FilingExtraction


@pytest.fixture
def engine(tmp_path):
    return init_db(tmp_path / "benchmark.db")


def seed_org(engine, ein, name=None, state="NY"):
    upsert_organizations(engine, [BmfOrg(
        ein=ein, name=name or f"ORG {ein}", city="ALBANY", state=state,
        ntee_code="A65", income_code=4, revenue_amount=480000,
    )])


def seed_parsed_filing(engine, ein, tax_year=2024, filing_revenue=512000,
                       executives=None):
    record_selected_filing(engine, ein, SelectedFiling(
        tax_year=tax_year, source="pdf", pdf_url=f"https://pdf/{ein}",
        total_revenue=None, officer_compensation=None,
    ))
    filing = next(f for f in list_filings(engine)
                  if f.ein == ein and f.tax_year == tax_year)
    if executives is None:
        executives = [ExecutiveRecord(name="JANE DOE", title="EXECUTIVE DIRECTOR",
                                      compensation_org=95000)]
    record_parse_success(engine, filing.id, FilingExtraction(
        total_revenue=filing_revenue, executives=executives,
    ))


def test_ein_lookup_returns_org_with_newest_filing_and_executives(engine):
    seed_org(engine, "111000001", name="ARTS COUNCIL")
    seed_parsed_filing(engine, "111000001", tax_year=2022, filing_revenue=400000)
    seed_parsed_filing(engine, "111000001", tax_year=2024, filing_revenue=512000)

    lookup = find_org_by_ein(engine, "111000001")

    assert lookup.organization.name == "ARTS COUNCIL"
    assert lookup.filing.tax_year == 2024
    assert lookup.filing.total_revenue == 512000
    assert [e.name for e in lookup.executives] == ["JANE DOE"]


def test_ein_lookup_misses_return_none_instead_of_blocking(engine):
    seed_org(engine, "111000001")

    assert find_org_by_ein(engine, "999999999") is None
    assert find_org_by_ein(engine, "") is None


def test_ein_lookup_of_org_without_filings_still_returns_its_profile(engine):
    seed_org(engine, "111000001", name="ARTS COUNCIL")

    lookup = find_org_by_ein(engine, "111000001")

    assert lookup.organization.name == "ARTS COUNCIL"
    assert lookup.filing is None
    assert lookup.executives == []


def test_name_search_matches_case_insensitive_substring(engine):
    seed_org(engine, "111000001", name="ALBANY ARTS COUNCIL")
    seed_org(engine, "111000002", name="COUNCIL OF THE ARTS")
    seed_org(engine, "111000003", name="FOOD BANK")

    candidates = search_organizations(engine, "arts")

    assert sorted(c.ein for c in candidates) == ["111000001", "111000002"]


def test_name_search_can_be_scoped_to_a_state(engine):
    seed_org(engine, "111000001", name="ALBANY ARTS COUNCIL", state="NY")
    seed_org(engine, "222000001", name="BURLINGTON ARTS COUNCIL", state="VT")

    candidates = search_organizations(engine, "arts", state="ny")

    assert [c.ein for c in candidates] == ["111000001"]


def test_name_search_with_no_match_returns_empty_list(engine):
    seed_org(engine, "111000001", name="ALBANY ARTS COUNCIL")

    assert search_organizations(engine, "hospital") == []
