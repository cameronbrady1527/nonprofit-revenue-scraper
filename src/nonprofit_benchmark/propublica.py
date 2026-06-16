"""ProPublica Nonprofit Explorer per-EIN client (thin I/O wrapper).

The session and sleep function are injectable so tests exercise retry
and error behavior without network or real waiting.
"""

import time
from collections.abc import Callable

BASE_URL = "https://projects.propublica.org/nonprofits/api/v2"


class ProPublicaError(Exception):
    """The API answered in a way we can't use (after retries)."""


class ProPublicaRateLimited(ProPublicaError):
    """Rate-limited (429) even after the client's own backoff; a concurrent
    caller can react by slowing its worker pool down."""


class ProPublicaClient:
    def __init__(
        self,
        session=None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 4,
    ):
        if session is None:
            import requests

            session = requests.Session()
        self._session = session
        self._sleep = sleep
        self._max_retries = max_retries

    def get_organization(self, ein: str) -> dict | None:
        """Fetch an organization's profile and filings; None if unknown EIN."""
        url = f"{BASE_URL}/organizations/{ein}.json"
        for attempt in range(self._max_retries + 1):
            response = self._session.get(url, timeout=30)
            if response.status_code == 404:
                return None
            if response.status_code == 429:
                if attempt == self._max_retries:
                    break
                self._sleep(2**attempt)
                continue
            try:
                return response.json()
            except ValueError as exc:
                raise ProPublicaError(f"Malformed payload for EIN {ein}") from exc
        raise ProPublicaRateLimited(f"Rate-limited for EIN {ein} after {self._max_retries} retries")
