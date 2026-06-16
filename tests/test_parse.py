"""`pipeline parse`: PDF-only filings -> IRS e-file XML -> executives in the DB.

The CF-blocked PDF + Gemini path was replaced by range-fetching the return's
XML from the IRS bulk ZIPs (see efile_*). These tests drive the real cache and
scheduler but inject a fake range-fetcher that serves canned 990 XML — so they
cover the same behaviors (failure handling, rerun, retry, banding, status
gating) the Gemini version did, over the new source.
"""

import pytest

import nonprofit_benchmark.cli as cli
from nonprofit_benchmark import efile_cache
from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.db import (
    get_engine,
    list_executives,
    list_filings,
    record_selected_filing,
    upsert_organizations,
)
from nonprofit_benchmark.efile_index import IndexRecord
from nonprofit_benchmark.filing_selector import SelectedFiling

NS = 'xmlns="http://www.irs.gov/efile"'
ZIP_URL = "https://z/2024_TEOS_XML_01A.zip"

# A two-executive 990 with the three compensation columns kept distinct.
GOOD_XML = (
    f"<Return {NS}><ReturnData><IRS990>"
    "<CYTotalRevenueAmt>512000</CYTotalRevenueAmt>"
    "<Form990PartVIISectionAGrp><PersonNm>JANE DOE</PersonNm>"
    "<TitleTxt>EXECUTIVE DIRECTOR</TitleTxt>"
    "<ReportableCompFromOrgAmt>95000</ReportableCompFromOrgAmt>"
    "<ReportableCompFromRltdOrgAmt>0</ReportableCompFromRltdOrgAmt>"
    "<OtherCompensationAmt>8200</OtherCompensationAmt></Form990PartVIISectionAGrp>"
    "<Form990PartVIISectionAGrp><PersonNm>JOHN ROE</PersonNm><TitleTxt>CFO</TitleTxt>"
    "<ReportableCompFromOrgAmt>78000</ReportableCompFromOrgAmt>"
    "<ReportableCompFromRltdOrgAmt>12000</ReportableCompFromRltdOrgAmt>"
    "<OtherCompensationAmt>0</OtherCompensationAmt></Form990PartVIISectionAGrp>"
    "</IRS990></ReturnData></Return>"
).encode()
BAD_XML = b"<Return><unclosed>"  # parse_990_xml -> EfileParseError -> recorded failed


def org(ein):
    return BmfOrg(ein=ein, name=f"ORG {ein}", city="ALBANY", state="NY",
                  ntee_code="A65", income_code=4, revenue_amount=480000)


def pdf_filing(year=2024):
    return SelectedFiling(tax_year=year, source="pdf", pdf_url="https://pp/pdf",
                          total_revenue=None, officer_compensation=None)


def _object_id(ein, year):
    return f"{ein.zfill(9)}{year}"


