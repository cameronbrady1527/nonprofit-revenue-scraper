"""`query_peers`: filtered peer data (org + newest filing + executives)."""

import pytest

from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.db import (
    init_db,
    list_filings,
    query_peers,
    record_parse_success,
    record_selected_filing,
    upsert_organizations,
)
from nonprofit_benchmark.filing_selector import SelectedFiling
from nonprofit_benchmark.gemini_parser import ExecutiveRecord, FilingExtraction


@pytest.fixture
def engine(tmp_path):
    return init_db(tmp_path / "benchmark.db")


def seed_parsed_org(engine, ein, state="NY", ntee_code="A65", bmf_revenue=480000,
                    filing_revenue=512000, tax_year=2024, executives=None):
    """A pdf-sourced org whose filing was parsed by Gemini."""
    upsert_organizations(engine, [BmfOrg(
        ein=ein, name=f"ORG {ein}", city="ALBANY", state=state,
        ntee_code=ntee_code, income_code=4, revenue_amount=bmf_revenue,
    )])
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


def test_query_returns_org_with_newest_filing_and_its_executives(engine):
    seed_parsed_org(engine, "111000001")

    [peer] = query_peers(engine)

    assert peer.organization.ein == "111000001"
    assert peer.filing.tax_year == 2024
    assert peer.filing.total_revenue == 512000
    assert [e.name for e in peer.executives] == ["JANE DOE"]


def test_query_filters_by_state(engine):
    seed_parsed_org(engine, "111000001", state="NY")
    seed_parsed_org(engine, "222000001", state="VT")

    peers = query_peers(engine, state="ny")

    assert [p.organization.ein for p in peers] == ["111000001"]


def test_revenue_band_uses_filing_revenue_with_bmf_fallback(engine):
    seed_parsed_org(engine, "111000001", filing_revenue=512000)
    seed_parsed_org(engine, "111000002", filing_revenue=2_000_000)
    seed_parsed_org(engine, "111000003", filing_revenue=None, bmf_revenue=300000)
    seed_parsed_org(engine, "111000004", filing_revenue=None, bmf_revenue=50000)

    peers = query_peers(engine, revenue_min=250_000, revenue_max=1_000_000)

    assert sorted(p.organization.ein for p in peers) == ["111000001", "111000003"]


def test_query_filters_by_ntee_prefix(engine):
    seed_parsed_org(engine, "111000001", ntee_code="A65")
    seed_parsed_org(engine, "111000002", ntee_code="A20")
    seed_parsed_org(engine, "111000003", ntee_code="B65")
    seed_parsed_org(engine, "111000004", ntee_code=None)

    major_group = query_peers(engine, ntee_prefix="A")
    full_code = query_peers(engine, ntee_prefix="A65")

    assert sorted(p.organization.ein for p in major_group) == ["111000001", "111000002"]
    assert [p.organization.ein for p in full_code] == ["111000001"]


def test_org_with_multiple_stored_filings_contributes_only_its_newest(engine):
    seed_parsed_org(engine, "111000001", tax_year=2022, filing_revenue=400000)
    seed_parsed_org(engine, "111000001", tax_year=2024, filing_revenue=512000)

    [peer] = query_peers(engine)

    assert peer.filing.tax_year == 2024
    assert peer.filing.total_revenue == 512000
