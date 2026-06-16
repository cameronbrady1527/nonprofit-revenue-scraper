"""Range-fetch a single 990 XML from the IRS bulk ZIPs (thin I/O shell).

Given an `ObjectLocation` from the cache, pull just that return's XML out of
its national ZIP via HTTP range requests — no full-ZIP download. Each ZIP's
central directory is read once and reused across every member fetched from it
within a parse run, so processing many filings from the same ZIP costs one
directory read, not one per filing. The ZIP opener is injectable for tests.
"""

from collections.abc import Callable

# The IRS 2025+ bulk ZIPs compress members with Deflate64 (method 9), which the
# stdlib zipfile (used by remotezip) cannot inflate — it raises "That
# compression method is not supported". Importing this patches zipfile's
# decompressor registry to handle Deflate64, transparently fixing remotezip.
import zipfile_deflate64  # noqa: F401

from nonprofit_benchmark.efile_cache import ObjectLocation


class EfileFetchError(Exception):
    """The XML member could not be fetched; record the filing as failed."""


class EfileFetcher:
    """Fetches member XML bytes, caching one open archive per ZIP URL."""

    def __init__(self, open_zip: Callable[[str], object] | None = None):
        self._open = open_zip or _open_remote_zip
        self._archives: dict[str, object] = {}

    def fetch(self, location: ObjectLocation) -> bytes:
        try:
            archive = self._archives.get(location.zip_url)
            if archive is None:
                archive = self._open(location.zip_url)
                self._archives[location.zip_url] = archive
            return archive.read(location.member_name)
        except EfileFetchError:
            raise
        except Exception as exc:
            raise EfileFetchError(
                f"Could not fetch {location.member_name} from {location.zip_url}: {exc}"
            ) from exc

    def close(self) -> None:
        for archive in self._archives.values():
            closer = getattr(archive, "close", None)
            if closer is not None:
                try:
                    closer()
                except Exception:
                    pass
        self._archives.clear()

    def __enter__(self) -> "EfileFetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _open_remote_zip(zip_url: str):
    from remotezip import RemoteZip

    return RemoteZip(zip_url)
