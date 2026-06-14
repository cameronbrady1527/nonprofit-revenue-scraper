"""Benchmark Engine (pure, no I/O).

Turns peer data — an organization, its newest filing, and that filing's
executives — into one benchmark row per organization plus summary
statistics. The benchmark figure per organization is its highest-paid
executive's Part VII column D compensation, never a sum across people.
"""

import statistics
from dataclasses import dataclass
from typing import NamedTuple

from nonprofit_benchmark.models import Executive, Filing, Organization

DATA_SOURCE_API = "api"
DATA_SOURCE_AI = "ai"

PROPUBLICA_ORG_URL = "https://projects.propublica.org/nonprofits/organizations/{ein}"


class Peer(NamedTuple):
    """One organization with its selected filing and that filing's executives."""

    organization: Organization
    filing: Filing
    executives: list[Executive]


@dataclass(frozen=True)
class BenchmarkRow:
    ein: str
    name: str
    city: str | None
    state: str | None
    ntee_code: str | None
    total_revenue: int | None
    executive_title: str | None
    executive_compensation: int | None
    percent_of_revenue: float | None
    filing_year: int
    data_source: str  # DATA_SOURCE_API or DATA_SOURCE_AI
    propublica_url: str
    paid_executive_count: int | None
    executives: tuple[Executive, ...]
    stale: bool  # filing more than three years older than current_year


@dataclass(frozen=True)
class SummaryStats:
    """Median/quartile statistics over the rows' benchmark compensation."""

    peer_count: int
    median: float | None
    p25: float | None
    p75: float | None
    minimum: int | None
    maximum: int | None


def summarize(rows: list[BenchmarkRow]) -> SummaryStats:
    """Robust headline statistics; rows without a compensation figure are excluded."""
    comps = sorted(
        row.executive_compensation
        for row in rows
        if row.executive_compensation is not None
    )
    if not comps:
        return SummaryStats(
            peer_count=0, median=None, p25=None, p75=None, minimum=None, maximum=None
        )
    if len(comps) == 1:
        p25 = median = p75 = comps[0]
    else:
        p25, median, p75 = statistics.quantiles(comps, n=4, method="inclusive")
    return SummaryStats(
        peer_count=len(comps),
        median=median,
        p25=p25,
        p75=p75,
        minimum=comps[0],
        maximum=comps[-1],
    )


def _percent_of_revenue(compensation: int | None, revenue: int | None) -> float | None:
    if compensation is None or not revenue:
        return None
    return compensation / revenue * 100


def _highest_paid(executives: list[Executive]) -> Executive | None:
    """The executive with the largest column-D figure; None if no one has one."""
    compensated = [e for e in executives if e.compensation_org is not None]
    if not compensated:
        return None
    return max(compensated, key=lambda e: e.compensation_org)


def build_rows(peers: list[Peer], current_year: int) -> list[BenchmarkRow]:
    """One table row per organization, benchmarked on its top-paid executive."""
    rows = []
    for organization, filing, executives in peers:
        if filing.source == "api":
            title, compensation, paid_count = None, filing.officer_compensation, None
            data_source = DATA_SOURCE_API
        else:
            top = _highest_paid(executives)
            title = top.title if top else None
            compensation = top.compensation_org if top else None
            paid_count = sum(1 for e in executives if (e.compensation_org or 0) > 0)
            data_source = DATA_SOURCE_AI
        rows.append(
            BenchmarkRow(
                ein=organization.ein,
                name=organization.name,
                city=organization.city,
                state=organization.state,
                ntee_code=organization.ntee_code,
                total_revenue=filing.total_revenue,
                executive_title=title,
                executive_compensation=compensation,
                percent_of_revenue=_percent_of_revenue(compensation, filing.total_revenue),
                filing_year=filing.tax_year,
                data_source=data_source,
                propublica_url=PROPUBLICA_ORG_URL.format(ein=organization.ein),
                paid_executive_count=paid_count,
                executives=tuple(executives),
                stale=current_year - filing.tax_year > 3,
            )
        )
    return rows
