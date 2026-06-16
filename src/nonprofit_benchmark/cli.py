"""The single `pipeline` CLI entry point."""

import argparse
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from nonprofit_benchmark import efile_cache, efile_sync
from nonprofit_benchmark.bmf import download_bmf, parse_bmf
from nonprofit_benchmark.db import (
    get_engine,
    init_db,
    is_initialized,
    list_filings,
    list_organizations,
    reconcile_with_efile,
    record_parse_failure,
    record_parse_success,
    record_selected_filing,
    upsert_organizations,
)
from nonprofit_benchmark.efile_fetch import EfileFetcher, EfileFetchError
from nonprofit_benchmark.efile_xml import EfileParseError, parse_990_xml
from nonprofit_benchmark.filing_selector import select_filing
from nonprofit_benchmark.parse_scheduler import schedule_filings
from nonprofit_benchmark.propublica import (
    ProPublicaClient,
    ProPublicaError,
    ProPublicaRateLimited,
)
from nonprofit_benchmark.throttle import AdaptiveThrottle

DEFAULT_DB = "benchmark.db"
DEFAULT_CACHE = "irs_cache.db"
DEFAULT_WORKERS = 8


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def _progress(done: int, total: int, started: float, **tally: int) -> None:
    """One-line progress with rate and ETA: `...300/5000 (...) — 42/s, ETA 1m52s`."""
    elapsed = time.monotonic() - started
    rate = done / elapsed if elapsed > 0 else 0.0
    eta = (total - done) / rate if rate > 0 else 0.0
    detail = ", ".join(f"{value} {label}" for label, value in tally.items())
    detail = f" ({detail})" if detail else ""
    print(f"  ...{done}/{total}{detail} — {rate:.0f}/s, ETA {_format_duration(eta)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Nonprofit executive compensation data pipeline",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init_cmd = subcommands.add_parser("init", help="Create the local database")
    init_cmd.add_argument("--db", default=DEFAULT_DB, help="Path to the SQLite database file")

    seed_cmd = subcommands.add_parser(
        "seed", help="Seed the 501(c)(3) roster for a state from the IRS BMF"
    )
    seed_cmd.add_argument("--state", required=True, help="Two-letter state code")
    seed_cmd.add_argument("--db", default=DEFAULT_DB, help="Path to the SQLite database file")
    seed_cmd.add_argument(
        "--file", help="Local BMF CSV to ingest instead of downloading from the IRS"
    )

    fetch_cmd = subcommands.add_parser(
        "fetch", help="Fetch filings from ProPublica for every seeded org in a state"
    )
    fetch_cmd.add_argument("--state", required=True, help="Two-letter state code")
    fetch_cmd.add_argument("--db", default=DEFAULT_DB, help="Path to the SQLite database file")
    fetch_cmd.add_argument("--limit", type=int, help="Only fetch the first N organizations")
    fetch_cmd.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help="Concurrent ProPublica requests (auto-throttles on rate limits)",
    )

    parse_cmd = subcommands.add_parser(
        "parse", help="Parse unparsed PDF-only filings from IRS e-file XML for a state"
    )
    parse_cmd.add_argument("--state", required=True, help="Two-letter state code")
    parse_cmd.add_argument("--db", default=DEFAULT_DB, help="Path to the SQLite database file")
    parse_cmd.add_argument("--limit", type=int, help="Only parse the first N filings")
    parse_cmd.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also re-attempt filings whose previous parse failed",
    )
    parse_cmd.add_argument(
        "--revenue-min", type=int,
        help="Only parse orgs whose known revenue is at or near this floor",
    )
    parse_cmd.add_argument(
        "--revenue-max", type=int,
        help="Only parse orgs whose known revenue is at or near this ceiling",
    )
    parse_cmd.add_argument(
        "--cache", default=DEFAULT_CACHE,
        help="Path to the IRS e-file cache built by `sync-irs`",
    )
    parse_cmd.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help="Concurrent e-file XML fetches",
    )

    sync_cmd = subcommands.add_parser(
        "sync-irs",
        help="Download IRS e-file index + ZIP directories into the local cache",
    )
    sync_cmd.add_argument(
        "--year", type=int, action="append", required=True, dest="years",
        help="IRS processing year to sync (repeatable). A tax-year-N return is "
        "usually processed in year N+1, so sync the year(s) after the tax years you want.",
    )
    sync_cmd.add_argument(
        "--cache", default=DEFAULT_CACHE, help="Path to the IRS e-file cache file"
    )

    return parser


