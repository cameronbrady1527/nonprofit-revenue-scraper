"""Downloading 990 PDFs (thin I/O shell).

ProPublica's PDF host sometimes 403s plain library requests; the
browser-like header set (with ProPublica referer) is the strategy the
legacy scraper validated in production, with a simple-headers fallback.
"""

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://projects.propublica.org/nonprofits/",
}

FALLBACK_HEADERS = {"User-Agent": "python-requests/2.32.0", "Accept": "*/*"}


class PdfDownloadError(Exception):
    """The PDF could not be fetched; record the filing as failed."""


def download_pdf(url: str, session=None) -> bytes:
    if session is None:
        import requests

        session = requests.Session()

    last_status = None
    for headers in (BROWSER_HEADERS, FALLBACK_HEADERS):
        response = session.get(url, headers=headers, timeout=60, allow_redirects=True)
        if response.status_code == 200:
            return response.content
        last_status = response.status_code
    raise PdfDownloadError(f"Could not download {url} (last status {last_status})")
