"""`pipeline parse`: PDF-only filings -> Gemini -> executives in the database."""

import pytest

import nonprofit_benchmark.cli as cli
from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.db import (
    get_engine,
    list_executives,
    list_filings,
    record_selected_filing,
    upsert_organizations,
)
from nonprofit_benchmark.filing_selector import SelectedFiling
from nonprofit_benchmark.gemini_parser import (
    ExecutiveRecord,
    FilingExtraction,
    GeminiParseError,
)


def org(ein):
    return BmfOrg(ein=ein, name=f"ORG {ein}", city="ALBANY", state="NY",
                  ntee_code="A65", income_code=4, revenue_amount=480000)


def pdf_filing(year=2024, url="https://pdf/x"):
    return SelectedFiling(tax_year=year, source="pdf", pdf_url=url,
                          total_revenue=None, officer_compensation=None)


EXTRACTION = FilingExtraction(
    total_revenue=512000,
    executives=[
        ExecutiveRecord(name="JANE DOE", title="EXECUTIVE DIRECTOR",
                        compensation_org=95000, compensation_related=0,
                        compensation_other=8200),
        ExecutiveRecord(name="JOHN ROE", title="CFO",
                        compensation_org=78000, compensation_related=12000,
                        compensation_other=0),
    ],
)


class StubParser:
    def __init__(self, results):
        self._results = results  # pdf_url-keyed extraction or exception
        self.parsed_urls = []

    def parse_url(self, url):
        self.parsed_urls.append(url)
        result = self._results[url]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Seeded pipeline whose `parse` command can be run repeatedly with stubs."""

    class Pipeline:
        db_path = tmp_path / "benchmark.db"

        def seed(self, filings_by_ein, orgs=None):
            cli.main(["init", "--db", str(self.db_path)])
            engine = get_engine(self.db_path)
            upsert_organizations(engine, orgs or [org(ein) for ein in filings_by_ein])
            for ein, selected in filings_by_ein.items():
                record_selected_filing(engine, ein, selected)

        def parse(self, results, *extra_args):
            stub = StubParser(results)
            monkeypatch.setattr(cli, "GeminiParser", lambda: stub)
            monkeypatch.setattr(cli, "download_pdf", lambda url: f"bytes:{url}")
            stub.parse = lambda pdf_bytes: stub.parse_url(str(pdf_bytes).removeprefix("bytes:"))
            code = cli.main(["parse", "--state", "NY", "--db", str(self.db_path), *extra_args])
            return stub, code

    return Pipeline()


@pytest.fixture
def run_parse(pipeline):
    """Runner: run_parse(filings_by_ein, results) -> (db_path, stub, exit_code)."""

    def run(filings_by_ein, results):
        pipeline.seed(filings_by_ein)
        stub, code = pipeline.parse(results)
        return pipeline.db_path, stub, code

    return run


def test_parse_stores_each_executive_with_separate_columns(run_parse):
    db_path, _, code = run_parse(
        {"111000001": pdf_filing(url="https://pdf/1")},
        {"https://pdf/1": EXTRACTION},
    )

    assert code == 0
    engine = get_engine(db_path)
    filing = list_filings(engine)[0]
    assert filing.parse_status == "parsed"
    assert filing.total_revenue == 512000

    execs = {e.name: e for e in list_executives(engine, filing.id)}
    assert len(execs) == 2
    jane = execs["JANE DOE"]
    assert jane.title == "EXECUTIVE DIRECTOR"
    assert (jane.compensation_org, jane.compensation_related, jane.compensation_other) == (
        95000, 0, 8200,
    )


def test_failed_parse_marks_filing_failed_and_run_continues(run_parse):
    db_path, _, code = run_parse(
        {
            "111000001": pdf_filing(url="https://pdf/bad"),
            "111000002": pdf_filing(url="https://pdf/good"),
        },
        {
            "https://pdf/bad": GeminiParseError("refusal"),
            "https://pdf/good": EXTRACTION,
        },
    )

    assert code == 0
    engine = get_engine(db_path)
    by_ein = {f.ein: f for f in list_filings(engine)}
    failed = by_ein["111000001"]
    assert failed.parse_status == "failed"
    assert list_executives(engine, failed.id) == []
    assert by_ein["111000002"].parse_status == "parsed"


def test_rerun_after_interrupt_repeats_no_completed_or_hopeless_work(pipeline):
    pipeline.seed(
        {
            "111000001": pdf_filing(url="https://pdf/1"),
            "111000002": pdf_filing(url="https://pdf/bad"),
        }
    )
    _, code = pipeline.parse(
        {"https://pdf/1": EXTRACTION, "https://pdf/bad": GeminiParseError("refusal")}
    )
    assert code == 0

    rerun_stub, code = pipeline.parse({})
    assert code == 0
    assert rerun_stub.parsed_urls == []  # parsed and failed filings stay untouched


def test_retry_failed_flag_reattempts_only_failures(pipeline):
    pipeline.seed(
        {
            "111000001": pdf_filing(url="https://pdf/1"),
            "111000002": pdf_filing(url="https://pdf/bad"),
        }
    )
    pipeline.parse(
        {"https://pdf/1": EXTRACTION, "https://pdf/bad": GeminiParseError("refusal")}
    )

    retry_stub, code = pipeline.parse({"https://pdf/bad": EXTRACTION}, "--retry-failed")
    assert code == 0
    assert retry_stub.parsed_urls == ["https://pdf/bad"]

    engine = get_engine(pipeline.db_path)
    by_ein = {f.ein: f for f in list_filings(engine)}
    assert by_ein["111000002"].parse_status == "parsed"


def test_revenue_band_flags_limit_parsing_to_orgs_near_the_band(pipeline):
    def org_with_revenue(ein, revenue):
        return BmfOrg(ein=ein, name=f"ORG {ein}", city="ALBANY", state="NY",
                      ntee_code="A65", income_code=4, revenue_amount=revenue)

    pipeline.seed(
        {
            "111000001": pdf_filing(url="https://pdf/in-band"),
            "111000002": pdf_filing(url="https://pdf/far-out"),
        },
        orgs=[
            org_with_revenue("111000001", 500_000),
            org_with_revenue("111000002", 50_000_000),
        ],
    )

    stub, code = pipeline.parse(
        {"https://pdf/in-band": EXTRACTION},
        "--revenue-min", "250000", "--revenue-max", "1000000",
    )
    assert code == 0
    assert stub.parsed_urls == ["https://pdf/in-band"]


def test_only_unparsed_filings_are_attempted(run_parse):
    no_pdf = SelectedFiling(tax_year=2024, source="pdf", pdf_url=None,
                            total_revenue=None, officer_compensation=None)
    api_filing = SelectedFiling(tax_year=2023, source="api", pdf_url=None,
                                total_revenue=480000, officer_compensation=120000)

    _, stub, code = run_parse(
        {
            "111000001": pdf_filing(url="https://pdf/1"),
            "111000002": no_pdf,
            "111000003": api_filing,
        },
        {"https://pdf/1": EXTRACTION},
    )

    assert code == 0
    assert stub.parsed_urls == ["https://pdf/1"]
