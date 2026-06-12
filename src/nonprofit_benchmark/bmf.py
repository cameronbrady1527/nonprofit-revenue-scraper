"""IRS Exempt Organizations Business Master File parsing.

The parse core is pure: it consumes CSV lines and returns records plus a
malformed-row count. Downloading lives in a separate thin shell.
"""

import csv
from collections.abc import Iterable
from dataclasses import dataclass

BMF_URL_TEMPLATE = "https://www.irs.gov/pub/irs-soi/eo_{state}.csv"
SUBSECTION_501C3 = 3


@dataclass(frozen=True)
class BmfOrg:
    ein: str
    name: str
    city: str | None
    state: str | None
    ntee_code: str | None
    income_code: int | None
    revenue_amount: int | None


@dataclass(frozen=True)
class BmfParseResult:
    organizations: list[BmfOrg]
    skipped_rows: int


def _optional_int(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


def download_bmf(state: str) -> Iterable[str]:
    """Thin I/O shell: fetch the per-state BMF extract from the IRS."""
    import requests

    response = requests.get(BMF_URL_TEMPLATE.format(state=state.lower()), timeout=120)
    response.raise_for_status()
    return response.text.splitlines()


def parse_bmf(lines: Iterable[str]) -> BmfParseResult:
    """Parse BMF CSV lines into 501(c)(3) records; count malformed rows."""
    organizations: list[BmfOrg] = []
    skipped = 0
    for row in csv.DictReader(lines):
        try:
            if int(row["SUBSECTION"]) != SUBSECTION_501C3:
                continue
            ein = row["EIN"].strip()
            name = row["NAME"].strip()
            if not ein or not name:
                raise ValueError("missing EIN or NAME")
            organizations.append(
                BmfOrg(
                    ein=ein,
                    name=name,
                    city=(row.get("CITY") or "").strip() or None,
                    state=(row.get("STATE") or "").strip() or None,
                    ntee_code=(row.get("NTEE_CD") or "").strip() or None,
                    income_code=_optional_int(row.get("INCOME_CD")),
                    revenue_amount=_optional_int(row.get("REVENUE_AMT")),
                )
            )
        except (KeyError, TypeError, ValueError):
            skipped += 1
    return BmfParseResult(organizations=organizations, skipped_rows=skipped)
