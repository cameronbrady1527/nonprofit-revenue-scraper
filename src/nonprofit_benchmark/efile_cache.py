"""Local cache of IRS e-file object locations (SQLite, thin I/O).

For every supported return this records where its XML lives — which national
ZIP and which member name — so `parse` can range-fetch exactly the XML it needs
without downloading gigabytes. Populated by `pipeline sync-irs`, read by
`pipeline parse`. Kept in its own file (default `irs_cache.db`), separate from
the per-state benchmark database, because it is national reference data shared
across every run.
"""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from nonprofit_benchmark.efile_index import IndexRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS efile_objects (
    object_id TEXT PRIMARY KEY,
    ein TEXT NOT NULL,
    tax_period INTEGER NOT NULL,
    tax_year INTEGER NOT NULL,
    return_type TEXT NOT NULL,
    processing_year INTEGER NOT NULL,
    zip_url TEXT,
    member_name TEXT
);
CREATE INDEX IF NOT EXISTS ix_efile_ein_year ON efile_objects (ein, tax_year);
"""


@dataclass(frozen=True)
class ObjectLocation:
    object_id: str
    return_type: str
    zip_url: str
    member_name: str


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the cache database, creating the schema if needed."""
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    return conn


def upsert_records(conn: sqlite3.Connection, records: Iterable[IndexRecord]) -> int:
    """Store index records (without ZIP locations yet); returns the count.

    Existing ZIP locations are preserved so re-running an index pass does not
    wipe a prior namelist pass for the same object.
    """
    count = 0
    with conn:
        for record in records:
            conn.execute(
                """
                INSERT INTO efile_objects
                    (object_id, ein, tax_period, tax_year, return_type, processing_year)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_id) DO UPDATE SET
                    ein=excluded.ein, tax_period=excluded.tax_period,
                    tax_year=excluded.tax_year, return_type=excluded.return_type,
                    processing_year=excluded.processing_year
                """,
                (
                    record.object_id,
                    record.ein,
                    record.tax_period,
                    record.tax_year,
                    record.return_type,
                    record.processing_year,
                ),
            )
            count += 1
    return count


def set_locations(conn: sqlite3.Connection, locations: dict[str, tuple[str, str]]) -> int:
    """Attach `object_id -> (zip_url, member_name)` to known records.

    Only objects already present from an index pass are updated; entries for
    unknown object ids (e.g. 990-T members we skip) are ignored. Returns the
    number of rows actually located.
    """
    located = 0
    with conn:
        for object_id, (zip_url, member_name) in locations.items():
            cur = conn.execute(
                "UPDATE efile_objects SET zip_url=?, member_name=? WHERE object_id=?",
                (zip_url, member_name, object_id),
            )
            located += cur.rowcount
    return located


def newest_located_year(conn: sqlite3.Connection, ein: str) -> int | None:
    """The most recent tax year for which this EIN has a located e-file return,
    or None. Used to compare IRS coverage against ProPublica's recorded filing."""
    row = conn.execute(
        """
        SELECT tax_year FROM efile_objects
        WHERE ein=? AND zip_url IS NOT NULL AND member_name IS NOT NULL
        ORDER BY tax_year DESC, processing_year DESC
        LIMIT 1
        """,
        (ein.zfill(9),),
    ).fetchone()
    return row[0] if row else None


def resolve(conn: sqlite3.Connection, ein: str, tax_year: int) -> ObjectLocation | None:
    """The located return for this EIN and tax year, newest filing first.

    Newest is by processing year then tax period, so an amended return
    processed later supersedes the original. Returns None when no located
    return exists for the EIN/year yet.
    """
    row = conn.execute(
        """
        SELECT object_id, return_type, zip_url, member_name
        FROM efile_objects
        WHERE ein=? AND tax_year=? AND zip_url IS NOT NULL AND member_name IS NOT NULL
        ORDER BY processing_year DESC, tax_period DESC
        LIMIT 1
        """,
        (ein.zfill(9), tax_year),
    ).fetchone()
    if row is None:
        return None
    return ObjectLocation(object_id=row[0], return_type=row[1], zip_url=row[2], member_name=row[3])
