"""The `mlb` command: bootstrap and maintain the database.

    mlb migrate
    mlb ingest register --mode bootstrap
    mlb ingest register --mode update
    mlb inventory
    mlb doctor

Every entry in CONNECTORS must expose bootstrap() and update(), each returning
a dict of {table: row_count}, plus health_check() -> list[Check] for `mlb doctor`.
See docs/ARCHITECTURE.md "Connector contract" and CLAUDE.md "Operational health checks".
"""

import argparse
import sys

from mlb_baseball import doctor, inventory, migrate
from mlb_baseball.registry import CONNECTORS


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mlb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("source", choices=sorted(CONNECTORS))
    ingest_parser.add_argument("--mode", choices=["bootstrap", "update"], default="bootstrap")

    subparsers.add_parser("inventory")
    subparsers.add_parser("doctor")

    args = parser.parse_args(argv)

    if args.command == "migrate":
        migrate.main()
    elif args.command == "ingest":
        connector = CONNECTORS[args.source]
        fn = connector.bootstrap if args.mode == "bootstrap" else connector.update
        for table, count in fn().items():
            print(f"{table}: {count} rows")
    elif args.command == "inventory":
        for row in inventory.tables():
            print(f"{row['schema']}.{row['table']}: {row['rows']} rows")
        print("\nLast run per source:")
        for row in inventory.last_runs():
            print(
                f"  {row['source']}: {row['status']} ({row['mode']}, "
                f"{row['rows']} rows, started {row['started_at']})"
            )
    elif args.command == "doctor":
        checks = doctor.run()
        failed = [c for c in checks if not c.ok]
        for check in checks:
            status = "OK" if check.ok else "FAIL"
            print(f"[{status}] {check.name}: {check.detail}")
        print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
