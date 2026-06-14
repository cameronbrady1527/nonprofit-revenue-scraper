"""Database layer: engine creation, schema initialization, persistence.

SQLite for the MVP. Schema constructs are restricted to what ports
unchanged to PostgreSQL/Supabase.
"""

from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.models import Base, Organization


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


def list_organizations(engine: Engine) -> list[Organization]:
    with Session(engine) as session:
        return list(session.scalars(select(Organization)))
