"""Database layer: engine creation and schema initialization.

SQLite for the MVP. Schema constructs are restricted to what ports
unchanged to PostgreSQL/Supabase.
"""

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base all pipeline tables register against."""


def init_db(db_path: str | Path) -> Engine:
    """Create the database file with the current schema; safe to re-run."""
    engine = create_engine(f"sqlite:///{Path(db_path)}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA user_version = 1"))
    return engine
