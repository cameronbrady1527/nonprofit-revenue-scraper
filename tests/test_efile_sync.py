"""IRS sync join logic and range-fetcher tests (offline, injected transport)."""

import pytest

from nonprofit_benchmark import efile_cache
from nonprofit_benchmark.efile_fetch import EfileFetcher, EfileFetchError
from nonprofit_benchmark.efile_sync import locations_from_namelist, object_id_of, sync_year

OID_A = "202401189349300001"
OID_B = "202401189349200002"

INDEX_CSV = f"""\
RETURN_ID,FILING_TYPE,EIN,TAX_PERIOD,SUB_DATE,TAXPAYER_NAME,RETURN_TYPE,DLN,OBJECT_ID
1,EFILE,012345678,202212,2024,ORG ONE,990,dln,{OID_A}
2,EFILE,099999999,202212,2024,ORG TWO,990EZ,dln,{OID_B}
"""

NAMELIST = {
    "https://z/01A.zip": [f"2024_TEOS_XML_01A/{OID_A}_public.xml", "2024_TEOS_XML_01A/manifest.txt"],
    "https://z/02A.zip": [f"2024_TEOS_XML_02A/{OID_B}_public.xml"],
}


def test_object_id_and_namelist_mapping():
    assert object_id_of("2024_TEOS_XML_01A/202412345678901234_public.xml") == "202412345678901234"
    mapped = locations_from_namelist("https://z/01A.zip", NAMELIST["https://z/01A.zip"])
    assert mapped == {OID_A: ("https://z/01A.zip", f"2024_TEOS_XML_01A/{OID_A}_public.xml")}
    assert "manifest.txt" not in str(mapped)  # only _public.xml members are kept


def test_sync_year_indexes_and_locates_across_zips():
    conn = efile_cache.connect(":memory:")
    result = sync_year(
        conn,
        2024,
        fetch_index=lambda year: INDEX_CSV,
        list_zip_urls=lambda year: list(NAMELIST),
        namelist=lambda url: NAMELIST[url],
    )
    assert (result.indexed, result.zips, result.located) == (2, 2, 2)

    a = efile_cache.resolve(conn, "012345678", 2022)
    b = efile_cache.resolve(conn, "099999999", 2022)
    assert a.object_id == OID_A and a.zip_url == "https://z/01A.zip"
    assert b.return_type == "990EZ" and b.member_name.endswith(f"{OID_B}_public.xml")


class _FakeZip:
    def __init__(self, members):
        self.members = members
        self.opens = 0

    def read(self, name):
        return self.members[name]

    def close(self):
        pass


def test_fetcher_reuses_one_archive_per_zip():
    opens = []

    def opener(url):
        opens.append(url)
        return _FakeZip({"m1": b"<xml1/>", "m2": b"<xml2/>"})

    loc1 = efile_cache.ObjectLocation("o1", "990", "https://z/01A.zip", "m1")
    loc2 = efile_cache.ObjectLocation("o2", "990", "https://z/01A.zip", "m2")
    with EfileFetcher(open_zip=opener) as fetcher:
        assert fetcher.fetch(loc1) == b"<xml1/>"
        assert fetcher.fetch(loc2) == b"<xml2/>"
    assert opens == ["https://z/01A.zip"]  # same ZIP opened only once


def test_fetcher_wraps_transport_errors():
    def boom(url):
        raise OSError("network down")

    loc = efile_cache.ObjectLocation("o", "990", "https://z/01A.zip", "m")
    with pytest.raises(EfileFetchError):
        EfileFetcher(open_zip=boom).fetch(loc)
