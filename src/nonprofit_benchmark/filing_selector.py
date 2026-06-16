"""Recency-first filing selection (pure, no I/O).

For each organization the newest filing across ProPublica's
`filings_with_data` and `filings_without_data` wins — even when older
structured data exists. The result is classified by where its numbers
must come from: the API (structured) or the 990 PDF.
"""

from dataclasses import dataclass

SOURCE_API = "api"
SOURCE_PDF = "pdf"
SOURCE_EFILE = "efile"  # the filing's data comes straight from IRS e-file XML


@dataclass(frozen=True)
class SelectedFiling:
    tax_year: int
    source: str  # SOURCE_API or SOURCE_PDF
    pdf_url: str | None
    total_revenue: int | None
    officer_compensation: int | None


def _recency_key(entry: dict) -> int:
    tax_prd = entry.get("tax_prd")
    if tax_prd:
        return int(tax_prd)
    tax_prd_yr = entry.get("tax_prd_yr")
    return int(tax_prd_yr) * 100 if tax_prd_yr else 0


def _year(entry: dict) -> int:
    tax_prd_yr = entry.get("tax_prd_yr")
    if tax_prd_yr:
        return int(tax_prd_yr)
    return _recency_key(entry) // 100


def select_filing(
    filings_with_data: list[dict], filings_without_data: list[dict]
) -> SelectedFiling | None:
    candidates = [(entry, True) for entry in filings_with_data]
    candidates += [(entry, False) for entry in filings_without_data]
    if not candidates:
        return None

    entry, structured = max(candidates, key=lambda item: _recency_key(item[0]))

    if structured:
        return SelectedFiling(
            tax_year=_year(entry),
            source=SOURCE_API,
            pdf_url=entry.get("pdf_url"),
            total_revenue=entry.get("totrevenue"),
            officer_compensation=entry.get("compnsatncurrofcr"),
        )
    return SelectedFiling(
        tax_year=_year(entry),
        source=SOURCE_PDF,
        pdf_url=entry.get("pdf_url"),
        total_revenue=None,
        officer_compensation=None,
    )
