"""ProPublica per-EIN client: request, retry, and error behavior."""

import pytest

from nonprofit_benchmark.propublica import ProPublicaClient, ProPublicaError


class StubResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("malformed JSON")
        return self._json_data


class StubSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requested_urls = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        return self._responses.pop(0)


def make_client(responses):
    session = StubSession(responses)
    sleeps = []
    client = ProPublicaClient(session=session, sleep=sleeps.append)
    return client, session, sleeps


ORG_PAYLOAD = {
    "organization": {"ein": 111000001, "name": "HUDSON VALLEY YOUTH ARTS"},
    "filings_with_data": [{"tax_prd_yr": 2023, "totrevenue": 480000}],
    "filings_without_data": [],
}


def test_get_organization_returns_payload_for_known_ein():
    client, session, _ = make_client([StubResponse(200, ORG_PAYLOAD)])

    payload = client.get_organization("111000001")

    assert payload == ORG_PAYLOAD
    assert session.requested_urls == [
        "https://projects.propublica.org/nonprofits/api/v2/organizations/111000001.json"
    ]


def test_unknown_ein_returns_none():
    client, _, _ = make_client([StubResponse(404)])

    assert client.get_organization("999999999") is None


def test_rate_limit_is_retried_with_backoff_until_success():
    client, session, sleeps = make_client(
        [StubResponse(429), StubResponse(429), StubResponse(200, ORG_PAYLOAD)]
    )

    payload = client.get_organization("111000001")

    assert payload == ORG_PAYLOAD
    assert len(session.requested_urls) == 3
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # backoff grows


def test_persistent_rate_limit_raises_propublica_error():
    client, _, _ = make_client([StubResponse(429)] * 10)

    with pytest.raises(ProPublicaError):
        client.get_organization("111000001")


def test_malformed_payload_raises_propublica_error():
    client, _, _ = make_client([StubResponse(200, json_data=None)])

    with pytest.raises(ProPublicaError):
        client.get_organization("111000001")
