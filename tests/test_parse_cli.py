"""`pipeline parse` (IRS-XML path) and `pipeline sync-irs` dispatch.

The IRS network transport is replaced: `parse` gets a fake range-fetcher
returning canned 990 XML, and `sync-irs` gets a stubbed live sync. The cache
and benchmark databases are real SQLite.
"""

import nonprofit_benchmark.cli as cli
from nonprofit_benchmark import efile_cache
from nonprofit_benchmark.bmf import BmfOrg
from nonprofit_benchmark.db import (
    get_engine,
    list_executives,
    list_filings,
    upsert_organizations,
)
from nonprofit_benchmark.efile_index import IndexRecord
from nonprofit_benchmark.efile_sync import SyncResult
from nonprofit_benchmark.filing_selector import SOURCE_PDF, SelectedFiling

NS = 'xmlns="http://www.irs.gov/efile"'
XML_990 = (
    f"<Return {NS}><ReturnData><IRS990>"
    "<CYTotalRevenueAmt>480000</CYTotalRevenueAmt>"
    "<Form990PartVIISectionAGrp><PersonNm>Ada Director</PersonNm>"
    "<TitleTxt>CEO</TitleTxt>"
    "<ReportableCompFromOrgAmt>95000</ReportableCompFromOrgAmt>"
    "</Form990PartVIISectionAGrp></IRS990></ReturnData></Return>"
).encode()

OID = "202401189349300001"
MEMBER = f"2024_TEOS_XML_01A/{OID}_public.xml"
ZIP_URL = "https://z/2024_TEOS_XML_01A.zip"


class _FakeFetcher:
    """Stands in for cli.EfileFetcher; serves XML by member name."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetch(self, location):
        return {MEMBER: XML_990}[location.member_name]


def _seed_org_and_filing(db_path):
    cli.main(["init", "--db", str(db_path)])
    engine = get_engine(db_path)
    upsert_organizations(
        engine,
        [BmfOrg("111000001", "ORG ONE", "ALBANY", "NY", "A65", 4, 480000)],
    )
    cli.record_selected_filing(
        engine,
        "111000001",
        SelectedFiling(tax_year=2023, source=SOURCE_PDF, pdf_url="https://pp/pdf",
                       total_revenue=None, officer_compensation=None),
    )
    return engine


def _seed_cache(cache_path):
    conn = efile_cache.connect(cache_path)
    efile_cache.upsert_records(
        conn, [IndexRecord("111000001", 202312, "990", OID, processing_year=2024)]
    )
    efile_cache.set_locations(conn, {OID: (ZIP_URL, MEMBER)})
    conn.close()


def test_parse_extracts_from_irs_xml(tmp_path, monkeypatch):
    db_path = tmp_path / "benchmark.db"
    cache_path = tmp_path / "irs_cache.db"
    engine = _seed_org_and_filing(db_path)
    _seed_cache(cache_path)
    monkeypatch.setattr(cli, "EfileFetcher", _FakeFetcher)

    code = cli.main(["parse", "--state", "NY", "--db", str(db_path), "--cache", str(cache_path)])

    assert code == 0
    [filing] = list_filings(engine, state="NY")
    assert filing.parse_status == "parsed"
    assert filing.total_revenue == 480000
    [executive] = list_executives(engine, filing_id=filing.id)
    assert executive.name == "Ada Director"
    assert executive.compensation_org == 95000


def test_parse_leaves_filing_unparsed_when_not_in_cache(tmp_path, monkeypatch):
    db_path = tmp_path / "benchmark.db"
    cache_path = tmp_path / "irs_cache.db"
    engine = _seed_org_and_filing(db_path)
    efile_cache.connect(cache_path).close()  # empty cache: nothing resolves
    monkeypatch.setattr(cli, "EfileFetcher", _FakeFetcher)

    code = cli.main(["parse", "--state", "NY", "--db", str(db_path), "--cache", str(cache_path)])

    assert code == 0
    [filing] = list_filings(engine, state="NY")
    assert filing.parse_status == "unparsed"  # preserved for a later sync-irs
    assert list_executives(engine, filing_id=filing.id) == []


def test_sync_irs_invokes_live_sync_per_year(tmp_path, monkeypatch):
    cache_path = tmp_path / "irs_cache.db"
    calls = []

    def fake_sync(conn, year):
        calls.append(year)
        return SyncResult(year=year, indexed=10, zips=12, located=9)

    monkeypatch.setattr(cli.efile_sync, "sync_year_live", fake_sync)

    code = cli.main(["sync-irs", "--year", "2024", "--year", "2025", "--cache", str(cache_path)])

    assert code == 0
    assert calls == [2024, 2025]
