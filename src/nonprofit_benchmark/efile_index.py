"""Parse the IRS e-file index (pure, no I/O).

The IRS publishes one `index_{year}.csv` per processing year listing every
electronically filed return received that year, keyed by an 18-digit OBJECT_ID
that names the return's XML inside the year's bulk ZIPs. `processing year` is
when the IRS received the return, not its tax year — a tax-year-2023 return is
typically processed in 2024 — so several index years must be parsed to cover a
given tax year. We keep only the return types this pipeline can parse.
"""

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

SUPPORTED_RETURN_TYPES = frozenset({"990", "990EZ", "990PF"})


@dataclass(frozen=True)
class IndexRecord:
    ein: str  # 9-digit, zero-padded
    tax_period: int  # YYYYMM
    return_type: str
    object_id: str
    processing_year: int

    @property
    def tax_year(self) -> int:
        return self.tax_period // 100


def parse_index(rows: Iterable[str], processing_year: int) -> Iterator[IndexRecord]:
    """Yield one IndexRecord per supported return in an index CSV.

    Rows of other return types (990-T, 990-N, ...) and rows missing an EIN,
    a numeric tax period, or an object id are skipped silently.
    """
    for row in csv.DictReader(rows):
        return_type = (row.get("RETURN_TYPE") or "").strip()
        if return_type not in SUPPORTED_RETURN_TYPES:
            continue
        ein = (row.get("EIN") or "").strip()
        tax_period = (row.get("TAX_PERIOD") or "").strip()
        object_id = (row.get("OBJECT_ID") or "").strip()
        if not (ein and tax_period.isdigit() and object_id):
            continue
        yield IndexRecord(
            ein=ein.zfill(9),
            tax_period=int(tax_period),
            return_type=return_type,
            object_id=object_id,
            processing_year=processing_year,
        )
