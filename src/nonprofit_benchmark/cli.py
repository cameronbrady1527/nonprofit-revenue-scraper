"""The single `pipeline` CLI entry point."""

import argparse

from nonprofit_benchmark.db import init_db

DEFAULT_DB = "benchmark.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Nonprofit executive compensation data pipeline",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init_cmd = subcommands.add_parser("init", help="Create the local database")
    init_cmd.add_argument("--db", default=DEFAULT_DB, help="Path to the SQLite database file")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init":
        init_db(args.db)
        print(f"Initialized database at {args.db}")

    return 0


def entrypoint() -> None:
    raise SystemExit(main())
