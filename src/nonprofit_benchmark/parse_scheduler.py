"""Pure parse scheduler: decides which filings get Gemini parsing.

No I/O here — the CLI shell queries the database and feeds plain
filing/organization data in.
"""

from collections.abc import Iterable

from nonprofit_benchmark.db import PARSE_STATUS_FAILED, PARSE_STATUS_UNPARSED
from nonprofit_benchmark.models import Filing, Organization

BAND_WIDENING = 0.5  # each band edge is relaxed by 50% to catch near-band orgs


def schedule_filings(
    filings: Iterable[Filing],
    organizations: Iterable[Organization],
    revenue_band: tuple[float, float] | None = None,
    retry_failed: bool = False,
) -> list[Filing]:
    """Return the filings worth sending to Gemini, input ordering preserved.

    Only "unparsed" filings are candidates ("failed" too when retry_failed);
    "parsed" and "no_pdf" are never re-attempted. With a revenue_band, the
    cost guard keeps a candidate only if its best-known revenue — the
    filing's total_revenue, else the organization's BMF revenue_amount —
    falls within the band widened by BAND_WIDENING on each side, or if its
    revenue is entirely unknown (unknown is never silently excluded).
    """
    candidate_statuses = {PARSE_STATUS_UNPARSED}
    if retry_failed:
        candidate_statuses.add(PARSE_STATUS_FAILED)
    revenue_by_ein = {o.ein: o.revenue_amount for o in organizations}
    selected = []
    for filing in filings:
        if filing.parse_status not in candidate_statuses:
            continue
        revenue = (
            filing.total_revenue
            if filing.total_revenue is not None
            else revenue_by_ein.get(filing.ein)
        )
        if revenue_band is not None and revenue is not None:
            band_min, band_max = revenue_band
            if not band_min * (1 - BAND_WIDENING) <= revenue <= band_max * (1 + BAND_WIDENING):
                continue
        selected.append(filing)
    return selected
