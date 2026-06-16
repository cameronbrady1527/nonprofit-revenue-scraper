"""Sync IRS e-file data into the local cache (thin I/O shell).

For each processing year: download `index_{year}.csv` into the cache, list the
year's bulk ZIPs, and read each ZIP's central directory — a cheap HTTP range
read, never a full download — to learn which ZIP holds each object's XML. The
result is a fully located cache so `parse` can later range-fetch only the few
XMLs it needs. All network access (index download, page scrape, ZIP namelist)
is injected, so the join logic is exercised offline.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from nonprofit_benchmark import efile_cache
from nonprofit_benchmark.efile_index import parse_index

INDEX_URL = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/index_{year}.csv"
DOWNLOADS_PAGE = "https://www.irs.gov/charities-non-profits/form-990-series-downloads"
_ZIP_URL_RE = r"https://apps\.irs\.gov/pub/epostcard/990/xml/%d/[^\"'<> ]+\.zip"


@dataclass(frozen=True)
class SyncResult:
    year: int
    indexed: int  # supported returns recorded from the index
    zips: int  # bulk ZIPs whose directories were read
    located: int  # indexed returns matched to a ZIP member


def object_id_of(member_name: str) -> str:
    """`2023_TEOS_XML_01A/202300109349300000_public.xml` -> `202300109349300000`."""
    return member_name.rsplit("/", 1)[-1].split("_", 1)[0]


def locations_from_namelist(zip_url: str, member_names: Iterable[str]) -> dict[str, tuple[str, str]]:
    """Map each return XML member in a ZIP to `(zip_url, member_name)`."""
    return {
        object_id_of(name): (zip_url, name)
        for name in member_names
        if name.endswith("_public.xml")
    }


def sync_year(
    conn,
    year: int,
    *,
    fetch_index: Callable[[int], str],
    list_zip_urls: Callable[[int], list[str]],
    namelist: Callable[[str], list[str]],
) -> SyncResult:
    """Populate the cache for one processing year using injected transports."""
    indexed = efile_cache.upsert_records(conn, parse_index(fetch_index(year).splitlines(), year))
    zip_urls = list_zip_urls(year)
    located = 0
    for zip_url in zip_urls:
        located += efile_cache.set_locations(conn, locations_from_namelist(zip_url, namelist(zip_url)))
    return SyncResult(year=year, indexed=indexed, zips=len(zip_urls), located=located)


def sync_year_live(conn, year: int) -> SyncResult:
    """`sync_year` wired to the real IRS endpoints."""
    return sync_year(
        conn,
        year,
        fetch_index=_fetch_index,
        list_zip_urls=_list_zip_urls,
        namelist=_namelist,
    )


def _get(url: str) -> bytes:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def _fetch_index(year: int) -> str:
    return _get(INDEX_URL.format(year=year)).decode("utf-8", "replace")


def _list_zip_urls(year: int) -> list[str]:
    html = _get(DOWNLOADS_PAGE).decode("utf-8", "replace")
    return sorted(set(re.findall(_ZIP_URL_RE % year, html)))


def _namelist(zip_url: str) -> list[str]:
    from remotezip import RemoteZip

    with RemoteZip(zip_url) as archive:
        return archive.namelist()