def _member(ein, year):
    return f"2024_TEOS_XML_01A/{_object_id(ein, year)}_public.xml"


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Seeded pipeline whose `parse` command can be run repeatedly with stubs."""

    class Pipeline:
        db_path = tmp_path / "benchmark.db"
        cache_path = tmp_path / "irs_cache.db"

        def seed(self, filings_by_ein, orgs=None):
            cli.main(["init", "--db", str(self.db_path)])
            engine = get_engine(self.db_path)
            upsert_organizations(engine, orgs or [org(ein) for ein in filings_by_ein])
            self.selected = dict(filings_by_ein)
            conn = efile_cache.connect(self.cache_path)
            for ein, selected in filings_by_ein.items():
                record_selected_filing(engine, ein, selected)
                # Every pdf-source filing is locatable in the IRS cache.
                oid = _object_id(ein, selected.tax_year)
                efile_cache.upsert_records(
                    conn,
                    [IndexRecord(ein.zfill(9), selected.tax_year * 100 + 12, "990",
                                 oid, processing_year=selected.tax_year + 1)],
                )
                efile_cache.set_locations(conn, {oid: (ZIP_URL, _member(ein, selected.tax_year))})
            conn.close()

        def parse(self, results, *extra_args):
            """results maps EIN -> "ok" | "bad"; returns (fetched_eins, exit_code)."""
            by_member = {
                _member(ein, self.selected[ein].tax_year): outcome
                for ein, outcome in results.items()
            }
            member_to_ein = {
                _member(ein, sel.tax_year): ein for ein, sel in self.selected.items()
            }
            fetched: list[str] = []

            class FakeFetcher:
                def __enter__(self_):
                    return self_

                def __exit__(self_, *exc):
                    return False

                def fetch(self_, location):
                    fetched.append(location.member_name)
                    return GOOD_XML if by_member[location.member_name] == "ok" else BAD_XML

            monkeypatch.setattr(cli, "EfileFetcher", FakeFetcher)
            code = cli.main(
                ["parse", "--state", "NY", "--db", str(self.db_path),
                 "--cache", str(self.cache_path), *extra_args]
            )
            return [member_to_ein[m] for m in fetched], code

    return Pipeline()


@pytest.fixture
def run_parse(pipeline):
    """Runner: run_parse(filings_by_ein, results) -> (db_path, fetched_eins, exit_code)."""

    def run(filings_by_ein, results):
        pipeline.seed(filings_by_ein)
        fetched, code = pipeline.parse(results)
        return pipeline.db_path, fetched, code

    return run


def test_parse_stores_each_executive_with_separate_columns(run_parse):
    db_path, _, code = run_parse({"111000001": pdf_filing()}, {"111000001": "ok"})

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
        {"111000001": pdf_filing(), "111000002": pdf_filing()},
        {"111000001": "bad", "111000002": "ok"},
    )

    assert code == 0
    engine = get_engine(db_path)
    by_ein = {f.ein: f for f in list_filings(engine)}
    failed = by_ein["111000001"]
    assert failed.parse_status == "failed"
    assert list_executives(engine, failed.id) == []
    assert by_ein["111000002"].parse_status == "parsed"


def test_rerun_after_interrupt_repeats_no_completed_or_hopeless_work(pipeline):
    pipeline.seed({"111000001": pdf_filing(), "111000002": pdf_filing()})
    _, code = pipeline.parse({"111000001": "ok", "111000002": "bad"})
    assert code == 0

    fetched, code = pipeline.parse({})
    assert code == 0
    assert fetched == []  # parsed and failed filings stay untouched


def test_retry_failed_flag_reattempts_only_failures(pipeline):
    pipeline.seed({"111000001": pdf_filing(), "111000002": pdf_filing()})
    pipeline.parse({"111000001": "ok", "111000002": "bad"})

    fetched, code = pipeline.parse({"111000002": "ok"}, "--retry-failed")
    assert code == 0
    assert fetched == ["111000002"]

    engine = get_engine(pipeline.db_path)
    by_ein = {f.ein: f for f in list_filings(engine)}
    assert by_ein["111000002"].parse_status == "parsed"


def test_revenue_band_flags_limit_parsing_to_orgs_near_the_band(pipeline):
    def org_with_revenue(ein, revenue):
        return BmfOrg(ein=ein, name=f"ORG {ein}", city="ALBANY", state="NY",
                      ntee_code="A65", income_code=4, revenue_amount=revenue)

    pipeline.seed(
        {"111000001": pdf_filing(), "111000002": pdf_filing()},
        orgs=[
            org_with_revenue("111000001", 500_000),
            org_with_revenue("111000002", 50_000_000),
        ],
    )

    fetched, code = pipeline.parse(
        {"111000001": "ok"}, "--revenue-min", "250000", "--revenue-max", "1000000"
    )
    assert code == 0
    assert fetched == ["111000001"]


def test_only_unparsed_filings_are_attempted(run_parse):
    no_pdf = SelectedFiling(tax_year=2024, source="pdf", pdf_url=None,
                            total_revenue=None, officer_compensation=None)
    api_filing = SelectedFiling(tax_year=2023, source="api", pdf_url=None,
                                total_revenue=480000, officer_compensation=120000)

    _, fetched, code = run_parse(
        {"111000001": pdf_filing(), "111000002": no_pdf, "111000003": api_filing},
        {"111000001": "ok"},
    )

    assert code == 0
    assert fetched == ["111000001"]
