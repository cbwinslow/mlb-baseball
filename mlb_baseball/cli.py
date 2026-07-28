"""The `mlb` command: bootstrap and maintain the database.

    mlb migrate
    mlb ingest register --mode bootstrap
    mlb ingest register --mode update
    mlb bootstrap
    mlb update
    mlb conform
    mlb inventory
    mlb doctor

Every entry in CONNECTORS must expose bootstrap() and update(), each returning
a dict of {table: row_count}, plus health_check() -> list[Check] for `mlb doctor`.
See docs/ARCHITECTURE.md "Connector contract" and CLAUDE.md "Operational health checks".

`mlb bootstrap`/`mlb update` run every registered connector's bootstrap()/
update() in one command — the single routine that stands up (or refreshes)
the whole database, rather than remembering to run `mlb ingest <source>` once
per source. A failure in one connector is logged and skipped, not fatal to
the rest — matches every individual connector's own per-season/per-game
resilience pattern; a bad source shouldn't block every other source from
bootstrapping.
"""

import argparse
import sys

from mlb_baseball import conform, doctor, inventory, migrate
from mlb_baseball.registry import CONNECTORS


def _run_all(mode: str) -> None:
    any_failed = False
    for name, connector in CONNECTORS.items():
        fn = connector.bootstrap if mode == "bootstrap" else connector.update
        print(f"=== {name} ({mode}) ===")
        try:
            for table, count in fn().items():
                print(f"{table}: {count} rows")
        except Exception as exc:
            any_failed = True
            print(f"{name}: FAILED ({exc}); continuing with remaining sources")
    if any_failed:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mlb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("source", choices=sorted(CONNECTORS))
    ingest_parser.add_argument("--mode", choices=["bootstrap", "update"], default="bootstrap")

    subparsers.add_parser("bootstrap")
    subparsers.add_parser("update")
    subparsers.add_parser("conform")
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
    elif args.command == "bootstrap":
        _run_all("bootstrap")
    elif args.command == "update":
        _run_all("update")
    elif args.command == "conform":
        for table, count in conform.run().items():
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
