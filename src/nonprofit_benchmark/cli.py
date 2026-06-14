"""The single `pipeline` CLI entry point."""

import argparse

from nonprofit_benchmark.bmf import download_bmf, parse_bmf
from nonprofit_benchmark.db import (
    get_engine,
    init_db,
    list_filings,
    list_organizations,
    record_parse_failure,
    record_parse_success,
    record_selected_filing,
    upsert_organizations,
)
from nonprofit_benchmark.filing_selector import select_filing
from nonprofit_benchmark.gemini_parser import GeminiParseError, GeminiParser
from nonprofit_benchmark.parse_scheduler import schedule_filings
from nonprofit_benchmark.pdfs import PdfDownloadError, download_pdf
from nonprofit_benchmark.propublica import ProPublicaClient, ProPublicaError

DEFAULT_DB = "benchmark.db"


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

    parse_cmd = subcommands.add_parser(
        "parse", help="Gemini-parse unparsed PDF-only filings for a state"
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

    return parser


def run_parse(args: argparse.Namespace) -> int:
    engine = get_engine(args.db)
    revenue_band = None
    if args.revenue_min is not None or args.revenue_max is not None:
        revenue_band = (
            args.revenue_min if args.revenue_min is not None else 0,
            args.revenue_max if args.revenue_max is not None else float("inf"),
        )
    filings = schedule_filings(
        list_filings(engine, state=args.state),
        list_organizations(engine, state=args.state),
        revenue_band=revenue_band,
        retry_failed=args.retry_failed,
    )
    if args.limit:
        filings = filings[: args.limit]
    parser = GeminiParser()

    parsed = failed = 0
    for i, filing in enumerate(filings, start=1):
        try:
            extraction = parser.parse(download_pdf(filing.pdf_url))
        except (PdfDownloadError, GeminiParseError) as exc:
            print(f"  ! {filing.ein} ({filing.tax_year}): {exc}")
            record_parse_failure(engine, filing.id)
            failed += 1
            continue
        record_parse_success(engine, filing.id, extraction)
        parsed += 1
        if i % 25 == 0:
            print(f"  ...{i}/{len(filings)} filings")

    print(
        f"Parsed {parsed} of {len(filings)} filings for {args.state.upper()} "
        f"({failed} failed)"
    )
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    engine = get_engine(args.db)
    orgs = list_organizations(engine, state=args.state)
    if args.limit:
        orgs = orgs[: args.limit]
    client = ProPublicaClient()

    recorded = unknown = empty = errors = 0
    for i, org in enumerate(orgs, start=1):
        try:
            payload = client.get_organization(org.ein)
        except ProPublicaError as exc:
            print(f"  ! {org.ein}: {exc}")
            errors += 1
            continue
        if payload is None:
            unknown += 1
            continue
        selected = select_filing(
            payload.get("filings_with_data") or [], payload.get("filings_without_data") or []
        )
        if selected is None:
            empty += 1
            continue
        record_selected_filing(engine, org.ein, selected)
        recorded += 1
        if i % 100 == 0:
            print(f"  ...{i}/{len(orgs)} organizations")

    print(
        f"Fetched {len(orgs)} organizations for {args.state.upper()}: "
        f"{recorded} filings recorded, {unknown} unknown EINs, "
        f"{empty} without filings, {errors} errors"
    )
    return 0


def run_seed(args: argparse.Namespace) -> int:
    if args.file:
        with open(args.file, newline="", encoding="utf-8") as f:
            result = parse_bmf(f)
    else:
        result = parse_bmf(download_bmf(args.state))

    stored = upsert_organizations(get_engine(args.db), result.organizations)
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

    return 0


def entrypoint() -> None:
    raise SystemExit(main())
