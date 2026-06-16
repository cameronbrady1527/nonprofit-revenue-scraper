"""Reconcile each organization's recorded filing against IRS e-file (pure).

ProPublica's per-EIN data is often stale or incomplete: it omits returns the
IRS already publishes, and for the filings it does have it exposes only an
*aggregate* officer-compensation figure, not the per-person Part VII detail the
benchmark needs. The IRS e-file XML is more current and complete.

This decides, for one organization, what to do given its currently recorded
newest filing and the newest located IRS e-file for the same EIN. The goal is
always the most recent, most accurate filing:

- IRS e-file is newer than anything recorded (or nothing is recorded yet)
  -> INSERT an e-file filing for that year (recovers data ProPublica missed).
- IRS e-file matches the recorded year, but that record is ProPublica's
  aggregate ("api") -> UPGRADE it to e-file so `parse` extracts the real
  per-person Part VII figure.
- IRS e-file matches a recorded pdf/e-file year -> nothing (it already resolves
  against the cache during parse).
- ProPublica's recorded filing is strictly newer than any e-file -> keep it;
  data only slips through when there is genuinely no e-file to use.

The caller turns INSERT/UPGRADE into database writes; this module has no I/O.
"""

from nonprofit_benchmark.filing_selector import SOURCE_API, SOURCE_PDF
from nonprofit_benchmark.models import PARSE_STATUS_NO_PDF

ACTION_INSERT = "insert"  # add a new e-file filing for a year not yet recorded
ACTION_UPGRADE = "upgrade"  # relabel an existing filing to e-file so it gets parsed


def decide_reconciliation(
    existing_year: int | None,
    existing_source: str | None,
    existing_status: str | None,
    irs_newest_year: int | None,
) -> str | None:
    """Return ACTION_INSERT, ACTION_UPGRADE, or None for one organization.

    A same-year filing is upgraded only when it would not otherwise yield full
    e-file data: ProPublica's aggregate ("api"), or a "no_pdf" record that parse
    never schedules. A same-year "pdf" filing already resolves against the cache
    during parse, and an "efile" or already-parsed filing is left as is.
    """
    if irs_newest_year is None:
        return None
    if existing_year is None or irs_newest_year > existing_year:
        return ACTION_INSERT
    if irs_newest_year == existing_year:
        if existing_source == SOURCE_API:
            return ACTION_UPGRADE
        if existing_source == SOURCE_PDF and existing_status == PARSE_STATUS_NO_PDF:
            return ACTION_UPGRADE
    return None
