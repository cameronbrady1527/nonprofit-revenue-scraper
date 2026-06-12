"""Recency-first filing selection: the newest filing always wins."""

from nonprofit_benchmark.filing_selector import select_filing


def filing(year, *, pdf_url=None, revenue=None, officer_comp=None):
    entry = {"tax_prd_yr": year, "tax_prd": year * 100 + 12}
    if pdf_url is not None:
        entry["pdf_url"] = pdf_url
    if revenue is not None:
        entry["totrevenue"] = revenue
        entry["compnsatncurrofcr"] = officer_comp
    return entry


def test_newest_structured_filing_is_selected_with_its_data():
    with_data = [
        filing(2023, revenue=480000, officer_comp=120000, pdf_url="https://pdf/2023"),
        filing(2021, revenue=400000, officer_comp=100000),
    ]

    selected = select_filing(with_data, [])

    assert selected.source == "api"
    assert selected.tax_year == 2023
    assert selected.total_revenue == 480000
    assert selected.officer_compensation == 120000
    assert selected.pdf_url == "https://pdf/2023"


def test_newer_pdf_only_filing_beats_older_structured_data():
    with_data = [filing(2022, revenue=400000, officer_comp=100000)]
    without_data = [filing(2024, pdf_url="https://pdf/2024")]

    selected = select_filing(with_data, without_data)

    assert selected.source == "pdf"
    assert selected.tax_year == 2024
    assert selected.pdf_url == "https://pdf/2024"
    assert selected.total_revenue is None


def test_tied_year_prefers_structured_data():
    with_data = [filing(2023, revenue=480000, officer_comp=120000)]
    without_data = [filing(2023, pdf_url="https://pdf/2023")]

    selected = select_filing(with_data, without_data)

    assert selected.source == "api"


def test_no_filings_returns_none():
    assert select_filing([], []) is None


def test_entries_missing_year_fields_are_treated_as_oldest():
    with_data = [{"totrevenue": 1, "compnsatncurrofcr": 1}]  # no tax_prd at all
    without_data = [filing(2020, pdf_url="https://pdf/2020")]

    selected = select_filing(with_data, without_data)

    assert selected.source == "pdf"
    assert selected.tax_year == 2020
