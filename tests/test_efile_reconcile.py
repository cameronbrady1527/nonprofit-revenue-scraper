"""Pure reconciliation decision: most-recent, most-accurate filing wins."""

from nonprofit_benchmark.efile_reconcile import (
    ACTION_INSERT,
    ACTION_UPGRADE,
    decide_reconciliation,
)

UNPARSED, PARSED, NO_PDF = "unparsed", "parsed", "no_pdf"


def test_no_efile_means_no_change():
    assert decide_reconciliation(2023, "api", PARSED, None) is None
    assert decide_reconciliation(None, None, None, None) is None


def test_org_with_no_recorded_filing_gets_backfilled():
    # The 'no_filing' case: ProPublica returned nothing, IRS has a return.
    assert decide_reconciliation(None, None, None, 2024) == ACTION_INSERT


def test_newer_efile_is_inserted():
    assert decide_reconciliation(2021, "api", PARSED, 2024) == ACTION_INSERT
    assert decide_reconciliation(2021, "pdf", UNPARSED, 2024) == ACTION_INSERT


def test_same_year_aggregate_api_is_upgraded_to_efile():
    assert decide_reconciliation(2024, "api", PARSED, 2024) == ACTION_UPGRADE


def test_same_year_no_pdf_is_upgraded_so_it_gets_parsed():
    # ProPublica recorded the year but with no usable PDF; parse never schedules
    # it, yet the IRS has the e-file — recover it.
    assert decide_reconciliation(2024, "pdf", NO_PDF, 2024) == ACTION_UPGRADE


def test_same_year_pdf_or_efile_left_alone():
    # pdf-unparsed already resolves against the cache during parse; efile is best.
    assert decide_reconciliation(2024, "pdf", UNPARSED, 2024) is None
    assert decide_reconciliation(2024, "efile", UNPARSED, 2024) is None


def test_propublica_strictly_newer_is_kept():
    assert decide_reconciliation(2025, "api", PARSED, 2024) is None
    assert decide_reconciliation(2025, "pdf", UNPARSED, 2024) is None
