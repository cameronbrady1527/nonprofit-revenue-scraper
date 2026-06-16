"""Database layer: engine creation, schema initialization, persistence.

SQLite for the MVP. Schema constructs are restricted to what ports
unchanged to PostgreSQL/Supabase.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.orm import Session

from nonprofit_benchmark.benchmark import Peer
from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.expansion import Filters
from nonprofit_benchmark.efile_reconcile import (
    ACTION_INSERT,
    ACTION_UPGRADE,
    decide_reconciliation,
)
from nonprofit_benchmark.filing_selector import SOURCE_API, SOURCE_EFILE, SelectedFiling
from nonprofit_benchmark.extraction import FilingExtraction
from nonprofit_benchmark.models import (
    PARSE_STATUS_FAILED,
    PARSE_STATUS_NO_PDF,
    PARSE_STATUS_PARSED,
    PARSE_STATUS_UNPARSED,
    Base,
    Executive,
    Filing,
    Organization,
)

__all__ = [  # re-exported for callers that import the status constants from here
    "PARSE_STATUS_FAILED",
    "PARSE_STATUS_NO_PDF",
    "PARSE_STATUS_PARSED",
    "PARSE_STATUS_UNPARSED",
]


def get_engine(db_path: str | Path) -> Engine:
    return create_engine(f"sqlite:///{Path(db_path)}")


def init_db(db_path: str | Path) -> Engine:
    """Create the database file with the current schema; safe to re-run."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA user_version = 1"))
    return engine


def is_initialized(engine: Engine) -> bool:
    """True once the schema exists (i.e. `init` has run on this database)."""
    return inspect(engine).has_table(Organization.__tablename__)


def upsert_organizations(engine: Engine, orgs: Iterable[BmfOrg]) -> int:
    """Insert or update organizations by EIN; returns the number processed."""
    count = 0
    with Session(engine) as session:
        for org in orgs:
            session.merge(
                Organization(
                    ein=org.ein,
                    name=org.name,
                    city=org.city,
                    state=org.state,
                    ntee_code=org.ntee_code,
                    income_code=org.income_code,
                    revenue_amount=org.revenue_amount,
                )
            )
            count += 1
        session.commit()
    return count


def list_organizations(engine: Engine, state: str | None = None) -> list[Organization]:
    query = select(Organization)
    if state:
        query = query.where(Organization.state == state.upper())
    with Session(engine) as session:
        return list(session.scalars(query))


def _initial_parse_status(selected: SelectedFiling) -> str:
    if selected.source == SOURCE_API:
        return PARSE_STATUS_PARSED
    return PARSE_STATUS_UNPARSED if selected.pdf_url else PARSE_STATUS_NO_PDF


def record_selected_filing(engine: Engine, ein: str, selected: SelectedFiling) -> None:
    """Insert the selected filing, or refresh it without clobbering parse work."""
    with Session(engine) as session:
        existing = session.scalars(
            select(Filing).where(Filing.ein == ein, Filing.tax_year == selected.tax_year)
        ).first()
        if existing is None:
            session.add(
                Filing(
                    ein=ein,
                    tax_year=selected.tax_year,
                    source=selected.source,
                    pdf_url=selected.pdf_url,
                    total_revenue=selected.total_revenue,
                    officer_compensation=selected.officer_compensation,
                    parse_status=_initial_parse_status(selected),
                )
            )
        elif selected.source == SOURCE_API:
            existing.source = selected.source
            existing.pdf_url = selected.pdf_url or existing.pdf_url
            existing.total_revenue = selected.total_revenue
            existing.officer_compensation = selected.officer_compensation
            existing.parse_status = PARSE_STATUS_PARSED
        session.commit()


def reconcile_with_efile(engine: Engine, newest_year, state: str) -> tuple[int, int]:
    """Make each org's recorded filing the most recent across ProPublica and the
    IRS e-file cache. `newest_year(ein)` returns the newest located e-file year
    for an EIN (or None). Returns (inserted, upgraded).

    INSERT adds an unparsed e-file filing for a year ProPublica did not record
    (a return it missed, or one newer than it had). UPGRADE relabels an existing
    ProPublica aggregate ("api") filing to e-file and re-queues it so `parse`
    extracts the real per-person Part VII figure; the existing api revenue and
    officer compensation are kept as a fallback should that later parse fail.
    """
    inserted = upgraded = 0
    with Session(engine) as session:
        for org in session.scalars(
            select(Organization).where(Organization.state == state.upper())
        ):
            existing = session.scalars(
                select(Filing)
                .where(Filing.ein == org.ein)
                .order_by(Filing.tax_year.desc())
                .limit(1)
            ).first()
            irs_year = newest_year(org.ein)
            action = decide_reconciliation(
                existing.tax_year if existing else None,
                existing.source if existing else None,
                existing.parse_status if existing else None,
                irs_year,
            )
            if action == ACTION_INSERT:
                session.add(
                    Filing(
                        ein=org.ein,
                        tax_year=irs_year,
                        source=SOURCE_EFILE,
                        pdf_url=None,
                        total_revenue=None,
                        officer_compensation=None,
                        parse_status=PARSE_STATUS_UNPARSED,
                    )
                )
                inserted += 1
            elif action == ACTION_UPGRADE:
                existing.source = SOURCE_EFILE
                existing.parse_status = PARSE_STATUS_UNPARSED
                upgraded += 1
        session.commit()
    return inserted, upgraded


