"""Database layer: engine creation, schema initialization, persistence.

SQLite for the MVP. Schema constructs are restricted to what ports
unchanged to PostgreSQL/Supabase.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from nonprofit_benchmark.benchmark import Peer
from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.filing_selector import SOURCE_API, SelectedFiling
from nonprofit_benchmark.gemini_parser import FilingExtraction
from nonprofit_benchmark.models import Base, Executive, Filing, Organization

PARSE_STATUS_UNPARSED = "unparsed"
PARSE_STATUS_PARSED = "parsed"
PARSE_STATUS_FAILED = "failed"
PARSE_STATUS_NO_PDF = "no_pdf"


def get_engine(db_path: str | Path) -> Engine:
    return create_engine(f"sqlite:///{Path(db_path)}")


def init_db(db_path: str | Path) -> Engine:
    """Create the database file with the current schema; safe to re-run."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA user_version = 1"))
    return engine


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
