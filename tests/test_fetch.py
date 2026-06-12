"""`pipeline fetch`: roster -> ProPublica -> filing selection -> database."""

import pytest

import nonprofit_benchmark.cli as cli
from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.db import get_engine, list_filings, upsert_organizations
from nonprofit_benchmark.propublica import ProPublicaError


def org(ein, state="NY"):
    return BmfOrg(
        ein=ein,
        name=f"ORG {ein}",
        city="ALBANY",
        state=state,
        ntee_code="A65",
        income_code=4,
        revenue_amount=480000,
    )


def payload(filings_with_data=(), filings_without_data=()):
    return {
        "organization": {},
        "filings_with_data": list(filings_with_data),
        "filings_without_data": list(filings_without_data),
    }


class StubClient:
    """Maps EIN -> payload dict, None (404), or an exception to raise."""

    def __init__(self, by_ein):
        self._by_ein = by_ein

    def get_organization(self, ein):
        result = self._by_ein[ein]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def fetch(tmp_path, monkeypatch):
    """Returns a runner: fetch(orgs, by_ein) -> (db_path, exit_code)."""
    db_path = tmp_path / "benchmark.db"

    def run(orgs, by_ein):
        cli.main(["init", "--db", str(db_path)])
        upsert_organizations(get_engine(db_path), orgs)
        monkeypatch.setattr(cli, "ProPublicaClient", lambda: StubClient(by_ein))
        code = cli.main(["fetch", "--state", "NY", "--db", str(db_path)])
        return db_path, code

    return run


def test_fetch_records_newest_filing_with_classification(fetch):
    db_path, code = fetch(
        [org("111000001"), org("111000002"), org("111000003"), org("111000004")],
        {
            # newest is structured -> api / parsed, data stored
            "111000001": payload(
                filings_with_data=[
                    {"tax_prd_yr": 2023, "tax_prd": 202312, "totrevenue": 480000,
                     "compnsatncurrofcr": 120000, "pdf_url": "https://pdf/1-2023"}
                ]
            ),
            # newest is pdf-only -> pdf / unparsed
            "111000002": payload(
                filings_with_data=[{"tax_prd_yr": 2022, "tax_prd": 202212, "totrevenue": 1}],
                filings_without_data=[
                    {"tax_prd_yr": 2024, "tax_prd": 202412, "pdf_url": "https://pdf/2-2024"}
                ],
            ),
            # newest is pdf-only without a pdf -> pdf / no_pdf
            "111000003": payload(
                filings_without_data=[{"tax_prd_yr": 2024, "tax_prd": 202412}]
            ),
            # unknown to ProPublica -> no filing row
            "111000004": None,
        },
    )

    assert code == 0
    filings = {f.ein: f for f in list_filings(get_engine(db_path))}

    structured = filings["111000001"]
    assert (structured.tax_year, structured.source, structured.parse_status) == (
        2023, "api", "parsed",
    )
    assert structured.total_revenue == 480000
    assert structured.officer_compensation == 120000

    pdf_only = filings["111000002"]
    assert (pdf_only.tax_year, pdf_only.source, pdf_only.parse_status) == (
        2024, "pdf", "unparsed",
    )
    assert pdf_only.pdf_url == "https://pdf/2-2024"

    assert filings["111000003"].parse_status == "no_pdf"
    assert "111000004" not in filings


def test_refetch_does_not_duplicate_filings(fetch):
    by_ein = {
        "111000001": payload(
            filings_with_data=[{"tax_prd_yr": 2023, "tax_prd": 202312, "totrevenue": 480000}]
        )
    }
    db_path, _ = fetch([org("111000001")], by_ein)

    code = cli.main(["fetch", "--state", "NY", "--db", str(db_path)])

    assert code == 0
    assert len(list_filings(get_engine(db_path))) == 1


def test_one_failing_org_does_not_abort_the_run(fetch, capsys):
    db_path, code = fetch(
        [org("111000001"), org("111000002")],
        {
            "111000001": ProPublicaError("rate-limited after retries"),
            "111000002": payload(
                filings_with_data=[{"tax_prd_yr": 2023, "tax_prd": 202312, "totrevenue": 1}]
            ),
        },
    )

    assert code == 0
    assert [f.ein for f in list_filings(get_engine(db_path))] == ["111000002"]
    assert "1 errors" in capsys.readouterr().out