def list_filings(engine: Engine, state: str | None = None) -> list[Filing]:
    query = select(Filing)
    if state:
        query = query.join(Organization, Organization.ein == Filing.ein).where(
            Organization.state == state.upper()
        )
    with Session(engine) as session:
        return list(session.scalars(query))


def record_parse_success(engine: Engine, filing_id: int, extraction: FilingExtraction) -> None:
    """Store extracted executives (replacing any prior parse) and mark parsed."""
    with Session(engine) as session:
        filing = session.get(Filing, filing_id)
        for stale in session.scalars(select(Executive).where(Executive.filing_id == filing_id)):
            session.delete(stale)
        for executive in extraction.executives:
            session.add(
                Executive(
                    filing_id=filing_id,
                    name=executive.name,
                    title=executive.title,
                    compensation_org=executive.compensation_org,
                    compensation_related=executive.compensation_related,
                    compensation_other=executive.compensation_other,
                )
            )
        if extraction.total_revenue is not None:
            filing.total_revenue = extraction.total_revenue
        filing.parse_status = PARSE_STATUS_PARSED
        session.commit()


def record_parse_failure(engine: Engine, filing_id: int) -> None:
    with Session(engine) as session:
        session.get(Filing, filing_id).parse_status = PARSE_STATUS_FAILED
        session.commit()


def query_peers(
    engine: Engine,
    state: str | None = None,
    revenue_min: int | None = None,
    revenue_max: int | None = None,
    ntee_prefix: str | None = None,
) -> list[Peer]:
    """Peer data for the Benchmark Engine: each matching organization with its
    newest filing and that filing's executives.

    The revenue band tests the newest filing's total_revenue, falling back to
    the organization's BMF revenue_amount when the filing has no figure.
    """
    query = select(Organization, Filing).join(Filing, Filing.ein == Organization.ein)
    if state:
        query = query.where(Organization.state == state.upper())
    if ntee_prefix:
        query = query.where(Organization.ntee_code.startswith(ntee_prefix.upper()))
    with Session(engine) as session:
        newest: dict[str, tuple[Organization, Filing]] = {}
        for organization, filing in session.execute(query):
            kept = newest.get(organization.ein)
            if kept is None or filing.tax_year > kept[1].tax_year:
                newest[organization.ein] = (organization, filing)
        peers = []
        for organization, filing in newest.values():
            revenue = filing.total_revenue
            if revenue is None:
                revenue = organization.revenue_amount
            if revenue_min is not None and (revenue is None or revenue < revenue_min):
                continue
            if revenue_max is not None and (revenue is None or revenue > revenue_max):
                continue
            executives = list(
                session.scalars(select(Executive).where(Executive.filing_id == filing.id))
            )
            peers.append(Peer(organization=organization, filing=filing, executives=executives))
    return peers


def query_peers_for_filters(engine: Engine, filters: Filters) -> list[Peer]:
    """`query_peers` over an Expansion Advisor filter set, which may span
    several states. The count source for the advisor is `len(...)` of this.
    """
    if not filters.states:
        return query_peers(
            engine,
            revenue_min=filters.revenue_min,
            revenue_max=filters.revenue_max,
            ntee_prefix=filters.ntee,
        )
    peers: list[Peer] = []
    for state in filters.states:
        peers.extend(
            query_peers(
                engine,
                state=state,
                revenue_min=filters.revenue_min,
                revenue_max=filters.revenue_max,
                ntee_prefix=filters.ntee,
            )
        )
    return peers


class OrgLookup(NamedTuple):
    """One organization with its newest stored filing (None if no filing yet)."""

    organization: Organization
    filing: Filing | None
    executives: list[Executive]


def find_org_by_ein(engine: Engine, ein: str) -> OrgLookup | None:
    """The organization with this exact EIN, its newest stored filing, and
    that filing's executives; None when the EIN is not in the database."""
    with Session(engine) as session:
        organization = session.get(Organization, ein)
        if organization is None:
            return None
        filing = session.scalars(
            select(Filing)
            .where(Filing.ein == ein)
            .order_by(Filing.tax_year.desc())
            .limit(1)
        ).first()
        executives = (
            list(session.scalars(select(Executive).where(Executive.filing_id == filing.id)))
            if filing
            else []
        )
        return OrgLookup(organization=organization, filing=filing, executives=executives)


def search_organizations(
    engine: Engine, name: str, state: str | None = None
) -> list[Organization]:
    """Candidate organizations whose name contains the query (case-insensitive),
    for pick-from-results when an EIN lookup misses."""
    query = select(Organization).where(Organization.name.icontains(name))
    if state:
        query = query.where(Organization.state == state.upper())
    with Session(engine) as session:
        return list(session.scalars(query))


def list_executives(engine: Engine, filing_id: int | None = None) -> list[Executive]:
    query = select(Executive)
    if filing_id is not None:
        query = query.where(Executive.filing_id == filing_id)
    with Session(engine) as session:
        return list(session.scalars(query))