def _open_initialized(db_path: str) -> "object | None":
    """Open the database, or print guidance and return None if it has no schema."""
    engine = get_engine(db_path)
    if not is_initialized(engine):
        print(
            f"Database '{db_path}' is empty or uninitialized. Run "
            f"`pipeline init --db {db_path}`, then `seed` and `fetch`, before this command."
        )
        return None
    return engine


def run_parse(args: argparse.Namespace) -> int:
    engine = _open_initialized(args.db)
    if engine is None:
        return 1
    revenue_band = None
    if args.revenue_min is not None or args.revenue_max is not None:
        revenue_band = (
            args.revenue_min if args.revenue_min is not None else 0,
            args.revenue_max if args.revenue_max is not None else float("inf"),
        )

    cache = efile_cache.connect(args.cache)
    # First make every org's recorded filing the most recent across ProPublica
    # and the IRS e-file cache: backfill returns ProPublica missed, and upgrade
    # its aggregate filings to e-file so we parse the real per-person figure.
    inserted, upgraded = reconcile_with_efile(
        engine, lambda ein: efile_cache.newest_located_year(cache, ein), args.state
    )
    if inserted or upgraded:
        print(
            f"Reconciled with IRS e-file: {inserted} filings backfilled "
            f"(missing from ProPublica), {upgraded} upgraded from aggregate to full e-file."
        )

    filings = schedule_filings(
        list_filings(engine, state=args.state),
        list_organizations(engine, state=args.state),
        revenue_band=revenue_band,
        retry_failed=args.retry_failed,
    )
    if args.limit:
        filings = filings[: args.limit]

    # Resolve each filing to its IRS XML location first, then fetch grouped by
    # ZIP so each archive's directory is read once. Filings with no e-file XML
    # in the cache (paper-only, or a year not yet synced) are left unparsed so a
    # later `sync-irs` can pick them up.
    located = []
    unavailable = 0
    for filing in filings:
        location = efile_cache.resolve(cache, filing.ein, filing.tax_year)
        if location is None:
            unavailable += 1
        else:
            located.append((filing, location))
    print(
        f"{len(filings)} filings scheduled for {args.state.upper()}: "
        f"{len(located)} resolved to e-file XML, {unavailable} with none in the cache."
    )

    # Group by ZIP so each archive's central directory is read once, then fetch
    # groups concurrently. Workers only do network + (pure) XML parsing; every
    # database write happens here on the main thread, which keeps SQLite single-
    # writer and the results deterministic regardless of completion order.
    by_zip: dict[str, list] = defaultdict(list)
    for filing, location in located:
        by_zip[location.zip_url].append((filing, location))

    def parse_group(items):
        results = []
        with EfileFetcher() as fetcher:
            for filing, location in items:
                try:
                    results.append((filing, parse_990_xml(fetcher.fetch(location)), None))
                except (EfileFetchError, EfileParseError) as exc:
                    results.append((filing, None, exc))
        return results

    started = time.monotonic()
    parsed = failed = done = 0
    workers = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for group in pool.map(parse_group, by_zip.values()):
            for filing, extraction, exc in group:
                done += 1
                if exc is not None:
                    print(f"  ! {filing.ein} ({filing.tax_year}): {exc}")
                    record_parse_failure(engine, filing.id)
                    failed += 1
                else:
                    record_parse_success(engine, filing.id, extraction)
                    parsed += 1
                if done % 25 == 0:
                    _progress(done, len(located), started, parsed=parsed, failed=failed)

    print(
        f"Parsed {parsed} of {len(filings)} filings for {args.state.upper()} in "
        f"{_format_duration(time.monotonic() - started)} "
        f"({failed} failed, {unavailable} with no e-file XML in the cache)"
    )
    if unavailable and parsed == 0 and failed == 0:
        cached = cache.execute("SELECT COUNT(*) FROM efile_objects").fetchone()[0]
        if cached == 0:
            print("  (the IRS cache is empty — run `pipeline sync-irs --year <processing year>` first)")
        else:
            print(
                "  (these filings have no electronically-filed XML — typically older or "
                "paper-filed returns; nothing left to parse)"
            )
    return 0


