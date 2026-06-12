"""Downloading 990 PDFs: browser-header strategy with fallback."""

import pytest

from nonprofit_benchmark.pdfs import PdfDownloadError, download_pdf


class StubResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class StubSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.headers_seen = []

    def get(self, url, headers=None, timeout=None, allow_redirects=None):
        self.headers_seen.append(headers or {})
        return self._responses.pop(0)


def test_successful_download_returns_pdf_bytes():
    session = StubSession([StubResponse(200, b"%PDF-1.7 data")])

    assert download_pdf("https://pdf/x", session=session) == b"%PDF-1.7 data"


def test_403_falls_back_to_alternate_headers():
    session = StubSession([StubResponse(403), StubResponse(200, b"%PDF-ok")])

    content = download_pdf("https://pdf/x", session=session)

    assert content == b"%PDF-ok"
    assert len(session.headers_seen) == 2
    assert session.headers_seen[0] != session.headers_seen[1]


def test_persistent_failure_raises_download_error():
    session = StubSession([StubResponse(403), StubResponse(404)])

    with pytest.raises(PdfDownloadError):
        download_pdf("https://pdf/x", session=session)
