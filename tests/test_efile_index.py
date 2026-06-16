"""IRS e-file index parsing + object-location cache tests (pure / offline)."""

from nonprofit_benchmark import efile_cache
from nonprofit_benchmark.efile_index import IndexRecord, parse_index

INDEX_CSV = """\
RETURN_ID,FILING_TYPE,EIN,TAX_PERIOD,SUB_DATE,TAXPAYER_NAME,RETURN_TYPE,DLN,OBJECT_ID
1,EFILE,203518700,202212,2023,FULL 990 ORG,990,93493018011043,202340189349301104
2,EFILE,12345678,202206,2023,SHORT EIN EZ,990EZ,93493018011044,202340189349301105
3,EFILE,366054378,202112,2023,A 990T WE SKIP,990T,93393018001093,202340189339300109
4,EFILE,990000001,202212,2023,NO OBJECT,990,,
"""


def test_parse_index_keeps_supported_types_and_pads_ein():
    records = list(parse_index(INDEX_CSV.splitlines(), processing_year=2023))
    assert len(records) == 2  # 990 + 990EZ; the 990-T and the empty row are dropped
    ez = records[1]
    assert ez.ein == "012345678"  # zero-padded to 9
    assert ez.return_type == "990EZ"
    assert ez.tax_period == 202206
    assert ez.tax_year == 2022


def test_resolve_returns_newest_located_filing():
    conn = efile_cache.connect(":memory:")
    efile_cache.upsert_records(
        conn,
        [
            IndexRecord("012345678", 202212, "990", "OID_ORIG", processing_year=2023),
            IndexRecord("012345678", 202212, "990", "OID_AMENDED", processing_year=2024),
        ],
    )
    # Only the amended object has a known ZIP location.
    located = efile_cache.set_locations(conn, {"OID_AMENDED": ("https://z/zip", "m/OID_AMENDED.xml")})
    assert located == 1

    result = efile_cache.resolve(conn, "12345678", 2022)  # caller passes unpadded EIN
    assert result is not None
    assert result.object_id == "OID_AMENDED"
    assert result.member_name == "m/OID_AMENDED.xml"


def test_resolve_skips_unlocated_and_unknown():
    conn = efile_cache.connect(":memory:")
    efile_cache.upsert_records(
        conn, [IndexRecord("012345678", 202212, "990", "OID", processing_year=2023)]
    )
    assert efile_cache.resolve(conn, "012345678", 2022) is None  # no location attached yet
    # Locating an object id we never indexed changes nothing.
    assert efile_cache.set_locations(conn, {"GHOST": ("z", "m")}) == 0
    assert efile_cache.resolve(conn, "999999999", 2022) is None
