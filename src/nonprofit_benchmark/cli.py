"""The single `pipeline` CLI entry point."""

import argparse

from nonprofit_benchmark.bmf import download_bmf, parse_bmf
from nonprofit_benchmark.db import get_engine, init_db, upsert_organizations

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

    return parser


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

    return 0


def entrypoint() -> None:
    raise SystemExit(main())
