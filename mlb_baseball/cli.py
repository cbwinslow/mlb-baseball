"""The `mlb` command: bootstrap and maintain the database.

    mlb migrate
    mlb ingest register --mode bootstrap
    mlb ingest register --mode update

Every entry in CONNECTORS must expose bootstrap() and update(), each returning
a dict of {table: row_count}. See docs/ARCHITECTURE.md "Connector contract".
"""

import argparse
import sys

from mlb_baseball import migrate
from mlb_baseball.connectors import chadwick_register, lahman, retrosheet

CONNECTORS = {
    "register": chadwick_register,
    "lahman": lahman,
    "retrosheet": retrosheet,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mlb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("source", choices=sorted(CONNECTORS))
    ingest_parser.add_argument("--mode", choices=["bootstrap", "update"], default="bootstrap")

    args = parser.parse_args(argv)

    if args.command == "migrate":
        migrate.main()
    elif args.command == "ingest":
        connector = CONNECTORS[args.source]
        fn = connector.bootstrap if args.mode == "bootstrap" else connector.update
        for table, count in fn().items():
            print(f"{table}: {count} rows")


if __name__ == "__main__":
    sys.exit(main())
