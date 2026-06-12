"""The single `pipeline` CLI entry point."""

import argparse

from nonprofit_benchmark.bmf import download_bmf, parse_bmf
from nonprofit_benchmark.db import (
    get_engine,
    init_db,
    list_organizations,
    record_selected_filing,
    upsert_organizations,
)
from nonprofit_benchmark.filing_selector import select_filing
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

    return parser


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

    return 0


def entrypoint() -> None:
    raise SystemExit(main())
