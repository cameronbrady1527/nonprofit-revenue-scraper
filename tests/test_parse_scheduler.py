"""Pure parse scheduler: cost guard + status rules over plain filing/org data."""

from nonprofit_benchmark.models import Filing, Organization
from nonprofit_benchmark.parse_scheduler import schedule_filings

BAND = (250_000, 1_000_000)


def org(ein, revenue=None):
    return Organization(ein=ein, name=f"ORG {ein}", city="ALBANY", state="NY",
                        ntee_code="A65", income_code=4, revenue_amount=revenue)


def filing(ein, status="unparsed", revenue=None):
    return Filing(ein=ein, tax_year=2024, source="pdf", pdf_url=f"https://pdf/{ein}",
                  total_revenue=revenue, officer_compensation=None, parse_status=status)


def selected_eins(filings, orgs, **kwargs):
    return [f.ein for f in schedule_filings(filings, orgs, **kwargs)]


def test_unparsed_filing_with_revenue_in_band_is_selected():
    assert selected_eins(
        [filing("111000001")], [org("111000001", revenue=500_000)], revenue_band=BAND
    ) == ["111000001"]


def test_filing_with_unknown_revenue_is_selected_despite_band():
    assert selected_eins(
        [filing("111000001")], [org("111000001", revenue=None)], revenue_band=BAND
    ) == ["111000001"]


def test_filing_with_revenue_near_band_is_selected():
    # The band is widened by 50% on each side: (250K, 1M) admits 125K..1.5M.
    assert selected_eins(
        [filing("111000001"), filing("111000002")],
        [org("111000001", revenue=130_000), org("111000002", revenue=1_400_000)],
        revenue_band=BAND,
    ) == ["111000001", "111000002"]


def test_filing_with_revenue_far_outside_band_is_skipped():
    assert selected_eins(
        [filing("111000001"), filing("111000002")],
        [org("111000001", revenue=50_000_000), org("111000002", revenue=10_000)],
        revenue_band=BAND,
    ) == []


def test_no_band_selects_every_candidate_regardless_of_revenue():
    assert selected_eins(
        [filing("111000001"), filing("111000002")],
        [org("111000001", revenue=50_000_000), org("111000002", revenue=None)],
    ) == ["111000001", "111000002"]


def test_parsed_and_no_pdf_filings_are_never_selected():
    orgs = [org("111000001", revenue=500_000), org("111000002", revenue=500_000)]
    assert selected_eins(
        [filing("111000001", status="parsed"), filing("111000002", status="no_pdf")],
        orgs,
        revenue_band=BAND,
    ) == []


def test_failed_filings_are_retried_only_when_requested():
    filings = [filing("111000001", status="failed")]
    orgs = [org("111000001", revenue=500_000)]

    assert selected_eins(filings, orgs, revenue_band=BAND) == []
    assert selected_eins(filings, orgs, revenue_band=BAND, retry_failed=True) == ["111000001"]


def test_filing_revenue_is_preferred_over_bmf_revenue():
    assert selected_eins(
        [
            filing("111000001", revenue=500_000),  # filing in band, BMF far out
            filing("111000002", revenue=50_000_000),  # filing far out, BMF in band
        ],
        [org("111000001", revenue=50_000_000), org("111000002", revenue=500_000)],
        revenue_band=BAND,
    ) == ["111000001"]
