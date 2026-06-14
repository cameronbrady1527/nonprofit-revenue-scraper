"""ORM models. One organization -> many filings -> many executives.

Types and constraints are restricted to what ports unchanged to
PostgreSQL/Supabase.
"""

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base all pipeline tables register against."""


class Organization(Base):
    __tablename__ = "organizations"

    ein: Mapped[str] = mapped_column(String(9), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String(2), index=True)
    ntee_code: Mapped[str | None] = mapped_column(String, index=True)
    income_code: Mapped[int | None] = mapped_column(Integer)
    revenue_amount: Mapped[int | None] = mapped_column(BigInteger)
