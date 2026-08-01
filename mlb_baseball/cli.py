"""The `mlb` command: bootstrap and maintain the database.

    mlb migrate
    mlb ingest register --mode bootstrap
    mlb ingest register --mode update
    mlb bootstrap
    mlb update
    mlb conform
    mlb predict
    mlb train
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

Connectors run in concurrent groups, not one at a time (ADR-031) — a full
historical bootstrap is on the order of 600,000+ sequential API calls for
mlb_api alone (measured directly, not estimated), which made a fully
serial `mlb bootstrap` a multi-day operation. Groups are split by which
external server each connector hits (see _SAME_SERVER_GROUPS) so this
doesn't reproduce ADR-005's undiagnosed thread-deadlock (many concurrent
connections to the *same* server, retrosheet.org).
"""

import argparse
import concurrent.futures
import sys

from mlb_baseball import conform, doctor, inventory, migrate, model
from mlb_baseball.registry import CONNECTORS

# Connector names confirmed (by reading each connector's own network calls,
# not guessed) to hit the same external server. Running several connectors
# from the same group *concurrently* would reproduce the exact failure
# documented in docs/DECISIONS.md ADR-005: many concurrent connections to
# one server (retrosheet.org, specifically) caused an undiagnosed thread
# deadlock during a real bootstrap run. So a group's own connectors stay
# sequential. Everything else is safe to overlap: different connectors
# mostly hit different external services (statsapi.mlb.com,
# baseballsavant.mlb.com, baseball-reference.com, gamma-api.polymarket.com,
# api.elections.kalshi.com, github.com/box.com), which doesn't create the
# same single-server-hammering scenario ADR-005 hit. See ADR-031.
_SAME_SERVER_GROUPS: list[frozenset[str]] = [
    frozenset(
        {
            "retrosheet",
            "retrosheet_event",
            "retrosheet_box",
            "retrosheet_gamelog",
            "retrosheet_reference",
            "retrosheet_roster",
            "retrosheet_schedule",
            "retrosheet_transaction",
        }
    ),  # all hit retrosheet.org
    frozenset({"statcast", "statcast_leaderboard"}),  # both hit baseballsavant.mlb.com
]


def _concurrency_groups(names: list[str]) -> list[list[str]]:
    """Splits `names` into groups that are safe to run concurrently with
    each other. A name matching one of _SAME_SERVER_GROUPS is bundled with
    the others from that same group (kept sequential internally, in
    `names`' own relative order); anything else gets its own singleton
    group — the safe default for a connector this list doesn't know about
    (a newly added connector nobody's classified yet, or a test double)."""
    remaining = list(names)
    groups: list[list[str]] = []
    for same_server in _SAME_SERVER_GROUPS:
        matched = [n for n in remaining if n in same_server]
        if matched:
            groups.append(matched)
            remaining = [n for n in remaining if n not in same_server]
    groups.extend([n] for n in remaining)
    return groups


def _run_group(names: list[str], mode: str) -> bool:
    """Runs one group's connectors sequentially — either because they share
    an external server (see _SAME_SERVER_GROUPS) or because a singleton
    group only has the one anyway. Returns True if anything in the group
    failed. Wrapped in its own try/except as defense in depth: every
    connector's own bootstrap()/update() failure is already caught below,
    but a group must never take down the other, concurrently-running
    groups over an unexpected error escaping this function."""
    any_failed = False
    for name in names:
        connector = CONNECTORS[name]
        fn = connector.bootstrap if mode == "bootstrap" else connector.update
        print(f"=== {name} ({mode}) ===")
        try:
            for table, count in fn().items():
                print(f"[{name}] {table}: {count} rows")
        except Exception as exc:
            any_failed = True
            print(f"[{name}] FAILED ({exc}); continuing with remaining sources")
    return any_failed


def _run_all(mode: str) -> None:
    # Groups run concurrently (different external servers per group,
    # confirmed no shared-server overlap between groups — see
    # _SAME_SERVER_GROUPS above); connectors within one group stay
    # sequential. This is the outer-orchestration-level concurrency ADR-031
    # chose instead of retrying concurrency *inside* a single connector's
    # request loop (ADR-005's undiagnosed deadlock, never root-caused —
    # not worth reintroducing that risk blind, a second time).
    groups = _concurrency_groups(list(CONNECTORS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(groups)) as pool:
        try:
            results = list(pool.map(lambda names: _run_group(names, mode), groups))
        except Exception as exc:
            print(f"mlb {mode}: an entire connector group failed unexpectedly ({exc})")
            sys.exit(1)
    if any(results):
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
    subparsers.add_parser("predict")
    subparsers.add_parser("train")
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
    elif args.command == "predict":
        for table, count in model.run().items():
            print(f"{table}: {count} rows")
    elif args.command == "train":
        metrics = model.train()
        print(f"train rows: {metrics['train_rows']}, validation rows: {metrics['validation_rows']}")
        for name in ("gbm", "log5", "elo"):
            m = metrics[name]
            print(f"  {name}: log_loss={m['log_loss']:.4f} brier={m['brier']:.4f}")
        if metrics["saved"]:
            print("saved: new model beat both baselines")
        else:
            print("not saved: did not beat both baselines")
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
    main()