def run_sync_irs(args: argparse.Namespace) -> int:
    cache = efile_cache.connect(args.cache)
    for year in args.years:
        print(f"Syncing IRS e-file data for processing year {year} ...")
        result = efile_sync.sync_year_live(cache, year)
        print(
            f"  {year}: indexed {result.indexed} returns, "
            f"located {result.located} across {result.zips} ZIPs"
        )
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    engine = _open_initialized(args.db)
    if engine is None:
        return 1
    orgs = list_organizations(engine, state=args.state)
    if args.limit:
        orgs = orgs[: args.limit]
    total = len(orgs)
    workers = max(1, args.workers)
    print(
        f"Fetching {total} organizations for {args.state.upper()} from ProPublica "
        f"({workers} workers) ..."
    )

    # Each worker thread keeps its own client (own HTTP session); a shared
    # adaptive throttle slows every worker when ProPublica rate-limits, so heavy
    # 429s degrade to a safe trickle rather than failing. Workers do the network
    # call and the pure filing selection; the main loop does every DB write.
    throttle = AdaptiveThrottle()
    local = threading.local()

    def client() -> ProPublicaClient:
        existing = getattr(local, "client", None)
        if existing is None:
            existing = local.client = ProPublicaClient()
        return existing

    def fetch_one(org):
        for _ in range(3):
            throttle.wait()
            try:
                payload = client().get_organization(org.ein)
            except ProPublicaRateLimited:
                throttle.penalize()  # back off, then retry at the slower pace
                continue
            except ProPublicaError as exc:
                return org, "error", exc
            throttle.relax()
            if payload is None:
                return org, "unknown", None
            selected = select_filing(
                payload.get("filings_with_data") or [],
                payload.get("filings_without_data") or [],
            )
            return (org, "recorded", selected) if selected else (org, "empty", None)
        return org, "rate_limited", None

    started = time.monotonic()
    recorded = unknown = empty = errors = rate_limited = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (org, kind, value) in enumerate(pool.map(fetch_one, orgs), start=1):
            if kind == "recorded":
                record_selected_filing(engine, org.ein, value)
                recorded += 1
            elif kind == "unknown":
                unknown += 1
            elif kind == "empty":
                empty += 1
            elif kind == "rate_limited":
                print(f"  ! {org.ein}: rate-limited, skipped")
                rate_limited += 1
            else:
                print(f"  ! {org.ein}: {value}")
                errors += 1
            if i % 200 == 0:
                _progress(i, total, started, filings=recorded, no_filing=empty)

    print(
        f"Fetched {total} organizations for {args.state.upper()} in "
        f"{_format_duration(time.monotonic() - started)}: "
        f"{recorded} filings recorded, {unknown} unknown EINs, "
        f"{empty} without filings, {errors} errors, {rate_limited} rate-limited"
    )
    return 0


def run_seed(args: argparse.Namespace) -> int:
    engine = _open_initialized(args.db)
    if engine is None:
        return 1
    if args.file:
        with open(args.file, newline="", encoding="utf-8") as f:
            result = parse_bmf(f)
    else:
        result = parse_bmf(download_bmf(args.state))

    stored = upsert_organizations(engine, result.organizations)
    print(
        f"Seeded {stored} 501(c)(3) organizations for {args.state.upper()} "
        f"({result.skipped_rows} malformed rows skipped)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init":
        init_db(args.db)
        print(f"Initialized database at {args.db}")
    elif args.command == "seed":
        return run_seed(args)
    elif args.command == "fetch":
        return run_fetch(args)
    elif args.command == "parse":
        return run_parse(args)
    elif args.command == "sync-irs":
        return run_sync_irs(args)

    return 0


def entrypoint() -> None:
    raise SystemExit(main())
