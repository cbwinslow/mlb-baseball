"""The `mlb` command: bootstrap and maintain the database.

    mlb migrate
    mlb ingest register --mode bootstrap
    mlb ingest register --mode update
    mlb ingest polymarket --mode backfill
    mlb ingest kalshi --mode backfill
    mlb bootstrap
    mlb update
    mlb conform
    mlb features
    mlb predict
    mlb train
    mlb inventory
    mlb status
    mlb metrics
    mlb doctor

Every entry in CONNECTORS must expose bootstrap() and update(), each returning
a dict of {table: row_count}, plus health_check() -> list[Check] for `mlb doctor`.
See docs/ARCHITECTURE.md "Connector contract" and CLAUDE.md "Operational health checks".

`--mode backfill` is a third, optional mode not every connector implements
(only polymarket.py/kalshi.py, so far — see ADR-049): a one-off historical
price/candlestick backfill, deliberately kept out of bootstrap()/update()
since it's much more expensive and isn't something a routine bootstrap or
scheduled update should ever trigger.

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
from collections.abc import Callable
from pathlib import Path
from typing import cast

from mlb_baseball import (
    backup,
    config,
    conform,
    doctor,
    field_census,
    ingest,
    inventory,
    migrate,
    model,
    player,
    progress_table,
    report,
    schema_inventory,
)
from mlb_baseball import (
    metrics as operational_metrics,
)
from mlb_baseball.model import experiment
from mlb_baseball.registry import CONNECTORS
from mlb_baseball.source_profiles import (
    PROFILES,
    SourceProfileError,
    active_profile,
    require_sources,
)

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


def _run_group(names: list[str], mode: str, profile: str) -> bool:
    """Runs one group's connectors sequentially — either because they share
    an external server (see _SAME_SERVER_GROUPS) or because a singleton
    group only has the one anyway. Returns True if anything in the group
    failed. Wrapped in its own try/except as defense in depth: every
    connector's own bootstrap()/update() failure is already caught below,
    but a group must never take down the other, concurrently-running
    groups over an unexpected error escaping this function."""
    any_failed = False
    for name in names:
        try:
            require_sources(profile, [name], purpose=f"ingest {name}")
        except SourceProfileError as exc:
            any_failed = True
            print(f"[{name}] SKIPPED ({exc})")
            continue
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


def _run_all(mode: str, profile: str) -> None:
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
            results = list(pool.map(lambda names: _run_group(names, mode, profile), groups))
        except Exception as exc:
            print(f"mlb {mode}: an entire connector group failed unexpectedly ({exc})")
            sys.exit(1)
    if any(results):
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mlb")
    parser.add_argument(
        "--config",
        help="optional TOML settings file (defaults to ./mlb.toml when present)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("source", choices=sorted(CONNECTORS))
    ingest_parser.add_argument(
        "--mode", choices=["bootstrap", "update", "backfill"], default="bootstrap"
    )
    ingest_parser.add_argument(
        "--stage",
        choices=["analytics", "analytics-replay"],
        help="run or replay one resumable MLB API historical stage instead of the full connector",
    )
    ingest_parser.add_argument(
        "--start-year", type=int, help="first season for a staged MLB API run"
    )
    ingest_parser.add_argument("--end-year", type=int, help="last season for a staged MLB API run")
    ingest_parser.add_argument(
        "--workers", type=int, help="bounded parallel API workers for a staged MLB API run"
    )

    for profile_parser in (
        ingest_parser,
        subparsers.add_parser("bootstrap"),
        subparsers.add_parser("update"),
    ):
        profile_parser.add_argument("--profile", choices=sorted(PROFILES))

    subparsers.add_parser("conform")
    subparsers.add_parser("report", help="rebuild documented gold research tables")
    subparsers.add_parser("features")
    subparsers.add_parser("predict")
    subparsers.add_parser("train")
    experiment_parser = subparsers.add_parser(
        "experiment", help="create and compare reproducible game-win experiments"
    )
    experiment_commands = experiment_parser.add_subparsers(dest="experiment_command", required=True)
    experiment_snapshot = experiment_commands.add_parser(
        "snapshot", help="copy approved PIT feature rows immutably"
    )
    experiment_snapshot.add_argument(
        "--target",
        choices=list(experiment.TARGET_REGISTRY),
        default="home_win",
    )
    experiment_run = experiment_commands.add_parser(
        "run", help="run one declared model on calendar folds"
    )
    experiment_run.add_argument("--snapshot", required=True)
    experiment_run.add_argument(
        "--target",
        choices=list(experiment.TARGET_REGISTRY),
        default="home_win",
    )
    experiment_run.add_argument("--model", choices=experiment.ALL_MODEL_FAMILIES, required=True)
    experiment_run.add_argument(
        "--fold-years", nargs="+", type=int, default=list(experiment.DEFAULT_FOLD_YEARS)
    )
    experiment_run.add_argument("--seed", type=int, default=0)
    experiment_compare = experiment_commands.add_parser("compare", help="show saved fold metrics")
    experiment_compare.add_argument("--snapshot", required=True)
    experiment_select = experiment_commands.add_parser(
        "select-features", help="compute feature-selection stability report"
    )
    experiment_select.add_argument("--snapshot", required=True)
    experiment_select.add_argument("--n-repeats", type=int, default=30)
    experiment_select.add_argument("--seed", type=int, default=0)
    experiment_select.add_argument(
        "--fold-years", nargs="+", type=int, default=list(experiment.DEFAULT_FOLD_YEARS)
    )
    experiment_stepwise = experiment_commands.add_parser(
        "select-features-stepwise",
        help="run forward-stepwise feature selection with nested chronological validation",
    )
    experiment_stepwise.add_argument("--snapshot", required=True)
    experiment_stepwise.add_argument("--seed", type=int, default=0)
    experiment_stepwise.add_argument(
        "--fold-years", nargs="+", type=int, default=list(experiment.DEFAULT_FOLD_YEARS)
    )
    experiment_stepwise.add_argument(
        "--min-survival-fraction", type=float, default=0.70
    )
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--season", type=int, required=True)
    evaluate_parser.add_argument("--models", nargs="+", required=True)
    evaluate_parser.add_argument(
        "--cutoff", choices=["open", "24h", "6h", "close"], default="close"
    )
    evaluate_parser.add_argument("--bootstrap-samples", type=int, default=1000)
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument(
        "--partitions",
        action="store_true",
        help="include individual core.play/core.pitch partitions",
    )
    schema_parser = subparsers.add_parser(
        "schema", help="inspect read-only schema objects and constraints"
    )
    schema_parser.add_argument(
        "--partitions", action="store_true", help="include physical child partitions"
    )
    census_parser = subparsers.add_parser(
        "field-census", help="read-only raw-to-core-to-gold field lineage inventory"
    )
    census_parser.add_argument(
        "--exact",
        action="store_true",
        help="use exact raw relation counts instead of catalog estimates",
    )
    census_parser.add_argument("--output-json", type=Path)
    census_parser.add_argument("--output-markdown", type=Path)
    player_id_parser = subparsers.add_parser(
        "player-id", help="resolve a player's IDs across retro/mlbam/bbref/fangraphs/chadwick"
    )
    player_id_parser.add_argument(
        "id_type", choices=sorted(player.ID_COLUMNS), help="which ID system you already have"
    )
    player_id_parser.add_argument("id_value", help="the ID value to look up")
    backup_parser = subparsers.add_parser(
        "backup", help="dump the configured database via pg_dump (read-only)"
    )
    backup_parser.add_argument(
        "--output-dir", type=Path, default=Path("backups"), help="default: ./backups"
    )
    backup_parser.add_argument(
        "--schema-only", action="store_true", help="omit row data, structure only"
    )
    backup_parser.add_argument(
        "--schema",
        dest="schemas",
        action="append",
        help="limit to this schema (repeatable); default: the whole database",
    )
    restore_parser = subparsers.add_parser(
        "restore", help="restore a pg_dump file into the configured database (DESTRUCTIVE)"
    )
    restore_parser.add_argument("dump_path", type=Path)
    restore_parser.add_argument(
        "--yes",
        action="store_true",
        help="required: confirms you want to overwrite the target database",
    )
    inventory_parser.add_argument(
        "--exact", action="store_true", help="count rows exactly instead of using catalog estimates"
    )
    metrics_parser = subparsers.add_parser("metrics")
    metrics_parser.add_argument("--source", default="mlb_api")
    metrics_parser.add_argument("--window-minutes", type=int, default=5)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument(
        "--all", action="store_true", help="show every table, not just populated ones"
    )
    status_parser.add_argument(
        "--watch", type=int, metavar="SECONDS", help="refresh live every SECONDS until Ctrl-C"
    )
    status_strategy = status_parser.add_mutually_exclusive_group()
    status_strategy.add_argument(
        "--run-status",
        action="store_true",
        help="use each table's last ingestion-run status instead of just row count",
    )
    status_strategy.add_argument(
        "--season-coverage",
        action="store_true",
        help="use exact distinct-season coverage for registered historical tables",
    )
    subparsers.add_parser("doctor")
    audit_parser = subparsers.add_parser(
        "audit", help="run read-only game-identity and data-quality checks"
    )
    audit_parser.add_argument(
        "--scope",
        choices=["game", "database", "statcast"],
        default="game",
        help=(
            "game is bounded identity validation; database adds planner statistics; "
            "statcast scans pitch coverage"
        ),
    )
    preflight_parser = subparsers.add_parser(
        "preflight", help="validate a planned bootstrap without downloading or writing to Postgres"
    )
    preflight_parser.add_argument(
        "--sources", nargs="+", choices=sorted(CONNECTORS), help="sources to plan individually"
    )
    preflight_parser.add_argument(
        "--with-conform", action="store_true", help="include the post-ingestion conform step"
    )
    subparsers.add_parser("repair-runs")
    backfill_identity = subparsers.add_parser("backfill-game-identities")
    backfill_identity.add_argument("--batch-size", type=int, default=1000)

    args = parser.parse_args(argv)

    try:
        settings = config.load_settings(args.config)
        config.apply_settings(settings)
    except config.ConfigError as exc:
        parser.error(str(exc))

    profile = getattr(args, "profile", None) or active_profile()

    if args.command == "migrate":
        migrate.main()
    elif args.command == "ingest":
        try:
            require_sources(profile, [args.source], purpose=f"ingest {args.source}")
        except SourceProfileError as exc:
            parser.error(str(exc))
        connector = CONNECTORS[args.source]
        fn: Callable[[], dict[str, int]]
        if args.stage:
            if args.source != "mlb_api":
                parser.error("staged ingestion is currently available only for mlb_api")
            if args.mode != "bootstrap":
                parser.error("staged ingestion uses bootstrap mode; omit --mode")
            if args.stage == "analytics":

                def fn():
                    return connector.backfill_analytics(
                        start_year=args.start_year or settings.analytics_start_year,
                        end_year=args.end_year or settings.analytics_end_year,
                        workers=args.workers or settings.analytics_workers,
                    )

            elif args.workers:
                parser.error("--workers is only valid with --stage analytics")
            else:

                def fn():
                    return connector.replay_analytics(
                        start_year=args.start_year or settings.analytics_start_year,
                        end_year=args.end_year or settings.analytics_end_year,
                    )
        elif args.start_year or args.end_year or args.workers:
            parser.error("--start-year, --end-year, and --workers require --stage analytics")
        elif args.mode == "bootstrap":
            fn = connector.bootstrap
        elif args.mode == "update":
            fn = connector.update
        else:
            # 'backfill' is an owner-triggered one-off historical load, not
            # part of the bootstrap()/update() contract every connector
            # exposes — only polymarket.py/kalshi.py implement it so far
            # (see ADR-049).
            backfill = getattr(connector, "backfill_history", None)
            if backfill is None:
                print(f"{args.source} has no backfill_history() to run")
                sys.exit(1)
            fn = cast(Callable[[], dict[str, int]], backfill)
        for table, count in fn().items():
            print(f"{table}: {count} rows")
    elif args.command == "bootstrap":
        _run_all("bootstrap", profile)
    elif args.command == "update":
        _run_all("update", profile)
    elif args.command == "conform":
        for table, count in conform.run().items():
            print(f"{table}: {count} rows")
    elif args.command == "report":
        for table, count in report.run().items():
            print(f"{table}: {count} rows")
    elif args.command == "schema":
        schema_inventory.print_report(partitions=args.partitions)
    elif args.command == "field-census":
        try:
            field_census.print_report(
                exact=args.exact,
                output_json=args.output_json,
                output_markdown=args.output_markdown,
            )
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "player-id":
        player.print_crosswalk(args.id_type, args.id_value)
    elif args.command == "backup":
        try:
            output_path = backup.backup(
                config.database_url(),
                args.output_dir,
                schema_only=args.schema_only,
                schemas=args.schemas,
            )
        except RuntimeError as exc:
            parser.error(str(exc))
        else:
            print(f"Wrote {output_path}")
    elif args.command == "restore":
        target = backup.dbname(config.database_url())
        if not args.yes:
            parser.error(
                f"refusing to restore into database {target!r} without --yes "
                "-- this OVERWRITES existing objects in that database"
            )
        print(f"Restoring {args.dump_path} into database {target!r} ...")
        try:
            backup.restore(config.database_url(), args.dump_path, confirm=True)
        except RuntimeError as exc:
            parser.error(str(exc))
        else:
            print("Restore complete.")
    elif args.command == "features":
        for table, count in model.run_features().items():
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
    elif args.command == "experiment":
        from mlb_baseball.db import get_connection

        with get_connection() as conn:
            if args.experiment_command == "snapshot":
                snapshot_id = experiment.create_snapshot(conn, target=args.target)
                conn.commit()
                print(f"snapshot: {snapshot_id}")
            elif args.experiment_command == "run":
                result = experiment.run(
                    conn,
                    experiment.ExperimentConfig(
                        snapshot_id=args.snapshot,
                        model_family=args.model,
                        target=args.target,
                        fold_years=tuple(args.fold_years),
                        seed=args.seed,
                    ),
                )
                conn.commit()
                mode = "reused" if result["reused"] else "ran"
                print(f"experiment: {result['experiment_id']} ({mode})")
                for fold, metrics in result["folds"].items():
                    if "log_loss" in metrics:
                        log_loss_val = metrics["log_loss"]
                        brier_val = metrics["brier"]
                        print(f"  {fold}: log_loss={log_loss_val:.4f} brier={brier_val:.4f}")
                    elif "mae" in metrics:
                        print(
                            f"  {fold}: mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f}"
                        )
            elif args.experiment_command == "select-features":
                from mlb_baseball.model import feature_select

                result = feature_select.select_features(
                    conn,
                    args.snapshot,
                    n_repeats=args.n_repeats,
                    seed=args.seed,
                    fold_years=tuple(args.fold_years),
                )
                conn.commit()
                mode = "reused" if result.get("reused") else "ran"
                print(f"feature_selection: {result['selection_id']} ({mode})")
                n = result["total_folds_evaluated"]
                for feat, summary in result["features"].items():
                    s1 = summary["stage1_survived_folds"]
                    s2 = summary["stage2_survived_folds"]
                    both = summary["both_stages_survived_folds"]
                    print(f"  {feat}: stage1: {s1}/{n}  stage2: {s2}/{n}  both: {both}/{n}")
            elif args.experiment_command == "select-features-stepwise":
                from mlb_baseball.model import feature_select_stepwise

                result = feature_select_stepwise.select_features_stepwise(
                    conn,
                    args.snapshot,
                    seed=args.seed,
                    fold_years=tuple(args.fold_years),
                    min_survival_fraction=args.min_survival_fraction,
                )
                conn.commit()
                mode = "reused" if result.get("reused") else "ran"
                print(f"feature_selection_stepwise: {result['selection_id']} ({mode})")
                n = result["total_folds_evaluated"]
                candidates = result["candidate_features"]
                print(f"candidates ({len(candidates)}): {', '.join(candidates)}")
                for feat, summary in result["features"].items():
                    sel = summary["selected_folds"]
                    pct = summary["selection_fraction"]
                    print(f"  {feat}: selected {sel}/{n} folds ({pct:.0%})")
            else:
                for row in experiment.compare(conn, args.snapshot):
                    if "log_loss" in row:
                        print(
                            f"{row['model']} {row['fold']}: "
                            f"log_loss={row['log_loss']:.4f} brier={row['brier']:.4f}"
                        )
                    elif "mae" in row:
                        print(
                            f"{row['model']} {row['fold']}: "
                            f"mae={row['mae']:.4f} rmse={row['rmse']:.4f}"
                        )
    elif args.command == "evaluate":
        evaluation_report = model.evaluate(
            args.models, args.season, args.cutoff, args.bootstrap_samples
        )
        print(
            f"season {evaluation_report['season']} / {evaluation_report['cutoff']} cutoff / "
            f"{evaluation_report['common_games']} common games"
        )
        for version in args.models:
            metrics = evaluation_report["models"][version]
            log_low, log_high = metrics["log_loss_95ci"]
            brier_low, brier_high = metrics["brier_95ci"]
            print(
                f"  {version}: coverage={evaluation_report['coverage'][version]} "
                f"log_loss={metrics['log_loss']:.4f} [{log_low:.4f}, {log_high:.4f}] "
                f"brier={metrics['brier']:.4f} [{brier_low:.4f}, {brier_high:.4f}] "
                f"accuracy={metrics['accuracy']:.4f}"
            )
    elif args.command == "inventory":
        for row in inventory.tables(partitions=args.partitions, exact=args.exact):
            approximate = "" if row["exact"] else "≈"
            print(f"{row['schema']}.{row['table']}: {approximate}{row['rows']} rows")
        print("\nLast run per source:")
        for row in inventory.last_runs():
            print(
                f"  {row['source']}: {row['status']} ({row['mode']}, "
                f"{row['rows']} rows, started {row['started_at']})"
            )
    elif args.command == "metrics":
        try:
            operational_metrics.print_report(args.source, args.window_minutes)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "status":
        if args.season_coverage and args.watch is not None:
            parser.error("status --season-coverage cannot be combined with --watch")
        strategy = (
            progress_table.RunStatusStrategy()
            if args.run_status
            else progress_table.SeasonCoverageStrategy()
            if args.season_coverage
            else None
        )
        progress_table.print_status_table(
            strategy=strategy, populated_only=not args.all, watch=args.watch
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
    elif args.command == "audit":
        from mlb_baseball import audit

        if not audit.print_report(args.scope):
            sys.exit(1)
    elif args.command == "preflight":
        from mlb_baseball import preflight

        preflight_checks, commands = preflight.run(settings, args.sources, args.with_conform)
        for preflight_check in preflight_checks:
            print(
                f"[{'OK' if preflight_check.ok else 'FAIL'}] "
                f"{preflight_check.name}: {preflight_check.detail}"
            )
        print("\nPlanned commands (not run):")
        for command in commands:
            print(f"  {command}")
        if any(not preflight_check.ok for preflight_check in preflight_checks):
            sys.exit(1)
    elif args.command == "repair-runs":
        from mlb_baseball.db import get_connection

        with get_connection() as conn:
            reaped = ingest.reap_stale_runs(conn)
        if not reaped:
            print("no stale ingestion runs found")
        else:
            print(f"repaired {len(reaped)} stale ingestion run(s)")
    elif args.command == "backfill-game-identities":
        from mlb_baseball.db import get_connection
        from mlb_baseball.model.identity import backfill_game_instance_keys

        with get_connection() as conn:
            counts = backfill_game_instance_keys(conn, args.batch_size)
        print(" ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
