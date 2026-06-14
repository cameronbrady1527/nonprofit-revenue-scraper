"""ORM models. One organization -> many filings -> many executives.

Types and constraints are restricted to what ports unchanged to
PostgreSQL/Supabase.
"""

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
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


class Filing(Base):
    """The selected (newest) filing for an organization, per tax year.

    parse_status tracks Gemini work: unparsed | parsed | failed | no_pdf.
    Structured API filings are stored as parsed — their data is already here.
    """

    __tablename__ = "filings"
    __table_args__ = (UniqueConstraint("ein", "tax_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ein: Mapped[str] = mapped_column(ForeignKey("organizations.ein"), index=True)
    tax_year: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String)  # api | pdf
    pdf_url: Mapped[str | None] = mapped_column(String)
    total_revenue: Mapped[int | None] = mapped_column(BigInteger)
    officer_compensation: Mapped[int | None] = mapped_column(BigInteger)
    parse_status: Mapped[str] = mapped_column(String, index=True)
