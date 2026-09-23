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
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import psycopg

from mlb_baseball import (
    backup,
    config,
    conform,
    doctor,
    feat,
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
    catalog as metric_catalog,
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

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Wires stdlib logging for the whole `mlb` process, so every module's
    `logging.getLogger(__name__)` calls (connector failures included) reach
    stderr with a timestamp/level/module instead of relying on logging's
    unconfigured "handler of last resort" (bare message, no context).
    `MLB_LOG_LEVEL` (default INFO) lets an operator raise verbosity for a
    single run without editing code; an unrecognized value falls back to
    INFO rather than raising."""
    level_name = os.environ.get("MLB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
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
            logger.error("[%s] SKIPPED (%s)", name, exc)
            continue
        connector = CONNECTORS[name]
        fn = connector.bootstrap if mode == "bootstrap" else connector.update
        print(f"=== {name} ({mode}) ===")
        try:
            for table, count in fn().items():
                print(f"[{name}] {table}: {count} rows")
        except Exception as exc:
            any_failed = True
            logger.error("[%s] FAILED (%s); continuing with remaining sources", name, exc)
    return any_failed


def _run_all(mode: str, profile: str, skip: list[str] | None = None) -> None:
    # Groups run concurrently (different external servers per group,
    # confirmed no shared-server overlap between groups — see
    # _SAME_SERVER_GROUPS above); connectors within one group stay
    # sequential. This is the outer-orchestration-level concurrency ADR-031
    # chose instead of retrying concurrency *inside* a single connector's
    # request loop (ADR-005's undiagnosed deadlock, never root-caused —
    # not worth reintroducing that risk blind, a second time).
    skipped = set(skip or ())
    unknown = skipped - set(CONNECTORS)
    if unknown:
        print(f"mlb {mode}: --skip names no known connector: {', '.join(sorted(unknown))}")
        sys.exit(2)
    names = [n for n in CONNECTORS if n not in skipped]
    if skipped:
        print(f"mlb {mode}: skipping {', '.join(sorted(skipped))}")
    if not names:
        print(f"mlb {mode}: nothing to do — every connector was --skip'd")
        return
    groups = _concurrency_groups(names)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(groups)) as pool:
        try:
            results = list(pool.map(lambda names: _run_group(names, mode, profile), groups))
        except Exception as exc:
            logger.error("mlb %s: an entire connector group failed unexpectedly (%s)", mode, exc)
            sys.exit(1)
    if any(results):
        sys.exit(1)


def _format_metrics_line(metrics: dict[str, Any]) -> str:
    if "log_loss" in metrics:
        return f"log_loss={metrics['log_loss']:.4f} brier={metrics['brier']:.4f}"
    if "mae" in metrics:
        return f"mae={metrics['mae']:.4f} rmse={metrics['rmse']:.4f}"
    return ""


def _run_experiment_command(args: argparse.Namespace, conn: psycopg.Connection) -> None:
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
            formatted = _format_metrics_line(metrics)
            if formatted:
                print(f"  {fold}: {formatted}")
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
            formatted = _format_metrics_line(row)
            if formatted:
                print(f"{row['model']} {row['fold']}: {formatted}")


def main(argv: list[str] | None = None) -> None:
    _configure_logging()
    parser = argparse.ArgumentParser(
        prog="mlb",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Local MLB research warehouse and prediction pipeline.",
        epilog=(
            "Core commands:\n"
            "  migrate, preflight, ingest, bootstrap, update, conform,\n"
            "  report, features, predict, train, evaluate, inventory,\n"
            "  doctor, dump, audit, status\n"
            "\n"
            "Read first: openspec/project.md, docs/ARCHITECTURE.md"
        ),
    )
    parser.add_argument(
        "--config",
        help="optional TOML settings file (defaults to ./mlb.toml when present)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="FILENAME",
        help="defer this migration version (by filename) to a later run; "
        "repeatable. For a documented forward dependency only -- see "
        "mlb_baseball/migrate.py's run().",
    )

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

    bootstrap_parser = subparsers.add_parser("bootstrap")
    update_parser = subparsers.add_parser("update")
    for profile_parser in (ingest_parser, bootstrap_parser, update_parser):
        profile_parser.add_argument("--profile", choices=sorted(PROFILES))
    for all_parser in (bootstrap_parser, update_parser):
        all_parser.add_argument(
            "--skip",
            action="append",
            default=[],
            metavar="CONNECTOR",
            help="exclude this connector from the run; repeatable. Used by "
            "scripts/mlb_daily_update.sh to skip mlb_api (kept fresh by the "
            "separate 5-minute mlb_api_update cron, whose ingestion lock the "
            "daily run would otherwise fight every time).",
        )

    subparsers.add_parser("conform")
    subparsers.add_parser("report", help="rebuild documented gold research tables")
    subparsers.add_parser("features")

    catalog_parser = subparsers.add_parser(
        "catalog", help="the metric catalog (mlb_baseball/metrics/*.yaml <-> meta.metric)"
    )
    catalog_commands = catalog_parser.add_subparsers(dest="catalog_command", required=True)
    catalog_commands.add_parser(
        "build", help="validate every metrics/*.yaml entry and rebuild meta.metric from it"
    )
    catalog_docs = catalog_commands.add_parser(
        "docs", help="generate the public (visibility: public) catalog Markdown page"
    )
    catalog_docs.add_argument(
        "--output",
        default="docs/site-src/metric-catalog.md",
        metavar="PATH",
        help="where to write the generated page (default: docs/site-src/metric-catalog.md)",
    )

    build_parser = subparsers.add_parser(
        "build",
        help="rebuild gold + the local DuckDB feature store (migrate -> conform -> report -> feat)",
    )
    build_parser.add_argument(
        "--db",
        metavar="PATH",
        help="DuckDB feature-store path (default: $MLB_DUCKDB_PATH, then ~/.mlb/mlb.duckdb)",
    )
    build_parser.add_argument("--feature-version", default="v1")
    build_parser.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=["migrate", "conform", "report"],
        metavar="STEP",
        help="skip a wrapped step (migrate|conform|report); repeatable",
    )
    build_parser.add_argument(
        "--only-features",
        action="store_true",
        help="skip migrate/conform/report and rebuild only the DuckDB feature store",
    )
    verify_parser = subparsers.add_parser(
        "verify",
        help="audit a local feature-store build: leakage checks + the Baseball-Reference tie-out",
    )
    verify_parser.add_argument(
        "--db",
        metavar="PATH",
        help="DuckDB feature-store path (default: $MLB_DUCKDB_PATH, then ~/.mlb/mlb.duckdb)",
    )
    verify_parser.add_argument("--feature-version", default="v1")
    verify_parser.add_argument(
        "--skip-tie-out",
        action="store_true",
        help="run only the leakage checks; skip the slower Baseball-Reference tie-out",
    )
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
    experiment_stepwise.add_argument("--min-survival-fraction", type=float, default=0.70)
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
    backup_parser.add_argument(
        "--keep",
        type=int,
        default=None,
        help="after a successful full backup, delete older full backups in "
        "--output-dir beyond the newest N (no effect with --schema-only)",
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

    # Season simulation command (PROJ-01)
    season_parser = subparsers.add_parser(
        "season-sim", help="run full-season Monte Carlo and playoff simulations"
    )
    season_parser.add_argument(
        "--season", type=int, default=2024, help="season year (default: 2024)"
    )
    season_parser.add_argument(
        "--sims", type=int, default=1000, help="number of season simulations"
    )
    season_parser.add_argument(
        "--seed", type=int, default=0, help="random seed for reproducibility"
    )
    season_parser.add_argument("--json", action="store_true", help="output result as JSON")

    # Simulation engine command (SIM-01)
    sim_parser = subparsers.add_parser("simulate", help="run Monte Carlo Markov game simulations")
    sim_parser.add_argument("--sims", type=int, default=10000, help="number of game simulations")
    sim_parser.add_argument("--seed", type=int, default=0, help="random seed for reproducibility")
    sim_parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2023, 2024],
        help="historical seasons for transition matrix",
    )
    sim_parser.add_argument(
        "--home-edge", type=float, default=0.0, help="home matchup run value edge per 100 pitches"
    )
    sim_parser.add_argument(
        "--away-edge", type=float, default=0.0, help="away matchup run value edge per 100 pitches"
    )
    sim_parser.add_argument(
        "--live", action="store_true", help="run in-game live simulation from state"
    )
    sim_parser.add_argument(
        "--inning", type=int, default=1, help="current inning for live simulation"
    )
    sim_parser.add_argument(
        "--bottom", action="store_true", help="bottom half of inning for live simulation"
    )
    sim_parser.add_argument(
        "--outs", type=int, choices=[0, 1, 2], default=0, help="current outs for live simulation"
    )
    sim_parser.add_argument("--home-score", type=int, default=0, help="current home score")
    sim_parser.add_argument("--away-score", type=int, default=0, help="current away score")

    # Live in-play command (LIVE-02)
    live_cli_parser = subparsers.add_parser(
        "live", help="monitor live in-play games and +EV prediction market opportunities"
    )
    live_cli_parser.add_argument(
        "--date", type=str, help="target game date (YYYY-MM-DD, default: today)"
    )
    live_cli_parser.add_argument(
        "--interval", type=int, default=15, help="refresh interval in seconds (default: 15)"
    )
    live_cli_parser.add_argument(
        "--sims", type=int, default=5000, help="number of live simulations per game (default: 5000)"
    )
    live_cli_parser.add_argument(
        "--watch", action="store_true", help="refresh continuously until Ctrl-C"
    )

    # Sabermetric research and citation catalog (RESEARCH-01)
    res_parser = subparsers.add_parser(
        "research", help="search sabermetric publications, books, and mathematical formulas"
    )
    res_parser.add_argument(
        "--query", type=str, default="", help="keyword search across titles, authors, and abstracts"
    )
    res_parser.add_argument(
        "--citation", type=str, help="lookup specific citation key (e.g. tango2006thebook)"
    )
    res_parser.add_argument("--json", action="store_true", help="output result as JSON")

    # Probability calibration and HFA decomposition (CALIB-01)
    cal_parser = subparsers.add_parser(
        "calibrate", help="evaluate probability calibration, reliability diagrams, and HFA metrics"
    )
    cal_parser.add_argument(
        "--prob", type=float, help="recalibrate a raw home win probability against MLB HFA baseline"
    )
    cal_parser.add_argument(
        "--eval",
        action="store_true",
        help="evaluate calibration error across historical DB predictions",
    )
    cal_parser.add_argument("--json", action="store_true", help="output result as JSON")

    # Historical Walk-Forward Backtesting Engine (BACKTEST-01)
    bt_parser = subparsers.add_parser(
        "backtest", help="run out-of-sample walk-forward portfolio backtesting across seasons"
    )
    bt_parser.add_argument(
        "--start-date",
        type=str,
        default="2024-04-01",
        help="backtest start date (default: 2024-04-01)",
    )
    bt_parser.add_argument(
        "--end-date", type=str, default="2024-09-30", help="backtest end date (default: 2024-09-30)"
    )
    bt_parser.add_argument(
        "--model", type=str, default="gbm-v2", help="model version (default: gbm-v2)"
    )
    bt_parser.add_argument(
        "--bankroll", type=float, default=10000.0, help="starting bankroll in USD (default: 10000)"
    )
    bt_parser.add_argument(
        "--min-edge", type=float, default=0.025, help="minimum edge to place bet (default: 0.025)"
    )
    bt_parser.add_argument(
        "--kelly-fraction",
        type=float,
        default=0.25,
        help="Kelly criterion fraction (default: 0.25)",
    )
    bt_parser.add_argument("--json", action="store_true", help="output backtest summary as JSON")

    # Dynamic Rest-of-Season simulation and playoff odds (ROS-01)
    ros_parser = subparsers.add_parser(
        "ros", help="run dynamic rest-of-season Monte Carlo simulation from current standings"
    )
    ros_parser.add_argument(
        "--season", type=int, default=2024, help="target MLB season (default: 2024)"
    )
    ros_parser.add_argument(
        "--as-of",
        type=str,
        default="2024-08-01",
        help="standings cutoff date (default: 2024-08-01)",
    )
    ros_parser.add_argument(
        "--sims", type=int, default=1000, help="number of Monte Carlo simulations (default: 1000)"
    )
    ros_parser.add_argument("--json", action="store_true", help="output ROS projections as JSON")

    # Research data and interop exporter (EXPORT-01)
    export_parser = subparsers.add_parser(
        "export",
        help=(
            "export database relations to CSV, Excel, or Parquet, or generate a "
            "public_safe/backbone bundle"
        ),
    )
    export_parser.add_argument(
        "relation",
        nargs="?",
        type=str,
        help="relation to export (e.g. gold.game_export, core.player, or game_export)",
    )
    export_parser.add_argument(
        "--season",
        type=int,
        help="filter export by season (for relations with a season column)",
    )
    export_parser.add_argument(
        "--format",
        choices=["csv", "xlsx", "parquet"],
        help="export format (default: inferred from --out extension or parquet)",
    )
    export_parser.add_argument(
        "--out",
        type=str,
        help="output file path or directory (default: <rel>.<ext> or export_bundle/)",
    )
    export_parser.add_argument(
        "--profile",
        choices=["public_safe"],
        help="export rights-filtered redistribution bundle (e.g. public_safe)",
    )
    export_parser.add_argument(
        "--preset",
        choices=["backbone"],
        help="export a named table-set bundle in HF dataset-repo layout (e.g. backbone)",
    )
    export_parser.add_argument(
        "--publish",
        choices=["hf"],
        help="publish the exported --preset bundle to a dataset host (requires --tag; "
        "reads the write credential from HF_TOKEN, never a flag)",
    )
    export_parser.add_argument(
        "--tag",
        type=str,
        help="release tag / revision to publish under (required with --publish)",
    )
    export_parser.add_argument(
        "--repo-id",
        type=str,
        default=None,
        help=(
            "HF dataset repo id to publish to (default: "
            "mlb_baseball.publish.DEFAULT_REPO_ID -- override once the final "
            "namespace is decided, e.g. an org account)"
        ),
    )
    export_parser.add_argument(
        "--zip",
        action="store_true",
        help="compress export bundle directory into a zip archive",
    )

    # Bayesian constrained ensemble stacking meta-learner (STACK-02)
    stack_parser = subparsers.add_parser(
        "stack", help="train and evaluate Bayesian convex ensemble stacking meta-learner (STACK-02)"
    )
    stack_parser.add_argument(
        "--train", action="store_true", help="train stacker on historical model predictions"
    )
    stack_parser.add_argument(
        "--eval", action="store_true", help="evaluate out-of-fold Brier skill score"
    )
    stack_parser.add_argument("--json", action="store_true", help="output stacker results as JSON")

    # Continuous model drift & calibration monitor (DRIFT-01)
    drift_parser = subparsers.add_parser(
        "drift",
        help="monitor rolling model calibration error, Platt slope, and concept drift (DRIFT-01)",
    )
    drift_parser.add_argument(
        "--model", type=str, default="gbm-v2", help="model version to evaluate (default: gbm-v2)"
    )
    drift_parser.add_argument(
        "--window", type=int, default=40, help="rolling window size in games (default: 40)"
    )
    drift_parser.add_argument(
        "--step", type=int, default=15, help="step size in games (default: 15)"
    )
    drift_parser.add_argument("--json", action="store_true", help="output drift report as JSON")

    # Correlated same-game parlay (SGP) engine & joint simulation (PARLAY-01)
    parlay_parser = subparsers.add_parser(
        "parlay",
        help="evaluate correlated same-game parlays (SGPs) via copula simulation (PARLAY-01)",
    )
    parlay_parser.add_argument(
        "--sims", type=int, default=10000, help="number of Monte Carlo simulations (default: 10000)"
    )
    parlay_parser.add_argument(
        "--legs", type=int, default=2, help="number of legs to optimize (default: 2)"
    )
    parlay_parser.add_argument(
        "--min-boost",
        type=float,
        default=1.10,
        help="minimum correlation multiplier boost (default: 1.10)",
    )
    parlay_parser.add_argument("--json", action="store_true", help="output parlay analysis as JSON")

    # Pitch physics, repertoire & Stuff+ / Location+ rating (STUFF-01)
    stuff_parser = subparsers.add_parser(
        "stuff",
        help="evaluate pitch trajectory aerodynamics and Stuff+/Location+ (STUFF-01)",
    )
    stuff_parser.add_argument(
        "--velo", type=float, default=95.0, help="release velocity in mph (default: 95.0)"
    )
    stuff_parser.add_argument(
        "--ivb", type=float, default=16.5, help="induced vertical break in inches (default: 16.5)"
    )
    stuff_parser.add_argument(
        "--hb", type=float, default=7.0, help="horizontal break in inches (default: 7.0)"
    )
    stuff_parser.add_argument(
        "--pitch-type",
        type=str,
        default="FF",
        help="pitch type code FF/SL/ST/CU/CH/SI (default: FF)",
    )
    stuff_parser.add_argument("--json", action="store_true", help="output pitch grade as JSON")

    # 2D strike zone KDE and spatial coordinates (HEATMAP-01)
    heatmap_parser = subparsers.add_parser(
        "heatmap",
        help="generate 2D strike zone KDE density surfaces and spray coordinates (HEATMAP-01)",
    )
    heatmap_parser.add_argument(
        "--ev", type=float, default=105.0, help="exit velocity mph for trajectory (default: 105.0)"
    )
    heatmap_parser.add_argument(
        "--la", type=float, default=28.0, help="launch angle degrees (default: 28.0)"
    )
    heatmap_parser.add_argument(
        "--spray", type=float, default=0.0, help="spray angle degrees (default: 0.0)"
    )
    heatmap_parser.add_argument("--json", action="store_true", help="output spatial data as JSON")

    # Hierarchical neural combiner and entity embeddings (NEURAL-01)
    neural_parser = subparsers.add_parser(
        "neural",
        help="evaluate hierarchical neural network with entity embeddings (NEURAL-01)",
    )
    neural_parser.add_argument(
        "--tree-prob",
        type=float,
        default=0.58,
        help="baseline tree win probability (default: 0.58)",
    )
    neural_parser.add_argument(
        "--json", action="store_true", help="output neural inference as JSON"
    )

    # Master end-to-end quantitative daily pipeline (PIPE-02)
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="execute complete 8-phase end-to-end daily quantitative pipeline (PIPE-02)",
    )
    pipeline_parser.add_argument(
        "--date", type=str, help="target game date (YYYY-MM-DD, default: today)"
    )
    pipeline_parser.add_argument(
        "--sims", type=int, default=5000, help="number of Monte Carlo simulations (default: 5000)"
    )
    pipeline_parser.add_argument(
        "--bankroll", type=float, default=10000.0, help="bankroll in USD (default: 10000.0)"
    )
    pipeline_parser.add_argument(
        "--skip-doctor", action="store_true", help="skip preflight doctor health checks"
    )
    pipeline_parser.add_argument(
        "--json", action="store_true", help="output pipeline report as JSON"
    )

    # Visual asset & chart generator (VISUAL-01)
    visual_parser = subparsers.add_parser(
        "visual",
        help="generate SVG vector charts for strike zones, spray maps, and WE graphs (VISUAL-01)",
    )
    visual_parser.add_argument(
        "--type", choices=["strikezone", "spray", "we"], default="spray", help="chart type"
    )
    visual_parser.add_argument("--output", type=str, help="output SVG file path")
    visual_parser.add_argument("--json", action="store_true", help="output chart metadata as JSON")

    # Live in-game hedging and middle bet calculator (HEDGE-01)
    hedge_parser = subparsers.add_parser(
        "hedge",
        help="calculate guaranteed-profit live in-play hedges and middle bets (HEDGE-01)",
    )
    hedge_parser.add_argument(
        "--stake", type=float, default=100.0, help="initial wager stake USD (default: 100.0)"
    )
    hedge_parser.add_argument(
        "--initial-odds", type=float, default=2.50, help="initial decimal odds (default: 2.50)"
    )
    hedge_parser.add_argument(
        "--hedge-odds",
        type=float,
        default=2.20,
        help="current opposite decimal odds (default: 2.20)",
    )
    hedge_parser.add_argument("--json", action="store_true", help="output hedge plan as JSON")

    # Pure-Python SVG Strike Zone 3D Isometric (ZONE-ISOMETRIC-01)
    zi_parser = subparsers.add_parser(
        "zone-isometric",
        help="generate vector SVG 3D isometric strike zone box (ZONE-ISOMETRIC-01)",
    )
    zi_parser.add_argument("--title", type=str, default="Skubal 3D Strike Zone", help="chart title")
    zi_parser.add_argument("--pitcher", type=str, default="Tarik Skubal", help="pitcher name")

    # Pure-Python SVG spray chart heatmap (SPRAY-HEATMAP-01)
    sh_parser = subparsers.add_parser(
        "spray-heatmap",
        help="generate vector SVG spray chart heatmap (SPRAY-HEATMAP-01)",
    )
    sh_parser.add_argument("--title", type=str, default="Spray Chart Heatmap", help="chart title")
    sh_parser.add_argument("--batter", type=str, default="Shohei Ohtani", help="batter name")
    sh_parser.add_argument("--hand", type=str, default="L", help="batter hand R or L (default: L)")

    # Pitcher pitch tunnel decision separation chart (TUNNEL-DECISION-01)
    td_parser = subparsers.add_parser(
        "tunnel-decision",
        help="generate vector SVG pitch tunnel decision separation chart (TUNNEL-DECISION-01)",
    )
    td_parser.add_argument(
        "--title", type=str, default="Skenes Fastball-Splinker Tunnel", help="chart title"
    )
    td_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Pitcher arsenal movement & spin polar compass (POLAR-COMPASS-01)
    pc_parser = subparsers.add_parser(
        "polar-compass",
        help="generate vector SVG pitcher arsenal movement & spin polar compass (POLAR-COMPASS-01)",
    )
    pc_parser.add_argument(
        "--title", type=str, default="Paul Skenes Movement Polar Compass", help="chart title"
    )
    pc_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter Statcast EV vs LA contact grid (BARREL-GRID-01)
    bg_parser = subparsers.add_parser(
        "barrel-grid",
        help="generate vector SVG Statcast contact quality barrel grid (BARREL-GRID-01)",
    )
    bg_parser.add_argument(
        "--title", type=str, default="Shohei Ohtani Statcast Contact Grid", help="chart title"
    )
    bg_parser.add_argument("--batter", type=str, default="Shohei Ohtani", help="batter name")

    # Pitcher count-dependent pitch mix transition flow (FLOW-MIX-01)
    fm_parser = subparsers.add_parser(
        "flow-mix",
        help="generate vector SVG count transition pitch mix flow chart (FLOW-MIX-01)",
    )
    fm_parser.add_argument(
        "--title", type=str, default="Paul Skenes Count Flow Mix", help="chart title"
    )
    fm_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Pitcher release point & tunnel box chart (TUNNEL-BOX-01)
    tb_parser = subparsers.add_parser(
        "tunnel-box",
        help="generate vector SVG release window & tunnel box chart (TUNNEL-BOX-01)",
    )
    tb_parser.add_argument(
        "--title", type=str, default="Paul Skenes Release & Tunnel Box", help="chart title"
    )
    tb_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter LA vs EV contour heatmap (LA-EV-CONTOUR-01)
    la_ev_parser = subparsers.add_parser(
        "la-ev-contour",
        help="generate vector SVG launch angle vs exit velocity contour heatmap (LA-EV-CONTOUR-01)",
    )
    la_ev_parser.add_argument(
        "--title", type=str, default="Aaron Judge LA vs EV Heatmap", help="chart title"
    )
    la_ev_parser.add_argument("--batter", type=str, default="Aaron Judge", help="batter name")

    # Pitcher spin polar clock chart (SPIN-POLAR-01)
    sp_pol_parser = subparsers.add_parser(
        "spin-polar",
        help="generate vector SVG polar spin clock chart (SPIN-POLAR-01)",
    )
    sp_pol_parser.add_argument(
        "--title", type=str, default="Paul Skenes Polar Spin Clock", help="chart title"
    )
    sp_pol_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter spray isochrones chart (SPRAY-ISO-01)
    sp_iso_parser = subparsers.add_parser(
        "spray-iso",
        help="generate vector SVG spray chart with distance isochrones (SPRAY-ISO-01)",
    )
    sp_iso_parser.add_argument(
        "--title", type=str, default="Aaron Judge Spray & Distance", help="chart title"
    )
    sp_iso_parser.add_argument("--batter", type=str, default="Aaron Judge", help="batter name")

    # Pitch arsenal break diamond (BREAK-DIAMOND-01)
    bd_parser = subparsers.add_parser(
        "break-diamond",
        help="generate vector SVG horizontal vs vertical pitch break scatter (BREAK-DIAMOND-01)",
    )
    bd_parser.add_argument(
        "--title", type=str, default="Paul Skenes Arsenal Break", help="chart title"
    )
    bd_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter 9x9 attack zone grid (ATTACK-9X9-01)
    a9_parser = subparsers.add_parser(
        "attack-9x9",
        help="generate vector SVG 9x9 strike zone attack grid heatmap (ATTACK-9X9-01)",
    )
    a9_parser.add_argument(
        "--title", type=str, default="Juan Soto 9x9 Attack Zone", help="chart title"
    )
    a9_parser.add_argument("--batter", type=str, default="Juan Soto", help="batter name")
    a9_parser.add_argument(
        "--mode", type=str, default="wOBA", help="metric mode wOBA/Swing/Whiff (default: wOBA)"
    )

    # Pitch arsenal release window scatter box plot (RELEASE-BOX-01)
    box_parser = subparsers.add_parser(
        "release-box",
        help="generate vector SVG arsenal release window scatter plot (RELEASE-BOX-01)",
    )
    box_parser.add_argument(
        "--title", type=str, default="Paul Skenes Release Window", help="chart title"
    )
    box_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter spray & elevation rose chart (SPRAY-ROSE-01)
    rose_parser = subparsers.add_parser(
        "spray-rose",
        help="generate vector SVG 3D spray and elevation polar rose chart (SPRAY-ROSE-01)",
    )
    rose_parser.add_argument(
        "--title", type=str, default="Shohei Ohtani Spray & Elevation Rose", help="chart title"
    )
    rose_parser.add_argument("--batter", type=str, default="Shohei Ohtani", help="batter name")

    # Pitch arsenal separation diamond plot (SEPARATION-PLOT-01)
    sep_parser = subparsers.add_parser(
        "separation-plot",
        help="generate vector SVG arsenal velocity vs movement plot (SEPARATION-PLOT-01)",
    )
    sep_parser.add_argument(
        "--title", type=str, default="Tarik Skubal Arsenal Separation", help="chart title"
    )
    sep_parser.add_argument("--pitcher", type=str, default="Tarik Skubal", help="pitcher name")

    # Pitch arsenal spin axis clock (SPIN-CLOCK-01)
    clk_parser = subparsers.add_parser(
        "spin-clock",
        help="generate vector SVG 12-hour pitch spin axis clock dial chart (SPIN-CLOCK-01)",
    )
    clk_parser.add_argument(
        "--title", type=str, default="Paul Skenes Arsenal Spin Clock", help="chart title"
    )
    clk_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Pitcher arm slot angle & release consistency (ARM-SLOT-01)
    asl_parser = subparsers.add_parser(
        "arm-slot",
        help="calculate pitcher arm slot angle and release point consistency (ARM-SLOT-01)",
    )
    asl_parser.add_argument(
        "--rel-x", type=float, default=-2.2, help="release X ft (default: -2.2)"
    )
    asl_parser.add_argument("--rel-z", type=float, default=5.8, help="release Z ft (default: 5.8)")
    asl_parser.add_argument(
        "--height", type=float, default=75.0, help="pitcher height inches (default: 75.0)"
    )
    asl_parser.add_argument(
        "--disp", type=float, default=1.3, help="release dispersion std inches (default: 1.3)"
    )
    asl_parser.add_argument(
        "--json", action="store_true", help="output arm slot evaluation as JSON"
    )

    # Strike zone 5x5 iso-contour surface (ZONE-SURFACE-01)
    zsf_parser = subparsers.add_parser(
        "zone-surface",
        help="generate vector SVG 5x5 strike zone iso-contour heat surface chart (ZONE-SURFACE-01)",
    )
    zsf_parser.add_argument(
        "--title", type=str, default="Juan Soto Slugging Surface", help="chart title"
    )
    zsf_parser.add_argument("--batter", type=str, default="Juan Soto", help="batter name")
    zsf_parser.add_argument("--metric", type=str, default="Expected SLG", help="metric label")

    # 3D isometric pitch trajectory flight (FLIGHT-3D-01)
    f3d_parser = subparsers.add_parser(
        "flight-3d",
        help="generate vector SVG 3D isometric pitch flight and tunnel chart (FLIGHT-3D-01)",
    )
    f3d_parser.add_argument(
        "--title", type=str, default="Tarik Skubal 3D Pitch Tunnel", help="chart title"
    )
    f3d_parser.add_argument("--pitcher", type=str, default="Tarik Skubal", help="pitcher name")

    # Win probability replay visualizer (WPA-REPLAY-01)
    wpa_rep_parser = subparsers.add_parser(
        "wpa-replay",
        help="generate vector SVG game win probability replay flow chart (WPA-REPLAY-01)",
    )
    wpa_rep_parser.add_argument(
        "--title", type=str, default="2024 WS Game 1 Replay", help="chart title"
    )
    wpa_rep_parser.add_argument("--home", type=str, default="LAD", help="home team code")
    wpa_rep_parser.add_argument("--away", type=str, default="NYY", help="away team code")

    # Batter BABIP luck deficit (BABIP-LUCK-01)
    babip_parser = subparsers.add_parser(
        "babip",
        help="evaluate BABIP luck deficit and xBABIP regression (BABIP-LUCK-01)",
    )
    babip_parser.add_argument(
        "--actual", type=float, default=0.320, help="Actual BABIP (default: 0.320)"
    )
    babip_parser.add_argument("--ld", type=float, default=0.21, help="Line Drive%% (default: 0.21)")
    babip_parser.add_argument(
        "--hard-hit", type=float, default=0.42, help="Hard-Hit%% (default: 0.42)"
    )
    babip_parser.add_argument(
        "--speed", type=float, default=27.5, help="Sprint Speed ft/s (default: 27.5)"
    )
    babip_parser.add_argument("--json", action="store_true", help="output BABIP evaluation as JSON")

    # Matchup comparison scouting card (COMPARE-CARD-01)
    card_parser = subparsers.add_parser(
        "matchup-card",
        help="generate vector SVG side-by-side player matchup scouting card (COMPARE-CARD-01)",
    )
    card_parser.add_argument("--batter", type=str, default="Aaron Judge", help="batter name")
    card_parser.add_argument("--pitcher", type=str, default="Gerrit Cole", help="pitcher name")

    # Spatial strike zone hexbin map (HEXBIN-01)
    hex_parser = subparsers.add_parser(
        "hexbin",
        help="generate vector SVG 2D strike zone hexbin attack map (HEXBIN-01)",
    )
    hex_parser.add_argument(
        "--title", type=str, default="Shohei Ohtani Spatial Attack Zone", help="chart title"
    )

    # RE24 Matrix Heatmap (RE24-MAP-01)
    re24_parser = subparsers.add_parser(
        "re24-heatmap",
        help="generate vector SVG 24-state run expectancy matrix heatmap (RE24-MAP-01)",
    )
    re24_parser.add_argument(
        "--title", type=str, default="MLB 24-State Run Expectancy Matrix", help="chart title"
    )

    # Game score flow chart (FLOW-01)
    flow_parser = subparsers.add_parser(
        "score-flow",
        help="generate vector SVG game score progression chart (FLOW-01)",
    )
    flow_parser.add_argument(
        "--title", type=str, default="LAD 5, SF 3 Live Score Flow", help="chart title"
    )
    flow_parser.add_argument("--home", type=str, default="LAD", help="home team (default: LAD)")
    flow_parser.add_argument("--away", type=str, default="SF", help="away team (default: SF)")

    # Pitch break chart (BREAK-PLOT-01)
    bplot_parser = subparsers.add_parser(
        "break-plot",
        help="generate 2D vector SVG pitch movement break plot (BREAK-PLOT-01)",
    )
    bplot_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Odds movement chart (ODDS-CHART-01)
    ochart_parser = subparsers.add_parser(
        "odds-chart",
        help="generate vector SVG market line movement chart (ODDS-CHART-01)",
    )
    ochart_parser.add_argument(
        "--title", type=str, default="NYY vs BOS Odds Movement", help="chart title"
    )
    ochart_parser.add_argument("--home", type=str, default="NYY", help="home team (default: NYY)")
    ochart_parser.add_argument("--away", type=str, default="BOS", help="away team (default: BOS)")

    # First inning valuation (NRFI-01)
    nrfi_parser = subparsers.add_parser(
        "nrfi",
        help="evaluate first-inning run scored NRFI / YRFI (NRFI-01)",
    )
    nrfi_parser.add_argument("--home", type=str, default="LAD", help="home team (default: LAD)")
    nrfi_parser.add_argument("--away", type=str, default="SF", help="away team (default: SF)")
    nrfi_parser.add_argument(
        "--home-top3", type=float, default=0.355, help="home top 3 wOBA (default: 0.355)"
    )
    nrfi_parser.add_argument(
        "--away-top3", type=float, default=0.330, help="away top 3 wOBA (default: 0.330)"
    )
    nrfi_parser.add_argument(
        "--home-era", type=float, default=3.10, help="home starter inn 1 ERA (default: 3.10)"
    )
    nrfi_parser.add_argument(
        "--away-era", type=float, default=3.60, help="away starter inn 1 ERA (default: 3.60)"
    )
    nrfi_parser.add_argument("--json", action="store_true", help="output NRFI result as JSON")

    # Visual spider radar chart (RADAR-01)
    radar_parser = subparsers.add_parser(
        "radar",
        help="generate multi-axis vector SVG spider radar chart (RADAR-01)",
    )
    radar_parser.add_argument("--player", type=str, default="Scouting Radar", help="chart title")
    radar_parser.add_argument("--contact", type=float, default=85.0, help="contact grade (0-100)")
    radar_parser.add_argument("--power", type=float, default=90.0, help="power grade (0-100)")
    radar_parser.add_argument(
        "--discipline", type=float, default=95.0, help="discipline grade (0-100)"
    )
    radar_parser.add_argument("--speed", type=float, default=55.0, help="speed grade (0-100)")
    radar_parser.add_argument("--defense", type=float, default=70.0, help="defense grade (0-100)")

    # Pitcher arsenals tunneling (TUNNEL-01)
    tun_parser = subparsers.add_parser(
        "tunnel",
        help="evaluate pitch pair tunneling and POC separation (TUNNEL-01)",
    )
    tun_parser.add_argument(
        "--ff-velo", type=float, default=96.0, help="fastball velo mph (default: 96.0)"
    )
    tun_parser.add_argument(
        "--sl-velo", type=float, default=86.0, help="slider velo mph (default: 86.0)"
    )
    tun_parser.add_argument(
        "--ff-ivb", type=float, default=17.0, help="fastball IVB in (default: 17.0)"
    )
    tun_parser.add_argument(
        "--sl-ivb", type=float, default=2.0, help="slider IVB in (default: 2.0)"
    )
    tun_parser.add_argument(
        "--ff-hb", type=float, default=10.0, help="fastball HB in (default: 10.0)"
    )
    tun_parser.add_argument(
        "--sl-hb", type=float, default=-8.0, help="slider HB in (default: -8.0)"
    )
    tun_parser.add_argument("--json", action="store_true", help="output tunneling result as JSON")

    # REST API server (API-01)
    api_parser = subparsers.add_parser(
        "serve-api",
        help="run lightweight local REST API gateway (API-01)",
    )
    api_parser.add_argument(
        "--port", type=int, default=8000, help="API server port (default: 8000)"
    )
    api_parser.add_argument(
        "--test-health", action="store_true", help="test route /api/v1/health and exit"
    )

    # Multi-book odds line shopping (SHOP-01)
    shop_parser = subparsers.add_parser(
        "shop",
        help="scan multi-book market offerings for best prices and +EV (SHOP-01)",
    )
    shop_parser.add_argument("--home", type=str, default="LAD", help="home team")
    shop_parser.add_argument("--away", type=str, default="SF", help="away team")
    shop_parser.add_argument(
        "--model-prob", type=float, default=0.56, help="model home win prob (default: 0.56)"
    )
    shop_parser.add_argument("--json", action="store_true", help="output line shopping as JSON")

    # Scheduled daily automation daemon (CRON-01)
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="run daily automation cycle and warm serving cache (CRON-01)",
    )
    daemon_parser.add_argument(
        "--date", type=str, default="2026-08-24", help="forecast date (YYYY-MM-DD)"
    )
    daemon_parser.add_argument(
        "--skip-doctor", action="store_true", help="skip doctor preflight checks"
    )
    daemon_parser.add_argument("--json", action="store_true", help="output daemon summary as JSON")

    # Unified daily research and wagering briefing (PIPE-01)
    daily_parser = subparsers.add_parser(
        "daily",
        help="generate unified daily quantitative research, forecasting, and wagering briefing",
    )
    daily_parser.add_argument(
        "--date", type=str, help="target game date (YYYY-MM-DD, default: today)"
    )
    daily_parser.add_argument(
        "--bankroll", type=float, default=10000.0, help="total bankroll in USD (default: 10000)"
    )
    daily_parser.add_argument(
        "--min-edge", type=float, default=0.020, help="min edge threshold (default: 0.020)"
    )
    daily_parser.add_argument("--json", action="store_true", help="output result as JSON")

    # Kelly Criterion portfolio allocator (PORT-01)
    kelly_parser = subparsers.add_parser(
        "kelly", help="calculate optimal Kelly Criterion portfolio allocation for +EV markets"
    )
    kelly_parser.add_argument(
        "--bankroll", type=float, default=10000.0, help="total bankroll in USD (default: 10000)"
    )
    kelly_parser.add_argument(
        "--fraction", type=float, default=0.25, help="Kelly fraction multiplier (default: 0.25)"
    )
    kelly_parser.add_argument(
        "--max-bet", type=float, default=0.025, help="max single position fraction (default: 0.025)"
    )
    kelly_parser.add_argument(
        "--max-total",
        type=float,
        default=0.150,
        help="max total portfolio exposure (default: 0.150)",
    )
    kelly_parser.add_argument(
        "--min-edge", type=float, default=0.025, help="min edge threshold (default: 0.025)"
    )
    kelly_parser.add_argument("--json", action="store_true", help="output result as JSON")

    # Player props command (PROP-01)
    props_parser = subparsers.add_parser(
        "props", help="forecast player proposition markets (K%%, outs, hits, HR)"
    )
    props_parser.add_argument("--game-pk", type=str, help="target MLB game PK to look up starters")
    props_parser.add_argument("--pitcher-k", type=float, help="manual starter K%% (e.g. 0.28)")
    props_parser.add_argument(
        "--opp-k", type=float, default=0.225, help="opposing lineup K%% (default: 0.225)"
    )
    props_parser.add_argument(
        "--pitcher-fip", type=float, default=3.80, help="starter FIP (default: 3.80)"
    )
    props_parser.add_argument(
        "--opp-wrc", type=float, default=100.0, help="opposing team wRC+ (default: 100)"
    )
    props_parser.add_argument("--rest-days", type=int, default=5, help="pitcher rest days")

    # Serving layer query command (SRV-01, LIVE-01)
    serve_parser = subparsers.add_parser(
        "serve", help="query analytical serving marts (daily-grid, props, live-tracker, alpha)"
    )
    serve_parser.add_argument(
        "mart", choices=["daily-grid", "pitcher-card", "props", "live-tracker", "alpha"]
    )
    serve_parser.add_argument("--date", type=str, help="game date filter (YYYY-MM-DD)")
    serve_parser.add_argument("--game-pk", type=str, help="MLB game PK filter")
    serve_parser.add_argument(
        "--player-id", type=int, help="internal player ID filter for pitcher card"
    )
    serve_parser.add_argument(
        "--min-edge", type=float, default=0.025, help="minimum edge threshold for +EV screener"
    )
    serve_parser.add_argument("--json", action="store_true", help="output result as JSON")

    args = parser.parse_args(argv)

    try:
        settings = config.load_settings(args.config)
        config.apply_settings(settings)
    except config.ConfigError as exc:
        parser.error(str(exc))

    profile = getattr(args, "profile", None) or active_profile()

    if args.command == "migrate":
        migrate.main(skip=set(args.skip))
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
        _run_all("bootstrap", profile, skip=args.skip)
    elif args.command == "update":
        _run_all("update", profile, skip=args.skip)
    elif args.command == "conform":
        for table, count in conform.run().items():
            print(f"{table}: {count} rows")
    elif args.command == "report":
        for table, count in report.run().items():
            print(f"{table}: {count} rows")
    elif args.command == "catalog":
        if args.catalog_command == "build":
            count = metric_catalog.build()
            print(f"meta.metric: {count} rows")
        elif args.catalog_command == "docs":
            with metric_catalog.get_connection() as conn:
                out_path = metric_catalog.write_docs_page(conn, Path(args.output))
            print(f"wrote {out_path}")
    elif args.command == "build":
        skip = set(args.skip)
        if not args.only_features:
            if "migrate" not in skip:
                migrate.main(skip=set())
                print("migrate: done")
            if "conform" not in skip:
                for table, count in conform.run().items():
                    print(f"{table}: {count} rows")
            if "report" not in skip:
                for table, count in report.run().items():
                    print(f"{table}: {count} rows")
        for relation, count in feat.build(
            duckdb_path=args.db, feature_version=args.feature_version
        ).items():
            print(f"{relation}: {count} rows")
    elif args.command == "verify":
        ok = feat.verify(
            duckdb_path=args.db,
            feature_version=args.feature_version,
            run_tie_out=not args.skip_tie_out,
        )
        if not ok:
            sys.exit(1)
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
        if args.keep is not None and args.keep < 1:
            parser.error("--keep must be >= 1")
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
            if args.keep is not None and not args.schema_only and not args.schemas:
                deleted = backup.rotate_backups(
                    config.database_url(), args.output_dir, keep=args.keep
                )
                if deleted:
                    names = ", ".join(p.name for p in deleted)
                    print(f"Rotated {len(deleted)} old backup(s): {names}")
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
            _run_experiment_command(args, conn)
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
    elif args.command == "season-sim":
        import json as json_lib

        from mlb_baseball.db import get_connection
        from mlb_baseball.model import season

        with get_connection() as conn:
            sched = season.load_schedule_from_db(args.season, conn=conn)
            if not sched:
                sched = season.generate_balanced_schedule(season.ALL_MLB_TEAMS)

            talents = {t: 0.500 for t in season.ALL_MLB_TEAMS}
            res = season.simulate_season_monte_carlo(
                schedule=sched,
                team_true_talents=talents,
                n_simulations=args.sims,
                seed=args.seed,
                season=args.season,
            )

        if args.json:
            out_dict = {
                "season": res.season,
                "simulations_run": res.simulations_run,
                "duration_ms": res.duration_ms,
                "simulations_per_sec": res.simulations_per_sec,
                "projections": {
                    t: {
                        "team": p.team_code,
                        "league": p.league,
                        "division": p.division,
                        "mean_wins": p.mean_wins,
                        "mean_losses": p.mean_losses,
                        "std_wins": p.std_wins,
                        "make_playoffs_prob": p.make_playoffs_prob,
                        "win_division_prob": p.win_division_prob,
                        "win_wild_card_prob": p.win_wild_card_prob,
                        "win_pennant_prob": p.win_pennant_prob,
                        "win_world_series_prob": p.win_world_series_prob,
                    }
                    for t, p in res.team_projections.items()
                },
            }
            print(json_lib.dumps(out_dict, indent=2))
        else:
            print(
                f"Season {res.season} Monte Carlo Simulation "
                f"({res.simulations_run:,} sims in {res.duration_ms:.1f}ms | "
                f"{res.simulations_per_sec:,.0f} seasons/sec):"
            )
            print(
                f"{'Team':<6} {'Div':<11} {'Wins':<6} {'Losses':<6} "
                f"{'Playoff%':<9} {'Div%':<7} {'Pennant%':<9} {'WS%':<7}"
            )
            print("-" * 65)
            sorted_teams = sorted(
                res.team_projections.values(), key=lambda p: (p.league, p.division, -p.mean_wins)
            )
            cur_div = ""
            for proj in sorted_teams:
                if proj.division != cur_div:
                    cur_div = proj.division
                    print(f"--- {cur_div} ---")
                print(
                    f"{proj.team_code:<6} {proj.division:<11} "
                    f"{proj.mean_wins:<6.1f} {proj.mean_losses:<6.1f} "
                    f"{proj.make_playoffs_prob * 100:<8.1f}% {proj.win_division_prob * 100:<6.1f}% "
                    f"{proj.win_pennant_prob * 100:<8.1f}% "
                    f"{proj.win_world_series_prob * 100:<6.1f}%"
                )
    elif args.command == "simulate":
        from mlb_baseball.db import get_connection
        from mlb_baseball.model import markov, simulate

        with get_connection() as conn:
            dist = markov.estimate_outcome_distribution(conn, seasons=args.seasons)
            if not dist:
                print(f"No Retrosheet transition data found for seasons {args.seasons}")
                sys.exit(1)
            table = simulate.DenseOutcomeTable.from_distribution(dist)
            home_table = table.adjust_for_matchup(args.home_edge)
            away_table = table.adjust_for_matchup(args.away_edge)

            if args.live:
                cur_state = markov.BaseOutState(outs=args.outs, on1=False, on2=False, on3=False)
                live_res = simulate.simulate_live_game_fast(
                    home_table=home_table,
                    away_table=away_table,
                    current_inning=args.inning,
                    is_bottom_half=args.bottom,
                    current_state=cur_state,
                    home_score=args.home_score,
                    away_score=args.away_score,
                    n_simulations=args.sims,
                    seed=args.seed,
                )
                print(
                    f"Live Simulation [{live_res.device.upper()}] "
                    f"({live_res.simulations_run:,} sims in {live_res.duration_ms:.1f}ms | "
                    f"{live_res.simulations_per_sec:,.0f} sims/sec):"
                )
                half_str = "Bottom" if live_res.is_bottom_half else "Top"
                print(
                    f"  Inning: {half_str} {live_res.current_inning} ({args.outs} outs) | "
                    f"Score: Away {live_res.away_score} - Home {live_res.home_score}"
                )
                print(
                    f"  Home Win: {live_res.home_win_prob * 100:.1f}% | "
                    f"Away Win: {live_res.away_win_prob * 100:.1f}%"
                )
                print(
                    f"  Home -1.5 Cover: {live_res.home_cover_run_line_prob * 100:.1f}% | "
                    f"Away +1.5 Cover: {live_res.away_cover_run_line_prob * 100:.1f}%"
                )
                print(
                    f"  Expected Final: Away {live_res.expected_final_away_runs:.2f} - "
                    f"Home {live_res.expected_final_home_runs:.2f} "
                    f"(Total: {live_res.expected_final_total_runs:.2f})"
                )
                print("  Over / Under Probs:")
                for line, prob in sorted(live_res.over_under_probs.items()):
                    print(f"    Over {line}: {prob * 100:.1f}%")
            else:
                sim_res = simulate.simulate_games_fast(
                    home_table=home_table,
                    away_table=away_table,
                    n_simulations=args.sims,
                    seed=args.seed,
                )
                print(
                    f"Monte Carlo Game Simulation [{sim_res.device.upper()}] "
                    f"({sim_res.simulations_run:,} sims in {sim_res.duration_ms:.1f}ms | "
                    f"{sim_res.simulations_per_sec:,.0f} sims/sec):"
                )
                print(
                    f"  Home Win Prob: {sim_res.home_win_prob * 100:.1f}% | "
                    f"Away Win Prob: {sim_res.away_win_prob * 100:.1f}%"
                )
                print(
                    f"  Home -1.5 Cover: {sim_res.home_cover_run_line_prob * 100:.1f}% | "
                    f"Away +1.5 Cover: {sim_res.away_cover_run_line_prob * 100:.1f}%"
                )
                print(
                    f"  Expected Runs: Home {sim_res.expected_home_runs:.2f} | "
                    f"Away {sim_res.expected_away_runs:.2f} | "
                    f"Total {sim_res.expected_total_runs:.2f}"
                )
                print("  Totals Over/Under:")
                for line, prob in sorted(sim_res.over_under_probs.items()):
                    print(
                        f"    Over {line}: {prob * 100:.1f}% | "
                        f"Under {line}: {(1.0 - prob) * 100:.1f}%"
                    )
    elif args.command == "live":
        import time as time_lib

        from mlb_baseball import live
        from mlb_baseball.db import get_connection
        from mlb_baseball.model import markov, simulate

        with get_connection() as conn:
            dist = markov.estimate_outcome_distribution(conn, seasons=[2023, 2024])
            if not dist:
                print("No Retrosheet transition data found.")
                sys.exit(1)
            table = simulate.DenseOutcomeTable.from_distribution(dist)

            while True:
                active_games = live.fetch_active_live_games(target_date=args.date, conn=conn)
                snapshots = []
                for g in active_games:
                    snap = live.evaluate_live_game_state(
                        game_data=g,
                        transition_table=table,
                        n_simulations=args.sims,
                    )
                    snapshots.append(snap)

                live.print_live_tracker_report(snapshots)
                if not args.watch:
                    break
                try:
                    time_lib.sleep(args.interval)
                except KeyboardInterrupt:
                    print("\nLive tracking stopped by user.")
                    break
    elif args.command == "props":
        from mlb_baseball.db import get_connection
        from mlb_baseball.model import props

        if args.game_pk:
            with get_connection() as conn:
                game_props = props.fetch_game_pitcher_props(args.game_pk, conn=conn)
                if not game_props:
                    print(f"No starting pitcher data found for game_pk={args.game_pk}")
                for p in game_props:
                    print(f"Pitcher: {p.player_name} (ID {p.player_id})")
                    print(
                        f"  Projected K%: {p.projected_k_pct * 100:.1f}% | "
                        f"Expected BF: {p.expected_bf:.1f} | Expected K: {p.expected_k:.2f}"
                    )
                    print("  Strikeout Lines:")
                    for line, prob in sorted(p.over_under_probs.items()):
                        print(
                            f"    Over {line}: {prob * 100:.1f}% | "
                            f"Under {line}: {(1.0 - prob) * 100:.1f}%"
                        )
        elif args.pitcher_k is not None:
            k_prop = props.predict_pitcher_strikeouts(
                player_id=1,
                player_name="Target Pitcher",
                mlb_game_pk="manual",
                pitcher_k_pct=args.pitcher_k,
                opponent_k_pct=args.opp_k,
                pitcher_rest_days=args.rest_days,
            )
            outs_prop = props.predict_pitcher_outs(
                player_id=1,
                player_name="Target Pitcher",
                mlb_game_pk="manual",
                pitcher_fip=args.pitcher_fip,
                opponent_wrc_plus=args.opp_wrc,
                pitcher_rest_days=args.rest_days,
            )
            print(
                f"Pitcher Prop Forecast (K%={args.pitcher_k * 100:.1f}%, "
                f"Opp K%={args.opp_k * 100:.1f}%):"
            )
            print(
                f"  Expected Strikeouts: {k_prop.expected_k:.2f} "
                f"(Projected K%: {k_prop.projected_k_pct * 100:.1f}%, "
                f"BF: {k_prop.expected_bf:.1f})"
            )
            print(
                f"  Expected Outs Recorded: {outs_prop.expected_outs:.1f} "
                f"({outs_prop.expected_ip:.1f} IP)"
            )
            print("  Strikeout Over/Under Probabilities:")
            for line, prob in sorted(k_prop.over_under_probs.items()):
                print(
                    f"    Over {line}: {prob * 100:.1f}% | Under {line}: {(1.0 - prob) * 100:.1f}%"
                )
            print("  Outs Recorded Over/Under Probabilities:")
            for line, prob in sorted(outs_prop.over_under_probs.items()):
                print(
                    f"    Over {line}: {prob * 100:.1f}% | Under {line}: {(1.0 - prob) * 100:.1f}%"
                )
        else:
            print("Please provide --game-pk or --pitcher-k. Use mlb props --help for options.")
    elif args.command == "research":
        import json as json_lib

        from mlb_baseball.research import LiteratureCatalog

        catalog = LiteratureCatalog()
        if args.citation:
            single_pub = catalog.get_by_citation_id(args.citation)
            found_pubs = [single_pub] if single_pub else []
        elif args.query:
            found_pubs = catalog.search(args.query)
        else:
            found_pubs = catalog.list_all()

        if args.json:
            res_out = [
                {
                    "citation_id": r_pub.citation_id,
                    "title": r_pub.title,
                    "authors": list(r_pub.authors),
                    "year": r_pub.year,
                    "publisher": r_pub.publisher_or_journal,
                    "domain": r_pub.domain.value,
                    "abstract": r_pub.abstract,
                    "key_formulas": list(r_pub.key_formulas),
                    "project_implementations": list(r_pub.project_implementations),
                }
                for r_pub in found_pubs
            ]
            print(json_lib.dumps(res_out, indent=2))
        else:
            print(
                f"\n=== SABERMETRIC RESEARCH & CITATION CATALOG "
                f"({len(found_pubs)} publications) ===\n"
            )
            for r_pub in found_pubs:
                print(f"[{r_pub.citation_id}] {r_pub.title} ({r_pub.year})")
                print(f"  Authors: {', '.join(r_pub.authors)} | Domain: {r_pub.domain.value}")
                print(f"  Abstract: {r_pub.abstract}")
                print("  Key Formulas:")
                for f_line in r_pub.key_formulas:
                    print(f"    • {f_line}")
                print(f"  Implemented In: {', '.join(r_pub.project_implementations)}\n")

    elif args.command == "calibrate":
        import json as json_lib

        from mlb_baseball.db import get_connection
        from mlb_baseball.model.calibration import HomeAdvantageCalibrator, evaluate_calibration

        hfa_cal = HomeAdvantageCalibrator()

        if args.prob is not None:
            adj = hfa_cal.adjust_home_win_prob(args.prob)
            if args.json:
                print(json_lib.dumps({"raw_prob": args.prob, "calibrated_prob": round(adj, 4)}))
            else:
                print("\n=== HOME FIELD ADVANTAGE RECALIBRATION ===")
                print(f"Raw Input Win Prob:        {args.prob * 100:.2f}%")
                print(f"Calibrated (True MLB HFA): {adj * 100:.2f}%\n")
        else:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT g.home_score > g.away_score, p.home_win_prob "
                        "FROM gold.prediction p "
                        "JOIN gold.game_feature f ON f.game_instance_key = p.game_instance_key "
                        "JOIN core.game g ON g.id = f.game_id "
                        "WHERE p.model_version = 'gbm-v2' AND g.home_score IS NOT NULL "
                        "LIMIT 5000"
                    )
                    rows = cur.fetchall()

            if not rows:
                print("No completed evaluated predictions found for calibration analysis.")
            else:
                y_true = [1 if r[0] else 0 for r in rows]
                y_prob = [float(r[1]) for r in rows]
                rep = evaluate_calibration(y_true, y_prob, n_bins=10)

                if args.json:
                    cal_out = {
                        "sample_size": rep.sample_size,
                        "expected_calibration_error": rep.expected_calibration_error,
                        "max_calibration_error": rep.max_calibration_error,
                        "brier_score": rep.brier_score,
                        "brier_skill_score": rep.brier_skill_score,
                        "bins": [
                            {
                                "bin_index": b.bin_index,
                                "min_prob": b.min_prob,
                                "max_prob": b.max_prob,
                                "mean_predicted_prob": b.mean_predicted_prob,
                                "empirical_win_rate": b.empirical_win_rate,
                                "sample_count": b.sample_count,
                                "calibration_error": b.calibration_error,
                            }
                            for b in rep.bins
                        ],
                    }
                    print(json_lib.dumps(cal_out, indent=2))
                else:
                    print(
                        f"\n=== PROBABILITY CALIBRATION & RELIABILITY DIAGRAM "
                        f"(N={rep.sample_size}) ==="
                    )
                    print(
                        f"Expected Calibration Error (ECE): "
                        f"{rep.expected_calibration_error * 100:.2f}%"
                    )
                    print(
                        f"Max Calibration Error (MCE):      {rep.max_calibration_error * 100:.2f}%"
                    )
                    print(
                        f"Brier Score:                      {rep.brier_score:.4f} "
                        f"(Skill: {rep.brier_skill_score * 100:.2f}%)\n"
                    )
                    b_hdr = (
                        f"{'Bin':<6} {'Range':<14} {'Mean Pred':<12} "
                        f"{'Empirical Win%':<16} {'Count':<8} {'Error':<8}"
                    )
                    print(b_hdr)
                    print("-" * len(b_hdr))
                    for b in rep.bins:
                        print(
                            f"{b.bin_index:<6} "
                            f"[{b.min_prob:.2f}, {b.max_prob:.2f})   "
                            f"{b.mean_predicted_prob * 100:>7.1f}%     "
                            f"{b.empirical_win_rate * 100:>10.1f}%       "
                            f"{b.sample_count:>5}   "
                            f"{b.calibration_error * 100:>6.2f}%"
                        )
                    print("")

    elif args.command == "backtest":
        import json as json_lib

        from mlb_baseball.model.backtest import WalkForwardBacktester
        from mlb_baseball.model.portfolio import KellyAllocator

        allocator = KellyAllocator(
            fraction=args.kelly_fraction,
            max_single_bet_pct=0.025,
            max_total_exposure_pct=0.150,
            min_edge_pct=args.min_edge,
        )
        tester = WalkForwardBacktester(allocator=allocator, min_edge_pct=args.min_edge)
        summary = tester.run_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            model_version=args.model,
            initial_bankroll=args.bankroll,
        )

        if args.json:
            bt_out = {
                "start_date": summary.start_date,
                "end_date": summary.end_date,
                "model_version": summary.model_version,
                "initial_bankroll_usd": summary.initial_bankroll_usd,
                "final_bankroll_usd": summary.final_bankroll_usd,
                "total_wagers": summary.total_wagers,
                "winning_wagers": summary.winning_wagers,
                "losing_wagers": summary.losing_wagers,
                "win_rate_pct": summary.win_rate_pct,
                "total_wagered_usd": summary.total_wagered_usd,
                "total_pnl_usd": summary.total_pnl_usd,
                "roi_pct": summary.roi_pct,
                "annualized_sharpe_ratio": summary.annualized_sharpe_ratio,
                "max_drawdown_pct": summary.max_drawdown_pct,
                "mean_clv_pct": summary.mean_clv_pct,
                "brier_score": summary.brier_score,
                "wager_history": [
                    {
                        "game_key": r.game_instance_key,
                        "date": r.game_date,
                        "matchup": r.matchup,
                        "model_prob": r.model_prob,
                        "market_prob": r.market_prob,
                        "decimal_odds": r.decimal_odds,
                        "wager_usd": r.wager_usd,
                        "won": r.won_bet,
                        "pnl_usd": r.pnl_usd,
                        "bankroll_after_usd": r.bankroll_after_usd,
                    }
                    for r in summary.wager_history
                ],
            }
            print(json_lib.dumps(bt_out, indent=2))
        else:
            print(f"\n{'=' * 80}")
            print(
                f"       HISTORICAL WALK-FORWARD BACKTEST SUMMARY ({summary.model_version.upper()})"
            )
            print(f"       Date Range: {summary.start_date} to {summary.end_date}")
            print(f"{'=' * 80}\n")
            print(f"Initial Bankroll:   ${summary.initial_bankroll_usd:,.2f}")
            print(f"Final Bankroll:     ${summary.final_bankroll_usd:,.2f}")
            print(
                f"Net PnL:            ${summary.total_pnl_usd:+,.2f} (ROI: {summary.roi_pct:+.2f}%)"
            )
            print(
                f"Total Wagers:       {summary.total_wagers} "
                f"({summary.winning_wagers}W - {summary.losing_wagers}L | "
                f"Win Rate: {summary.win_rate_pct:.1f}%)"
            )
            print(f"Total Wagered:      ${summary.total_wagered_usd:,.2f}")
            print(f"Annualized Sharpe:  {summary.annualized_sharpe_ratio:.2f}")
            print(f"Max Drawdown (MDD): {summary.max_drawdown_pct:.2f}%")
            print(f"Mean CLV Edge:      {summary.mean_clv_pct:+.2f}%")
            print(f"Brier Score:        {summary.brier_score:.4f}\n")

            if summary.wager_history:
                print("--- RECENT EXECUTED WAGERS ---")
                w_hdr = (
                    f"{'Date':<10} {'Matchup / Bet':<30} {'Model%':<8} "
                    f"{'Mkt%':<8} {'Odds':<6} {'Stake':<10} "
                    f"{'Result':<8} {'Bankroll':<12}"
                )
                print(w_hdr)
                print("-" * len(w_hdr))
                for w in summary.wager_history[-10:]:
                    res_str = (
                        f"WIN (+${w.pnl_usd:.2f})" if w.won_bet else f"LOSS (-${w.wager_usd:.2f})"
                    )
                    print(
                        f"{w.game_date:<10} "
                        f"{w.matchup:<30} "
                        f"{w.model_prob * 100:>6.1f}%  "
                        f"{w.market_prob * 100:>6.1f}%  "
                        f"{w.decimal_odds:>5.2f} "
                        f"${w.wager_usd:>8.2f} "
                        f"{res_str:<14} "
                        f"${w.bankroll_after_usd:>10.2f}"
                    )
                print("")

    elif args.command == "ros":
        import json as json_lib

        from mlb_baseball.model.ros import RestOfSeasonSimulator

        ros_sim = RestOfSeasonSimulator(random_seed=42)
        ros_report = ros_sim.simulate_ros(
            season=args.season,
            as_of_date=args.as_of,
            n_sims=args.sims,
        )

        if args.json:
            ros_out = {
                "season": ros_report.season,
                "as_of_date": ros_report.as_of_date,
                "simulations_count": ros_report.simulations_count,
                "projections": [
                    {
                        "team": ros_item.retro_team_id,
                        "league": ros_item.league,
                        "division": ros_item.division,
                        "current_record": f"{ros_item.current_wins}-{ros_item.current_losses}",
                        "proj_ros_wins": ros_item.proj_ros_wins,
                        "proj_total_wins_mean": ros_item.proj_total_wins_mean,
                        "proj_total_wins_p10": ros_item.proj_total_wins_p10,
                        "proj_total_wins_p90": ros_item.proj_total_wins_p90,
                        "division_title_prob": ros_item.division_title_prob,
                        "wild_card_prob": ros_item.wild_card_prob,
                        "make_playoffs_prob": ros_item.make_playoffs_prob,
                        "pennant_prob": ros_item.pennant_prob,
                        "world_series_prob": ros_item.world_series_prob,
                        "magic_number": ros_item.magic_number,
                    }
                    for ros_item in ros_report.team_projections
                ],
            }
            print(json_lib.dumps(ros_out, indent=2))
        else:
            print(f"\n{'=' * 88}")
            print(
                f"     REST-OF-SEASON (ROS) PROJECTIONS & PLAYOFF ODDS (SEASON {ros_report.season})"
            )
            print(
                f"     As Of: {ros_report.as_of_date} | "
                f"Monte Carlo Simulations: {ros_report.simulations_count:,}"
            )
            print(f"{'=' * 88}\n")

            current_div = ""
            for ros_item in ros_report.team_projections:
                if ros_item.division != current_div:
                    current_div = ros_item.division
                    print(f"--- {current_div.upper()} ---")
                    hdr = (
                        f"{'Team':<6} {'Record':<9} {'ROS W':<8} {'Proj W':<8} "
                        f"{'90% CI':<12} {'Div%':<8} {'WC%':<8} {'Playoffs%':<10} "
                        f"{'Pennant%':<10} {'WS%':<8} {'Magic#':<6}"
                    )
                    print(hdr)
                    print("-" * len(hdr))

                mn_str = str(ros_item.magic_number) if ros_item.magic_number is not None else "-"
                ci_str = f"[{ros_item.proj_total_wins_p10:.0f}-{ros_item.proj_total_wins_p90:.0f}]"
                rec_str = f"{ros_item.current_wins}-{ros_item.current_losses}"
                print(
                    f"{ros_item.retro_team_id:<6} "
                    f"{rec_str:<9} "
                    f"{ros_item.proj_ros_wins:>6.1f}   "
                    f"{ros_item.proj_total_wins_mean:>6.1f}   "
                    f"{ci_str:<12} "
                    f"{ros_item.division_title_prob * 100:>6.1f}% "
                    f"{ros_item.wild_card_prob * 100:>6.1f}% "
                    f"{ros_item.make_playoffs_prob * 100:>8.1f}%  "
                    f"{ros_item.pennant_prob * 100:>8.1f}%  "
                    f"{ros_item.world_series_prob * 100:>6.1f}% "
                    f"{mn_str:>5}"
                )
            print("")

    elif args.command == "export":
        from mlb_baseball.db import get_connection
        from mlb_baseball.export import export_backbone_bundle, export_bundle, export_relation

        if args.publish and not args.preset:
            export_parser.error("--publish requires --preset")
        if args.publish and not args.tag:
            export_parser.error("--publish requires --tag")
        if args.preset and args.zip:
            export_parser.error(
                "--zip is not supported with --preset (the HF publish step uploads the "
                "bundle directory as-is; a preset bundle is never zipped)"
            )

        if args.preset:
            with get_connection() as conn:
                out_dir = args.out or "backbone_bundle"
                result_path = export_backbone_bundle(conn, out_dir=out_dir)
            print(f"Exported {args.preset} preset bundle to {result_path}")

            if args.publish == "hf":
                from mlb_baseball.publish import publish_backbone_bundle

                publish_kwargs = {"tag": args.tag}
                if args.repo_id:
                    publish_kwargs["repo_id"] = args.repo_id
                commit = publish_backbone_bundle(result_path, **publish_kwargs)
                print(f"Published to Hugging Face (revision={args.tag}): {commit}")
        elif args.profile:
            with get_connection() as conn:
                out_dir = args.out or "export_bundle"
                result_path = export_bundle(
                    conn,
                    profile=args.profile,
                    out_dir=out_dir,
                    make_zip=args.zip,
                )
            print(f"Exported {args.profile} bundle to {result_path}")
        elif args.relation:
            with get_connection() as conn:
                result_path, count = export_relation(
                    conn,
                    relation=args.relation,
                    format=args.format,
                    out_path=args.out,
                    season=args.season,
                )
            print(f"Exported {count:,} rows to {result_path}")
        else:
            export_parser.error("must specify a relation, --profile, or --preset")

    elif args.command == "stack":
        import json as json_lib

        from mlb_baseball.db import get_connection
        from mlb_baseball.model import stack

        if args.train:
            with get_connection() as conn:
                stack_res = stack.train(conn)
            if args.json:
                print(json_lib.dumps(stack_res, indent=2))
            else:
                print(f"\n{'=' * 72}")
                print("     BAYESIAN CONVEX STACKING META-LEARNER (STACK-02)")
                print(f"{'=' * 72}\n")
                print(f"Model Version     : {stack_res['model_version']}")
                print(f"Train/Test Games: {stack_res['train_rows']} / {stack_res['test_rows']}")
                print(f"Test Log Loss     : {stack_res['test_log_loss']:.4f}")
                print(f"Test Brier Score  : {stack_res['test_brier']:.4f}")
                print(
                    f"Brier Skill Score : "
                    f"{stack_res['brier_skill_score'] * 100:+.2f}% vs best base model\n"
                )
                print("--- ENSEMBLE MODEL WEIGHTS ---")
                for m_name, w_val in stack_res["weights"].items():
                    bar = "█" * int(round(w_val * 30))
                    print(f"{m_name:<15} | {bar:<30} | {w_val * 100:>5.1f}%")
                print("")
        else:
            if not stack.MODEL_PATH.exists():
                print(f"No trained stack model found at {stack.MODEL_PATH}.")
                print("Run 'mlb stack --train' to train the ensemble meta-learner.")
            else:
                with open(stack.MODEL_PATH) as f:
                    saved = json_lib.load(f)
                if args.json:
                    print(json_lib.dumps(saved, indent=2))
                else:
                    print(f"\n{'=' * 72}")
                    print("     BAYESIAN CONVEX STACKING META-LEARNER (STACK-02)")
                    print(f"{'=' * 72}\n")
                    print(f"Model Version     : {saved.get('model_version', 'stack-v2')}")
                    print(
                        f"Train / Test Games: {saved.get('train_rows', '-')} / "
                        f"{saved.get('test_rows', '-')}"
                    )
                    print(f"Test Brier Score  : {saved.get('test_brier', '-'):.4f}")
                    print(
                        f"Brier Skill Score : "
                        f"{saved.get('brier_skill_score', 0.0) * 100:+.2f}% vs best base\n"
                    )
                    print("--- CONVEX SIMPLEX WEIGHTS ---")
                    for m_name, w_val in saved.get("weights", {}).items():
                        bar = "█" * int(round(w_val * 30))
                        print(f"{m_name:<15} | {bar:<30} | {w_val * 100:>5.1f}%")
                    print("")

    elif args.command == "drift":
        import json as json_lib

        from mlb_baseball.db import get_connection
        from mlb_baseball.model.drift import ModelDriftMonitor

        monitor = ModelDriftMonitor(
            window_size_games=args.window,
            step_size_games=args.step,
        )
        with get_connection() as conn:
            drift_report = monitor.evaluate_model_from_db(
                model_version=args.model,
                conn=conn,
            )

        if args.json:
            drift_out = {
                "model_version": drift_report.model_version,
                "total_evaluated_games": drift_report.total_evaluated_games,
                "overall_brier_score": drift_report.overall_brier_score,
                "overall_ece": drift_report.overall_ece,
                "current_status": drift_report.current_status.value,
                "alerts": drift_report.alerts,
                "windows": [
                    {
                        "window_index": w.window_index,
                        "start_date": w.start_date,
                        "end_date": w.end_date,
                        "sample_size": w.sample_size,
                        "brier_score": w.brier_score,
                        "log_loss_score": w.log_loss_score,
                        "expected_calibration_error": w.expected_calibration_error,
                        "platt_slope_w": w.platt_slope_w,
                        "hfa_intercept_b": w.hfa_intercept_b,
                        "brier_skill_score": w.brier_skill_score,
                        "severity": w.severity.value,
                        "warnings": w.warning_messages,
                    }
                    for w in drift_report.windows
                ],
            }
            print(json_lib.dumps(drift_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     MODEL CALIBRATION MONITOR ({drift_report.model_version.upper()})")
            print(
                f"     Games: {drift_report.total_evaluated_games:,} | "
                f"Overall ECE: {drift_report.overall_ece * 100:.1f}% | "
                f"Brier: {drift_report.overall_brier_score:.4f}"
            )
            print(f"     Current Status : [{drift_report.current_status.value}]")
            print(f"{'=' * 84}\n")

            if drift_report.alerts:
                for alert in drift_report.alerts:
                    print(f">> ALERT: {alert}")
                print("")

            if not drift_report.windows:
                print("No rolling windows could be formed with the specified game sample size.\n")
            else:
                hdr = (
                    f"{'Window':<8} {'Period':<23} {'Games':<7} "
                    f"{'Brier':<8} {'ECE%':<8} {'Slope α':<9} "
                    f"{'Intercept β':<12} {'Status':<10}"
                )
                print(hdr)
                print("-" * len(hdr))
                for w_item in drift_report.windows:
                    period = f"{w_item.start_date} -> {w_item.end_date}"
                    print(
                        f"#{w_item.window_index:<7} "
                        f"{period:<23} "
                        f"{w_item.sample_size:<7} "
                        f"{w_item.brier_score:<8.4f} "
                        f"{w_item.expected_calibration_error * 100:>5.1f}%  "
                        f"{w_item.platt_slope_w:>6.2f}   "
                        f"{w_item.hfa_intercept_b:>+8.2f}    "
                        f"[{w_item.severity.value}]"
                    )
                print("")

    elif args.command == "parlay":
        import json as json_lib

        from mlb_baseball.model.parlay import (
            CorrelatedParlayEvaluator,
            ParlayLeg,
            ParlayLegType,
            SyntheticGaussianCopulaSampler,
        )

        sampler = SyntheticGaussianCopulaSampler(
            exp_home_runs=4.8,
            exp_away_runs=3.8,
            exp_home_ks=6.8,
            exp_away_ks=5.2,
        )
        evaluator = CorrelatedParlayEvaluator(sampler, n_sims=args.sims)

        candidate_legs = [
            ParlayLeg(
                "l1",
                ParlayLegType.MONEYLINE_HOME,
                "Home Team Moneyline (Win)",
                individual_probability=0.58,
                decimal_odds=1.72,
            ),
            ParlayLeg(
                "l2",
                ParlayLegType.RUN_LINE_HOME,
                "Home Run Line -1.5",
                line=1.5,
                individual_probability=0.42,
                decimal_odds=2.38,
            ),
            ParlayLeg(
                "l3",
                ParlayLegType.TOTAL_UNDER,
                "Game Total Under 8.5",
                line=8.5,
                individual_probability=0.52,
                decimal_odds=1.92,
            ),
            ParlayLeg(
                "l4",
                ParlayLegType.TOTAL_OVER,
                "Game Total Over 8.5",
                line=8.5,
                individual_probability=0.48,
                decimal_odds=2.08,
            ),
            ParlayLeg(
                "l5",
                ParlayLegType.TEAM_TOTAL_AWAY_UNDER,
                "Away Team Total Under 3.5",
                line=3.5,
                individual_probability=0.54,
                decimal_odds=1.85,
            ),
            ParlayLeg(
                "l6",
                ParlayLegType.TEAM_TOTAL_HOME_OVER,
                "Home Team Total Over 4.5",
                line=4.5,
                individual_probability=0.50,
                decimal_odds=2.00,
            ),
            ParlayLeg(
                "l7",
                ParlayLegType.PITCHER_K_HOME_OVER,
                "Home Starter Over 6.5 Ks",
                line=6.5,
                individual_probability=0.55,
                decimal_odds=1.82,
            ),
            ParlayLeg(
                "l8",
                ParlayLegType.F5_MONEYLINE_HOME,
                "Home First-5 (F5) Moneyline",
                individual_probability=0.57,
                decimal_odds=1.75,
            ),
        ]

        best_parlays = evaluator.find_best_correlated_parlays(
            game_instance_key="sample_game",
            candidate_legs=candidate_legs,
            leg_count=args.legs,
            min_correlation_boost=args.min_boost,
        )

        if args.json:
            parlay_out = [
                {
                    "parlay_id": parlay_obj.parlay_id,
                    "leg_count": parlay_obj.leg_count,
                    "legs": [
                        {
                            "leg_id": leg.leg_id,
                            "type": leg.leg_type.value,
                            "description": leg.description,
                            "indiv_prob": leg.individual_probability,
                            "decimal_odds": leg.decimal_odds,
                        }
                        for leg in parlay_obj.legs
                    ],
                    "independent_prob": parlay_obj.independent_prob,
                    "joint_prob": parlay_obj.joint_prob,
                    "correlation_multiplier": parlay_obj.correlation_multiplier,
                    "fair_decimal_odds": parlay_obj.fair_decimal_odds,
                    "sportsbook_offered_odds": parlay_obj.sportsbook_offered_odds,
                    "expected_value_pct": parlay_obj.expected_value_pct,
                }
                for parlay_obj in best_parlays
            ]
            print(json_lib.dumps(parlay_out, indent=2))
        else:
            print(f"\n{'=' * 92}")
            print(f"     CORRELATED SGP COPULA OPTIMIZER ({args.legs}-Leg Combinations)")
            print(f"     Paths: {args.sims:,} | Min Boost: {args.min_boost:.2f}x")
            print(f"{'=' * 92}\n")

            if not best_parlays:
                print("No parlay combinations met the specified correlation boost threshold.\n")
            else:
                for idx, parlay_item in enumerate(best_parlays[:8]):
                    leg_descs = " + ".join([leg.description for leg in parlay_item.legs])
                    ev_str = (
                        f"{parlay_item.expected_value_pct * 100:+.1f}%"
                        if parlay_item.expected_value_pct is not None
                        else "N/A"
                    )
                    print(f"#{idx + 1:<2} | {leg_descs}")
                    print(
                        f"    Joint Prob: {parlay_item.joint_prob * 100:>5.1f}% "
                        f"(vs Indep: {parlay_item.independent_prob * 100:>5.1f}%) | "
                        f"Boost: {parlay_item.correlation_multiplier:>4.2f}x | "
                        f"Fair: {parlay_item.fair_decimal_odds:>5.2f} | "
                        f"Book: {parlay_item.sportsbook_offered_odds or 0.0:>5.2f} | "
                        f"EV: {ev_str}"
                    )
                    print("-" * 92)
                print("")

    elif args.command == "stuff":
        import json as json_lib

        from mlb_baseball.model.stuff import (
            PhysicalPitchRatingEngine,
            PitchPhysicsVector,
            PitchType,
        )

        pt_map = {
            "FF": PitchType.FOUR_SEAM,
            "SI": PitchType.SINKER,
            "FC": PitchType.CUTTER,
            "SL": PitchType.SLIDER,
            "ST": PitchType.SWEEPER,
            "CU": PitchType.CURVEBALL,
            "CH": PitchType.CHANGEUP,
            "FS": PitchType.SPLITTER,
            "KC": PitchType.KNUCKLE_CURVE,
        }
        pt = pt_map.get(args.pitch_type.upper(), PitchType.FOUR_SEAM)
        p_engine = PhysicalPitchRatingEngine()

        pitch_vec = PitchPhysicsVector(
            pitch_type=pt,
            release_speed_mph=args.velo,
            induced_vert_break_in=args.ivb,
            horizontal_break_in=args.hb,
            release_height_ft=6.0,
            release_side_ft=-1.8,
            release_extension_ft=6.3,
            plate_x_ft=0.2,
            plate_z_ft=2.8,
        )

        grade = p_engine.evaluate_pitch(pitch_vec, count=(0, 0))

        if args.json:
            stuff_out = {
                "pitch_type": grade.pitch_type.value,
                "velocity_mph": args.velo,
                "ivb_inches": args.ivb,
                "hb_inches": args.hb,
                "stuff_plus": grade.stuff_plus,
                "location_plus": grade.location_plus,
                "pitching_plus": grade.pitching_plus,
                "expected_whiff_rate": grade.expected_whiff_rate,
                "expected_run_value_per_100": grade.expected_run_value_per_100,
            }
            print(json_lib.dumps(stuff_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCH TRAJECTORY & PHYSICAL ARSENAL RATING ({grade.pitch_type.value})")
            print(
                f'     Velocity: {args.velo:.1f} mph | IVB: {args.ivb:+.1f}" | HB: {args.hb:+.1f}"'
            )
            print(f"{'=' * 84}\n")
            print(f"  • Stuff+       : {grade.stuff_plus:>5.1f}  (100 = Avg, >115 = Elite)")
            print(f"  • Location+    : {grade.location_plus:>5.1f}")
            print(f"  • Pitching+    : {grade.pitching_plus:>5.1f}  (Composite Physical + Command)")
            print(f"  • Exp Whiff%   : {grade.expected_whiff_rate * 100:>5.1f}%")
            print(f"  • Exp RV / 100 : {grade.expected_run_value_per_100:>+5.2f} runs\n")

    elif args.command == "heatmap":
        import json as json_lib

        from mlb_baseball.model.heatmap import BattedBallBallisticsEngine

        ballistics = BattedBallBallisticsEngine()
        hit = ballistics.compute_field_coordinates(
            hit_id="cli_hit",
            exit_velocity_mph=args.ev,
            launch_angle_deg=args.la,
            spray_angle_deg=args.spray,
        )

        if args.json:
            heat_out = {
                "exit_velocity_mph": hit.exit_velocity_mph,
                "launch_angle_deg": hit.launch_angle_deg,
                "spray_angle_deg": hit.spray_angle_deg,
                "distance_feet": hit.distance_feet,
                "field_x_ft": hit.field_x_ft,
                "field_y_ft": hit.field_y_ft,
                "is_barrel": hit.is_barrel,
                "is_hard_hit": hit.is_hard_hit,
            }
            print(json_lib.dumps(heat_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print("     BATTED BALL BALLISTIC SPATIAL TRAJECTORY")
            print(f"     EV: {args.ev:.1f} mph | LA: {args.la:+.1f}° | Spray: {args.spray:+.1f}°")
            print(f"{'=' * 84}\n")
            print(f"  • Projected Distance : {hit.distance_feet:>5.1f} ft")
            print(
                f"  • Landing Field (X,Y): ({hit.field_x_ft:>+5.1f} ft, {hit.field_y_ft:>5.1f} ft)"
            )
            print(f"  • Statcast Barrel    : [{'YES' if hit.is_barrel else 'NO'}]")
            print(f"  • Hard Hit (>=95mph) : [{'YES' if hit.is_hard_hit else 'NO'}]\n")

    elif args.command == "neural":
        import json as json_lib

        import numpy as np

        from mlb_baseball.model.neural import (
            HierarchicalTreeResidualCombiner,
            NeuralEntityIndices,
        )

        combiner = HierarchicalTreeResidualCombiner(
            continuous_dim=5,
            pitcher_vocab_size=100,
            team_vocab_size=32,
            venue_vocab_size=30,
            embedding_dim=8,
        )

        cont = np.array([[0.2, -0.4, 0.8, 0.1, -0.3]])
        entities = [NeuralEntityIndices(15, 25, 5, 12, 8)]
        n_res = combiner.forward(cont, entities, [args.tree_prob], game_keys=["sample_game"])[0]

        if args.json:
            neural_out = {
                "game_key": n_res.game_key,
                "tree_prior_prob": n_res.tree_prior_prob,
                "neural_residual_delta": n_res.neural_residual_delta,
                "composite_win_prob": n_res.composite_win_prob,
                "embedding_norms": n_res.embedding_norms,
            }
            print(json_lib.dumps(neural_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print("     HIERARCHICAL NEURAL + TREE RESIDUAL COMBINER")
            print(
                f"     Tree Baseline: {n_res.tree_prior_prob * 100:.1f}% | "
                f"Neural Delta: {n_res.neural_residual_delta:+.3f}"
            )
            print(f"{'=' * 84}\n")
            print(f"  • Tree Prior Prob    : {n_res.tree_prior_prob * 100:>5.1f}%")
            print(f"  • Neural Residual (Δ): {n_res.neural_residual_delta:>+5.3f} log-odds")
            print(f"  • Composite Win Prob : {n_res.composite_win_prob * 100:>5.1f}%")
            hnorm = n_res.embedding_norms.get("home_starter_norm", 0.0)
            anorm = n_res.embedding_norms.get("away_starter_norm", 0.0)
            print(f"  • Starter Norm (H)   : {hnorm:.2f}")
            print(f"  • Starter Norm (A)   : {anorm:.2f}\n")

    elif args.command == "pipeline":
        import json as json_lib

        from mlb_baseball.pipeline import MasterDailyPipeline

        pipe = MasterDailyPipeline(run_preflight_doctor=not args.skip_doctor)
        pipe_report = pipe.execute_daily_cycle(
            target_date=args.date,
            n_sims=args.sims,
            bankroll_usd=args.bankroll,
        )

        if args.json:
            pipe_out = {
                "run_id": pipe_report.run_id,
                "target_date": pipe_report.target_date,
                "overall_success": pipe_report.overall_success,
                "total_duration_seconds": pipe_report.total_duration_seconds,
                "alerts": pipe_report.alerts,
                "phases": [
                    {
                        "phase_name": p.phase_name,
                        "status": p.status,
                        "duration_seconds": p.duration_seconds,
                        "summary": p.summary,
                        "metrics": p.metrics,
                    }
                    for p in pipe_report.phases
                ],
            }
            print(json_lib.dumps(pipe_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     MASTER END-TO-END QUANTITATIVE DAILY PIPELINE ({pipe_report.target_date})")
            print(
                f"     Run: {pipe_report.run_id} | Time: {pipe_report.total_duration_seconds:.2f}s"
            )
            status_tag = "SUCCESS" if pipe_report.overall_success else "FAILED"
            print(f"     Overall Status: [{status_tag}]")
            print(f"{'=' * 84}\n")

            if pipe_report.alerts:
                for a in pipe_report.alerts:
                    print(f">> ALERT: {a}")
                print("")

            for ph_res in pipe_report.phases:
                print(
                    f"[{ph_res.status:^7}] {ph_res.phase_name:<34} "
                    f"({ph_res.duration_seconds:>5.2f}s) | {ph_res.summary}"
                )
            print("")

    elif args.command == "visual":
        import json as json_lib

        from mlb_baseball.model.heatmap import BattedBallBallisticsEngine, StrikeZoneKDEMonitor
        from mlb_baseball.visual import (
            DiamondSprayChartRenderer,
            StrikeZoneHeatmapRenderer,
            WinExpectancyGraphRenderer,
        )

        if args.type == "strikezone":
            sz_r = StrikeZoneHeatmapRenderer()
            kde_m = StrikeZoneKDEMonitor()
            grid_res = kde_m.compute_density_grid([0.1, 0.3, -0.2], [2.5, 3.1, 2.0])
            v_chart = sz_r.render(grid_res, title="MLB Strike Zone Density")
        elif args.type == "we":
            we_r = WinExpectancyGraphRenderer()
            v_chart = we_r.render(
                [(0, 0.5, 1.0), (1, 0.65, 2.0), (2, 0.95, 3.5)], title="Live WE Worm"
            )
        else:
            sp_r = DiamondSprayChartRenderer()
            ball_eng = BattedBallBallisticsEngine()
            hits_sample = [ball_eng.compute_field_coordinates("h1", 104.0, 27.0, 0.0)]
            v_chart = sp_r.render(hits_sample, title="MLB Diamond Spray Chart")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f_out:
                f_out.write(v_chart.svg_content)

        if args.json:
            v_out = {
                "chart_type": v_chart.chart_type.value,
                "title": v_chart.title,
                "width_px": v_chart.width_px,
                "height_px": v_chart.height_px,
                "svg_bytes": len(v_chart.svg_content),
            }
            print(json_lib.dumps(v_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     VECTOR CHART GENERATION ({v_chart.chart_type.value.upper()})")
            print(f"     Title: {v_chart.title} | Size: {v_chart.width_px}x{v_chart.height_px}px")
            print(f"{'=' * 84}\n")
            print(f"  • SVG Markup Size : {len(v_chart.svg_content):,} bytes")
            if args.output:
                print(f"  • Exported to     : {args.output}")
            print("")

    elif args.command == "hedge":
        import json as json_lib

        from mlb_baseball.model.hedge import HedgeStrategy, LiveHedgingEngine

        h_engine = LiveHedgingEngine()
        h_plan = h_engine.calculate_hedge(
            initial_stake=args.stake,
            initial_odds=args.initial_odds,
            hedge_odds=args.hedge_odds,
            strategy=HedgeStrategy.EQUAL_PROFIT,
        )

        if args.json:
            h_out = {
                "initial_stake_usd": h_plan.initial_stake_usd,
                "initial_odds": h_plan.initial_decimal_odds,
                "hedge_odds": h_plan.hedge_decimal_odds,
                "recommended_hedge_stake_usd": h_plan.recommended_hedge_stake_usd,
                "total_staked_usd": h_plan.total_capital_committed_usd,
                "net_profit_if_initial_wins": h_plan.net_profit_if_initial_wins_usd,
                "net_profit_if_hedge_wins": h_plan.net_profit_if_hedge_wins_usd,
                "is_guaranteed_profit": h_plan.is_arbitrage_guaranteed_profit,
                "guaranteed_profit_margin_pct": h_plan.guaranteed_profit_margin_pct,
            }
            print(json_lib.dumps(h_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print("     LIVE IN-GAME HEDGING & ARBITRAGE CALCULATOR")
            print(
                f"  Init: ${args.stake:.0f}@{args.initial_odds:.2f} | Hedge: {args.hedge_odds:.2f}"
            )
            print(f"{'=' * 84}\n")
            print(f"  • Recommended Hedge Stake : ${h_plan.recommended_hedge_stake_usd:.2f}")
            print(f"  • Total Capital Committed : ${h_plan.total_capital_committed_usd:.2f}")
            print(f"  • Profit if Initial Wins  : ${h_plan.net_profit_if_initial_wins_usd:+.2f}")
            print(f"  • Profit if Hedge Wins    : ${h_plan.net_profit_if_hedge_wins_usd:+.2f}")
            arb_tag = "YES (LOCKED-IN GAIN)" if h_plan.is_arbitrage_guaranteed_profit else "NO"
            print(f"  • Guaranteed Arbitrage    : [{arb_tag}]")
            if h_plan.is_arbitrage_guaranteed_profit:
                print(
                    f"  • Profit Margin           : {h_plan.guaranteed_profit_margin_pct:+.1f}%\n"
                )

    elif args.command == "zone-isometric":
        from mlb_baseball.visual import (
            IsometricZonePitch,
            PitcherZoneIsometricProfile,
            ZoneIsometricChartRenderer,
        )

        z_iso_renderer = ZoneIsometricChartRenderer()
        iso_p = [
            IsometricZonePitch("FF", 3.0, 32.0, 0.4, 98.5, "#00d2be"),
            IsometricZonePitch("SL", -4.0, 22.0, 1.1, 88.2, "#f59e0b"),
        ]
        z_iso_prof = PitcherZoneIsometricProfile(args.title, args.pitcher, iso_p)
        chart = z_iso_renderer.render(z_iso_prof)
        print(f"Generated Vector SVG 3D Isometric Strike Zone ({len(chart.svg_content)} bytes)")

    elif args.command == "spray-heatmap":
        from mlb_baseball.visual import (
            BatterSprayHeatmapProfile,
            SprayHeatmapChartRenderer,
            SprayHeatmapContact,
        )

        sh_renderer = SprayHeatmapChartRenderer()
        contacts = [
            SprayHeatmapContact(-25.0, 108.0, 28.0, "hr", "#ef4444"),
            SprayHeatmapContact(5.0, 95.0, 12.0, "single", "#22c55e"),
            SprayHeatmapContact(-10.0, 102.0, 20.0, "double", "#eab308"),
        ]
        sh_prof = BatterSprayHeatmapProfile(args.title, args.batter, contacts, args.hand)
        chart = sh_renderer.render(sh_prof)
        print(f"Generated Vector SVG Spray Chart Heatmap ({len(chart.svg_content)} bytes)")

    elif args.command == "tunnel-decision":
        from mlb_baseball.visual import (
            PitcherTunnelDecisionProfile,
            TunnelDecisionChartRenderer,
            TunnelTrajectoryPitch,
        )

        t_dec_renderer = TunnelDecisionChartRenderer()
        p1 = TunnelTrajectoryPitch("FF", 99.2, 2.0, 36.0, "#00d2be")
        p2 = TunnelTrajectoryPitch("SPL", 89.0, 6.0, 16.0, "#f59e0b")
        t_dec_prof = PitcherTunnelDecisionProfile(args.title, args.pitcher, p1, p2, 1.8, 18.2)
        chart = t_dec_renderer.render(t_dec_prof)
        print(f"Generated Vector SVG Tunnel Decision Separation ({len(chart.svg_content)} bytes)")

    elif args.command == "polar-compass":
        from mlb_baseball.visual import (
            PitcherPolarCompassProfile,
            PitchPolarCompassNode,
            PolarCompassPlotRenderer,
        )

        p_compass_renderer = PolarCompassPlotRenderer()
        p_compass_pitches = [
            PitchPolarCompassNode("FF", 18.2, 8.4, "1:15", 98.4, 96.0, "#00d2be"),
            PitchPolarCompassNode("SL", 2.1, -14.5, "9:30", 87.2, 42.0, "#f59e0b"),
            PitchPolarCompassNode("CH", -1.2, 16.0, "2:45", 89.0, 78.0, "#3b82f6"),
        ]
        p_compass_prof = PitcherPolarCompassProfile(args.title, args.pitcher, p_compass_pitches)
        chart = p_compass_renderer.render(p_compass_prof)
        print(f"Generated Vector SVG Pitch Polar Compass ({len(chart.svg_content)} bytes)")

    elif args.command == "barrel-grid":
        from mlb_baseball.visual import (
            BarrelGridPlotRenderer,
            BatterBarrelGridProfile,
            StatcastBattedBallEvent,
        )

        b_grid_renderer = BarrelGridPlotRenderer()
        b_grid_events = [
            StatcastBattedBallEvent(112.0, 28.0, "barrel", "home_run"),
            StatcastBattedBallEvent(95.0, 16.0, "solid_contact", "double"),
            StatcastBattedBallEvent(82.0, 12.0, "flare_burner", "single"),
        ]
        b_grid_prof = BatterBarrelGridProfile(args.title, args.batter, b_grid_events)
        chart = b_grid_renderer.render(b_grid_prof)
        print(f"Generated Vector SVG Statcast Barrel Grid ({len(chart.svg_content)} bytes)")

    elif args.command == "flow-mix":
        from mlb_baseball.visual import (
            CountPitchMixNode,
            CountUsageFlowChartRenderer,
            PitcherCountFlowProfile,
        )

        count_mix_renderer = CountUsageFlowChartRenderer()
        even_mix = [
            CountPitchMixNode("FF", 50.0, "#00d2be"),
            CountPitchMixNode("SL", 50.0, "#f59e0b"),
        ]
        ahead_mix = [
            CountPitchMixNode("FF", 25.0, "#00d2be"),
            CountPitchMixNode("SL", 75.0, "#f59e0b"),
        ]
        behind_mix = [
            CountPitchMixNode("FF", 80.0, "#00d2be"),
            CountPitchMixNode("SL", 20.0, "#f59e0b"),
        ]
        count_mix_prof = PitcherCountFlowProfile(
            args.title, args.pitcher, even_mix, ahead_mix, behind_mix
        )
        chart = count_mix_renderer.render(count_mix_prof)
        print(f"Generated Vector SVG Count Transition Flow ({len(chart.svg_content)} bytes)")

    elif args.command == "tunnel-box":
        from mlb_baseball.visual import (
            PitcherTunnelBoxProfile,
            PitchTunnelPoint,
            TunnelBoxChartRenderer,
        )

        tb_renderer = TunnelBoxChartRenderer()
        tb_pitches = [
            PitchTunnelPoint("FF", -2.15, 5.85, 1.2, 34.0, "#00d2be"),
            PitchTunnelPoint("SL", -2.18, 5.80, 2.0, 32.5, "#f59e0b"),
        ]
        tb_prof = PitcherTunnelBoxProfile(args.title, args.pitcher, tb_pitches)
        chart = tb_renderer.render(tb_prof)
        print(f"Generated Vector SVG Release Window & Tunnel Box ({len(chart.svg_content)} bytes)")

    elif args.command == "la-ev-contour":
        from mlb_baseball.visual import (
            BattedBallContactEvent,
            BatterLaEvContourProfile,
            LaEvContourHeatmapRenderer,
        )

        la_renderer = LaEvContourHeatmapRenderer()
        la_events = [
            BattedBallContactEvent(108.0, 28.0, "home_run", 425.0),
            BattedBallContactEvent(96.0, 14.0, "single", 260.0),
            BattedBallContactEvent(74.0, -12.0, "groundout", 120.0),
        ]
        la_prof = BatterLaEvContourProfile(args.title, args.batter, la_events)
        chart = la_renderer.render(la_prof)
        print(f"Generated Vector SVG LA vs EV Heatmap ({len(chart.svg_content)} bytes)")

    elif args.command == "spin-polar":
        from mlb_baseball.visual import (
            PitcherSpinPolarClockProfile,
            PolarSpinPitchVector,
            SpinPolarClockRenderer,
        )

        sp_pol_renderer = SpinPolarClockRenderer()
        sp_pol_pitches = [
            PolarSpinPitchVector("FF", 1, 15, 96.0, 2480.0, "#00d2be"),
            PolarSpinPitchVector("SL", 8, 30, 28.0, 2400.0, "#f59e0b"),
        ]
        sp_pol_prof = PitcherSpinPolarClockProfile(args.title, args.pitcher, sp_pol_pitches)
        chart = sp_pol_renderer.render(sp_pol_prof)
        print(f"Generated Vector SVG Spin Polar Clock Chart ({len(chart.svg_content)} bytes)")

    elif args.command == "spray-iso":
        from mlb_baseball.visual import (
            BattedBallLandingPoint,
            BatterSprayIsochroneProfile,
            SprayIsochroneChartRenderer,
        )

        sp_renderer = SprayIsochroneChartRenderer()
        sp_points = [
            BattedBallLandingPoint(-80.0, 320.0, 104.0, 26.0, 360.0, "home_run"),
            BattedBallLandingPoint(60.0, 240.0, 88.0, 14.0, 250.0, "single"),
        ]
        sp_prof = BatterSprayIsochroneProfile(args.title, args.batter, sp_points)
        chart = sp_renderer.render(sp_prof)
        print(f"Generated Vector SVG Spray Isochrone Chart ({len(chart.svg_content)} bytes)")

    elif args.command == "break-diamond":
        from mlb_baseball.visual import (
            BreakDiamondPlotRenderer,
            PitchArsenalBreakProfile,
            PitchBreakVector,
        )

        bd_renderer = BreakDiamondPlotRenderer()
        bd_pitches = [
            PitchBreakVector("4-Seam", 10.0, 18.0, 98.0, "#ef4444"),
            PitchBreakVector("Sweeper", -14.0, -1.0, 84.0, "#3b82f6"),
            PitchBreakVector("Changeup", 15.0, 6.0, 89.0, "#10b981"),
        ]
        bd_prof = PitchArsenalBreakProfile(args.title, args.pitcher, bd_pitches)
        chart = bd_renderer.render(bd_prof)
        print(f"Generated Vector SVG Pitch Break Diamond Chart ({len(chart.svg_content)} bytes)")

    elif args.command == "attack-9x9":
        from mlb_baseball.visual import (
            AttackZone9x9Cell,
            AttackZone9x9GridRenderer,
            BatterAttackZone9x9Profile,
        )

        grid_renderer = AttackZone9x9GridRenderer()
        grid_cells = [
            AttackZone9x9Cell(r, c_idx, 45.0, 0.340, 18.0) for r in range(9) for c_idx in range(9)
        ]
        grid_prof = BatterAttackZone9x9Profile(args.title, args.batter, args.mode, grid_cells)
        chart = grid_renderer.render(grid_prof)
        print(f"Generated Vector SVG 9x9 Attack Zone Grid ({len(chart.svg_content)} bytes)")

    elif args.command == "release-box":
        from mlb_baseball.visual import (
            PitcherReleaseWindowProfile,
            PitchReleasePoint,
            ReleaseWindowBoxRenderer,
        )

        box_renderer = ReleaseWindowBoxRenderer()
        box_pitches = [
            PitchReleasePoint("FF", -2.15, 5.85, 1.4, 1.2, "#3b82f6"),
            PitchReleasePoint("SL", -2.20, 5.80, 1.5, 1.3, "#ec4899"),
            PitchReleasePoint("CH", -2.10, 5.75, 1.6, 1.4, "#a855f7"),
            PitchReleasePoint("CB", -2.05, 5.90, 1.8, 1.5, "#eab308"),
        ]
        box_prof = PitcherReleaseWindowProfile(args.title, args.pitcher, box_pitches)
        chart = box_renderer.render(box_prof)
        print(f"Generated Vector SVG Release Window Box Plot ({len(chart.svg_content)} bytes)")

    elif args.command == "spray-rose":
        from mlb_baseball.visual import (
            BatterSprayElevationRoseProfile,
            SprayElevationRoseRenderer,
            SpraySectorData,
        )

        rose_renderer = SprayElevationRoseRenderer()
        rose_sectors = [
            SpraySectorData("Dead Pull", -36.0, 35.0, 25.0, 35.0, 5.0, 94.0),
            SpraySectorData("Pull", -18.0, 25.0, 40.0, 30.0, 5.0, 98.5),
            SpraySectorData("Center", 0.0, 20.0, 50.0, 25.0, 5.0, 102.0),
            SpraySectorData("Oppo", 18.0, 30.0, 40.0, 25.0, 5.0, 92.0),
            SpraySectorData("Dead Oppo", 36.0, 40.0, 30.0, 25.0, 5.0, 88.0),
        ]
        rose_prof = BatterSprayElevationRoseProfile(args.title, args.batter, rose_sectors)
        chart = rose_renderer.render(rose_prof)
        print(
            f"Generated Vector SVG Batter Spray & Elevation Rose ({len(chart.svg_content)} bytes)"
        )

    elif args.command == "separation-plot":
        from mlb_baseball.visual import (
            PitchSeparationArsenalProfile,
            PitchSeparationPoint,
            SeparationDiamondPlotRenderer,
        )

        sep_renderer = SeparationDiamondPlotRenderer()
        sep_pitches = [
            PitchSeparationPoint("FF", "4-Seam Fastball", 97.5, 18.2, -6.5, "#00d2be"),
            PitchSeparationPoint("SL", "Slider", 88.0, 2.5, 5.0, "#f59e0b"),
            PitchSeparationPoint("CH", "Changeup", 86.5, 4.0, 14.5, "#a855f7"),
            PitchSeparationPoint("CU", "Curveball", 79.0, -11.0, 8.0, "#3b82f6"),
        ]
        sep_prof = PitchSeparationArsenalProfile(args.title, args.pitcher, sep_pitches)
        chart = sep_renderer.render(sep_prof)
        print(f"Generated Vector SVG Arsenal Separation Plot ({len(chart.svg_content)} bytes)")

    elif args.command == "spin-clock":
        from mlb_baseball.visual import (
            PitcherSpinClockArsenalProfile,
            PitchSpinClockSpec,
            SpinAxisClockVisualizerRenderer,
        )

        clk_renderer = SpinAxisClockVisualizerRenderer()
        clk_pitches = [
            PitchSpinClockSpec("FF", "4-Seam Fastball", 1, 15, 98.0, "#00d2be"),
            PitchSpinClockSpec("SL", "Sweeper", 9, 0, 35.0, "#f59e0b"),
            PitchSpinClockSpec("CH", "Changeup", 10, 45, 88.0, "#a855f7"),
            PitchSpinClockSpec("CU", "Curveball", 6, 30, 92.0, "#3b82f6"),
        ]
        clk_prof = PitcherSpinClockArsenalProfile(args.title, args.pitcher, clk_pitches)
        chart = clk_renderer.render(clk_prof)
        print(f"Generated Vector SVG 12-Hour Spin Clock Dial ({len(chart.svg_content)} bytes)")

    elif args.command == "arm-slot":
        import json as json_lib

        from mlb_baseball.model.arm_slot import (
            PitcherArmSlotEngine,
            PitcherArmSlotMetrics,
        )

        asl_eng = PitcherArmSlotEngine()
        asl_m = PitcherArmSlotMetrics(
            "p1",
            "Target Pitcher",
            release_x_ft=args.rel_x,
            release_z_ft=args.rel_z,
            pitcher_height_in=args.height,
            release_dispersion_std_in=args.disp,
        )
        asl_res = asl_eng.evaluate_arm_slot(asl_m)

        if args.json:
            asl_out = {
                "arm_slot_angle_deg": asl_res.arm_slot_angle_deg,
                "tier": asl_res.arm_slot_tier,
                "consistency_score": asl_res.release_consistency_score,
                "is_elite_tunnel": asl_res.is_elite_release_tunnel,
            }
            print(json_lib.dumps(asl_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCHER ARM SLOT & RELEASE CONSISTENCY [{asl_res.arm_slot_tier}]")
            hdr_as = (
                f"     Arm Slot Angle: {asl_res.arm_slot_angle_deg:.1f}° "
                f"| Release Consistency: {asl_res.release_consistency_score:.1f}/100 "
                f"| Tier: {asl_res.arm_slot_tier}"
            )
            print(hdr_as)
            print(f"{'=' * 84}\n")
            print(f"  • Arm Slot Classification : {asl_res.arm_slot_tier}")
            tunnel_txt = "YES" if asl_res.is_elite_release_tunnel else "NO"
            print(f"  • Elite Release Tunnel    : {tunnel_txt}")

    elif args.command == "zone-surface":
        from mlb_baseball.visual import (
            ZoneGridValue,
            ZoneSurfaceContourProfile,
            ZoneSurfaceContourRenderer,
        )

        zs_renderer = ZoneSurfaceContourRenderer()
        zs_cells = [
            ZoneGridValue(r, c, round(0.20 + (4 - r) * 0.15 + (2 - abs(c - 2)) * 0.10, 2))
            for r in range(5)
            for c in range(5)
        ]
        zs_prof = ZoneSurfaceContourProfile(args.title, args.batter, args.metric, zs_cells)
        chart = zs_renderer.render(zs_prof)
        print(f"Generated Vector SVG 5x5 Strike Zone Surface ({len(chart.svg_content)} bytes)")

    elif args.command == "flight-3d":
        from mlb_baseball.visual import (
            PitchTrajectory3DSpec,
            PitchTrajectory3DVisualizerRenderer,
            PitchTunnel3DProfile,
        )

        f3d_renderer = PitchTrajectory3DVisualizerRenderer()
        f3d_pitches = [
            PitchTrajectory3DSpec(
                "FF", "4-Seam Fastball", -2.2, 5.8, 0.2, 3.2, 8.0, 18.0, "#00d2be"
            ),
            PitchTrajectory3DSpec("SL", "Sweeper", -2.4, 5.6, 0.8, 2.0, -8.0, 2.0, "#f59e0b"),
            PitchTrajectory3DSpec("CH", "Changeup", -2.1, 5.7, -0.4, 1.8, 14.0, 6.0, "#a855f7"),
        ]
        f3d_prof = PitchTunnel3DProfile(args.title, args.pitcher, f3d_pitches)
        chart = f3d_renderer.render(f3d_prof)
        print(f"Generated Vector SVG 3D Isometric Pitch Flight ({len(chart.svg_content)} bytes)")

    elif args.command == "wpa-replay":
        from mlb_baseball.visual import (
            GameWPAReplayProfile,
            WinProbabilityReplayRenderer,
            WinProbabilityReplayStep,
        )

        replay_renderer = WinProbabilityReplayRenderer()
        wpa_replay_steps = [
            WinProbabilityReplayStep(0, 1, True, 0.50, "Pregame", 0.0),
            WinProbabilityReplayStep(1, 3, False, 0.65, "2-Run Double", 0.15, True),
            WinProbabilityReplayStep(2, 7, True, 0.35, "3-Run HR", -0.30, True),
            WinProbabilityReplayStep(3, 9, False, 0.95, "Walkoff Grand Slam", 0.60, True),
        ]
        wpa_game_prof = GameWPAReplayProfile(
            args.title,
            args.home,
            args.away,
            "6-3 Final",
            wpa_replay_steps,
        )
        chart = replay_renderer.render(wpa_game_prof)
        print(f"Generated Vector SVG Game WPA Replay Flow ({len(chart.svg_content)} bytes)")

    elif args.command == "babip":
        import json as json_lib

        from mlb_baseball.model.babip import (
            BABIPRegressionEngine,
            BatterBABIPInputs,
        )

        babip_eng = BABIPRegressionEngine()
        babip_m = BatterBABIPInputs(
            "b1",
            "Target Hitter",
            actual_babip=args.actual,
            ld_pct=args.ld,
            hard_hit_pct=args.hard_hit,
            sprint_speed_fps=args.speed,
        )
        babip_res = babip_eng.evaluate_babip(babip_m)

        if args.json:
            babip_out = {
                "actual_babip": babip_res.actual_babip,
                "expected_xbabip": babip_res.expected_xbabip,
                "luck_delta": babip_res.babip_luck_delta,
                "tier": babip_res.regression_tier,
                "is_buy_low": babip_res.is_buy_low_candidate,
            }
            print(json_lib.dumps(babip_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BABIP EXPECTED LUCK SCANNER [{babip_res.regression_tier}]")
            hdr_ba = (
                f"     Actual BABIP: {babip_res.actual_babip:.3f} "
                f"| Expected xBABIP: {babip_res.expected_xbabip:.3f} "
                f"| Luck Delta: {babip_res.babip_luck_delta:>+5.3f}"
            )
            print(hdr_ba)
            print(f"{'=' * 84}\n")
            print(f"  • Regression Tier    : {babip_res.regression_tier}")
            print(f"  • Buy-Low Candidate  : {'YES' if babip_res.is_buy_low_candidate else 'NO'}\n")

    elif args.command == "matchup-card":
        from mlb_baseball.visual import (
            MatchupCardProfile,
            MatchupComparisonCardRenderer,
            MatchupMetricComparison,
        )

        card_renderer = MatchupComparisonCardRenderer()
        m_comps = [
            MatchupMetricComparison("wOBA", 0.90, 0.60, ".410", ".305"),
            MatchupMetricComparison("Hard-Hit%", 0.85, 0.45, "52.0%", "36.0%"),
            MatchupMetricComparison("K%", 0.30, 0.80, "18.0%", "32.0%"),
            MatchupMetricComparison("Whiff%", 0.35, 0.75, "22.0%", "34.0%"),
        ]
        card_prof = MatchupCardProfile(
            f"{args.batter} vs {args.pitcher} Scouting Card",
            args.batter,
            args.pitcher,
            "BATTER_ADVANTAGE",
            m_comps,
        )
        chart = card_renderer.render(card_prof)
        print(f"Generated Vector SVG Matchup Scouting Card ({len(chart.svg_content)} bytes)")

    elif args.command == "hexbin":
        from mlb_baseball.visual import (
            HexbinPitchObservation,
            SpatialHexbinProfile,
            SpatialHexbinVisualizerRenderer,
        )

        hex_renderer = SpatialHexbinVisualizerRenderer()
        hex_pitches = [
            HexbinPitchObservation(0.1, 2.6, "FF", True),
            HexbinPitchObservation(-0.2, 2.2, "FF", True),
            HexbinPitchObservation(0.4, 3.1, "SL", True),
            HexbinPitchObservation(-0.7, 1.6, "CH", False),
        ]
        h_prof = SpatialHexbinProfile(args.title, "Shohei Ohtani", "Pitcher", hex_pitches)
        chart = hex_renderer.render(h_prof)
        print(f"Generated Vector SVG Hexbin Strike Zone Map ({len(chart.svg_content)} bytes)")

    elif args.command == "re24-heatmap":
        from mlb_baseball.visual import (
            BaseOutRunExpectancyGrid,
            RunExpectancyHeatmapRenderer,
        )

        re24_renderer = RunExpectancyHeatmapRenderer()
        grid = BaseOutRunExpectancyGrid(args.title)
        chart = re24_renderer.render(grid)
        print(f"Generated Vector SVG RE24 Matrix Heatmap ({len(chart.svg_content)} bytes)")

    elif args.command == "score-flow":
        from mlb_baseball.visual import (
            GameScoreFlowProfile,
            InningScoreFlowRenderer,
            InningScoreStep,
        )

        flow_renderer = InningScoreFlowRenderer()
        steps = [
            InningScoreStep(1, 0, 1, 0, 1),
            InningScoreStep(2, 0, 0, 0, 1),
            InningScoreStep(3, 2, 0, 2, 1),
            InningScoreStep(4, 0, 2, 2, 3),
            InningScoreStep(5, 1, 1, 3, 4),
            InningScoreStep(6, 0, 1, 3, 5),
            InningScoreStep(7, 0, 0, 3, 5),
            InningScoreStep(8, 0, 0, 3, 5),
            InningScoreStep(9, 0, 0, 3, 5),
        ]
        flow_prof = GameScoreFlowProfile(args.title, args.home, args.away, steps)
        chart = flow_renderer.render(flow_prof)
        print(
            f"Generated Vector SVG Score Flow for '{args.title}' ({len(chart.svg_content)} bytes)"
        )

    elif args.command == "break-plot":
        from mlb_baseball.visual import (
            PitchBreakChartRenderer,
            PitchBreakObservation,
            PitcherArsenalBreakProfile,
        )

        bplot_renderer = PitchBreakChartRenderer()
        sample_pitches = [
            PitchBreakObservation("FF", 98.2, -8.0, 18.0, "#00d2be"),
            PitchBreakObservation("SL", 88.0, 5.5, 2.0, "#a855f7"),
            PitchBreakObservation("CH", 89.5, -14.0, 5.0, "#f59e0b"),
        ]
        profile = PitcherArsenalBreakProfile(args.pitcher, sample_pitches)
        chart = bplot_renderer.render(profile)
        print(f"Generated Vector SVG Pitch Break Plot ({len(chart.svg_content)} bytes)")

    elif args.command == "odds-chart":
        from mlb_baseball.visual import (
            MarketOddsTimeline,
            OddsMovementChartRenderer,
            OddsMovementPoint,
        )

        ochart_renderer = OddsMovementChartRenderer()
        pts = [
            OddsMovementPoint("09:00", 1.90, 1.90),
            OddsMovementPoint("12:00", 1.82, 2.08),
            OddsMovementPoint("15:30", 1.74, 2.20, is_steam_move=True),
            OddsMovementPoint("18:45", 1.70, 2.25),
        ]
        timeline = MarketOddsTimeline(args.title, args.home, args.away, pts)
        chart = ochart_renderer.render(timeline)
        print(
            f"Generated Vector SVG Odds Chart for '{args.title}' ({len(chart.svg_content)} bytes)"
        )

    elif args.command == "nrfi":
        import json as json_lib

        from mlb_baseball.model.nrfi import (
            FirstInningValuationEngine,
            InningOneMatchupInputs,
        )

        nrfi_eng = FirstInningValuationEngine()
        inp = InningOneMatchupInputs(
            home_team=args.home,
            away_team=args.away,
            home_starter_inn1_era=args.home_era,
            away_starter_inn1_era=args.away_era,
            home_top3_woba=args.home_top3,
            away_top3_woba=args.away_top3,
        )
        nrfi_res = nrfi_eng.evaluate_first_inning(inp)

        if args.json:
            nrfi_out = {
                "matchup": f"{args.away} @ {args.home}",
                "nrfi_prob": nrfi_res.nrfi_probability,
                "yrfi_prob": nrfi_res.yrfi_probability,
                "fair_nrfi_line": nrfi_res.fair_nrfi_american,
                "fair_yrfi_line": nrfi_res.fair_yrfi_american,
                "recommendation": nrfi_res.recommended_side,
            }
            print(json_lib.dumps(nrfi_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     FIRST INNING DERIVATIVE VALUATION [{nrfi_res.recommended_side}]")
            hdr_nr = (
                f"     P(NRFI): {nrfi_res.nrfi_probability * 100:.1f}% "
                f"({nrfi_res.fair_nrfi_american:+d}) "
                f"| P(YRFI): {nrfi_res.yrfi_probability * 100:.1f}% "
                f"({nrfi_res.fair_yrfi_american:+d})"
            )
            print(hdr_nr)
            print(f"{'=' * 84}\n")
            print(f"  • Fair NRFI Moneyline  : {nrfi_res.fair_nrfi_american:+d}")
            print(f"  • Fair YRFI Moneyline  : {nrfi_res.fair_yrfi_american:+d}\n")

    elif args.command == "radar":
        from mlb_baseball.visual import (
            PlayerRadarProfile,
            RadarChartRenderer,
            RadarDimension,
        )

        radar_renderer = RadarChartRenderer()
        dims = [
            RadarDimension("Contact", args.contact),
            RadarDimension("Power", args.power),
            RadarDimension("Discipline", args.discipline),
            RadarDimension("Speed", args.speed),
            RadarDimension("Defense", args.defense),
        ]
        prof = PlayerRadarProfile(args.player, dims)
        chart = radar_renderer.render(prof)
        print(
            f"Generated Vector SVG Radar Chart for '{args.player}' ({len(chart.svg_content)} bytes)"
        )

    elif args.command == "tunnel":
        import json as json_lib

        from mlb_baseball.model.tunnel import (
            PitchFlightVector,
            PitchTunnelingEngine,
        )

        tun_eng = PitchTunnelingEngine()
        ff_p = PitchFlightVector(
            "FF",
            velocity_mph=args.ff_velo,
            release_x_ft=-2.1,
            release_z_ft=6.0,
            ivb_in=args.ff_ivb,
            hb_in=args.ff_hb,
        )
        sl_p = PitchFlightVector(
            "SL",
            velocity_mph=args.sl_velo,
            release_x_ft=-2.1,
            release_z_ft=6.0,
            ivb_in=args.sl_ivb,
            hb_in=args.sl_hb,
        )
        tun_res = tun_eng.evaluate_tunnel_pair(ff_p, sl_p)

        if args.json:
            tun_out = {
                "pair": tun_res.pitch_pair_label,
                "release_dist": tun_res.release_distance_in,
                "poc_separation": tun_res.tunnel_distance_at_poc_in,
                "plate_separation": tun_res.plate_break_separation_in,
                "tunnel_score": tun_res.tunneling_quality_score,
                "whiff_boost": tun_res.whiff_boost_pct,
                "is_elite": tun_res.is_elite_tunnel,
            }
            print(json_lib.dumps(tun_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            tun_tag = "ELITE TUNNEL" if tun_res.is_elite_tunnel else "STANDARD"
            print(f"     PITCH ARSENAL TUNNELING [{tun_tag}]")
            hdr_tun = (
                f"     Pair: {tun_res.pitch_pair_label} "
                f"| POC Dist: {tun_res.tunnel_distance_at_poc_in:.1f}in "
                f"| Plate: {tun_res.plate_break_separation_in:.1f}in"
            )
            print(hdr_tun)
            print(f"{'=' * 84}\n")
            print(f"  • POC Separation (23.8ft): {tun_res.tunnel_distance_at_poc_in:.1f} in")
            print(f"  • Plate Break Split     : {tun_res.plate_break_separation_in:.1f} in")
            print(f"  • Whiff Boost Multiplier : +{tun_res.whiff_boost_pct:.1f}%\n")

    elif args.command == "serve-api":
        import json as json_lib

        from mlb_baseball.api import MLBApiRouter

        router = MLBApiRouter()
        if args.test_health:
            api_res = router.route_request("/api/v1/health", "GET")
            b_str = (
                api_res.body_data.decode("utf-8")
                if isinstance(api_res.body_data, bytes)
                else str(api_res.body_data)
            )
            print(f"API Health Test: Status {api_res.status_code} | Body: {b_str}")
        else:
            print(
                f"REST API Gateway ready on port {args.port} (Use --test-health for CLI inspection)"
            )

    elif args.command == "shop":
        import json as json_lib

        from mlb_baseball.model.shop import (
            OddsLineShoppingEngine,
            SportsbookQuote,
        )

        shop_eng = OddsLineShoppingEngine()
        sample_quotes = [
            SportsbookQuote(
                "DraftKings", home_decimal_odds=2.25, away_decimal_odds=1.70, vig_pct=4.2
            ),
            SportsbookQuote("FanDuel", home_decimal_odds=2.10, away_decimal_odds=1.80, vig_pct=4.1),
            SportsbookQuote(
                "Pinnacle", home_decimal_odds=2.18, away_decimal_odds=1.77, vig_pct=2.4
            ),
        ]
        shop_res = shop_eng.find_best_lines(
            "g1", args.home, args.away, sample_quotes, model_home_prob=args.model_prob
        )

        if args.json:
            shop_out = {
                "best_home_book": shop_res.best_home_sportsbook,
                "best_home_odds": shop_res.best_home_odds,
                "best_away_book": shop_res.best_away_sportsbook,
                "best_away_odds": shop_res.best_away_odds,
                "synthetic_hold": shop_res.synthetic_market_hold_pct,
                "home_ev": shop_res.home_ev_pct,
                "away_ev": shop_res.away_ev_pct,
                "best_side": shop_res.best_value_side,
            }
            print(json_lib.dumps(shop_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     MULTI-BOOK LINE SHOPPING ({args.home} vs {args.away})")
            best_sd = shop_res.best_value_side or "NO BET"
            print(f"     Hold: {shop_res.synthetic_market_hold_pct:.2f}% | Best Side: {best_sd}")
            print(f"{'=' * 84}\n")
            bh_str = (
                f"  • Best Home: {shop_res.best_home_sportsbook} "
                f"@ {shop_res.best_home_odds} ({shop_res.home_ev_pct:+.1f}%)"
            )
            print(bh_str)
            ba_str = (
                f"  • Best Away: {shop_res.best_away_sportsbook} "
                f"@ {shop_res.best_away_odds} ({shop_res.away_ev_pct:+.1f}%)\n"
            )
            print(ba_str)

    elif args.command == "daemon":
        import json as json_lib

        from mlb_baseball.daemon import DailyAutomationDaemon

        d_eng = DailyAutomationDaemon()
        d_summary = d_eng.execute_daily_cycle(date_str=args.date, skip_doctor=args.skip_doctor)

        if args.json:
            d_out = {
                "timestamp": d_summary.execution_timestamp,
                "pipeline_status": d_summary.pipeline_status,
                "pipeline_duration_s": d_summary.pipeline_duration_s,
                "cache_warming_time_ms": d_summary.cache_warming_time_ms,
                "assets_baked": d_summary.visual_assets_baked,
                "alerts": d_summary.alerts,
            }
            print(json_lib.dumps(d_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     DAILY AUTOMATION DAEMON RUN ({d_summary.execution_timestamp})")
            p_hdr = (
                f"     Status: [{d_summary.pipeline_status}] | {d_summary.pipeline_duration_s:.2f}s"
            )
            print(p_hdr)
            print(f"{'=' * 84}\n")
            print(f"  • Cache Warming        : {d_summary.cache_warming_time_ms:.1f}ms (5 Marts)")
            print(f"  • Visual Assets Baked  : {d_summary.visual_assets_baked} vector charts")
            print(f"  • Active Alerts        : {len(d_summary.alerts)} registered\n")

    elif args.command == "daily":
        import json as json_lib

        from mlb_baseball.daily import format_daily_briefing_terminal, generate_daily_briefing
        from mlb_baseball.db import get_connection

        with get_connection() as conn:
            daily_report = generate_daily_briefing(
                target_date=args.date,
                bankroll=args.bankroll,
                min_edge=args.min_edge,
                conn=conn,
            )

        if args.json:
            out_dict = {
                "target_date": daily_report.target_date,
                "generated_at": daily_report.generated_at,
                "health_status": [
                    {"name": chk.name, "ok": chk.ok, "detail": chk.detail}
                    for chk in daily_report.health_status
                ],
                "matchups": [
                    {
                        "game_key": m.game_instance_key,
                        "away_team": m.away_team,
                        "home_team": m.home_team,
                        "model_home_win_prob": m.model_home_win_prob,
                        "model_away_win_prob": m.model_away_win_prob,
                        "home_starter": m.home_starter,
                        "away_starter": m.away_starter,
                    }
                    for m in daily_report.matchups
                ],
                "pitcher_props": [
                    {
                        "pitcher_name": p.pitcher_name,
                        "team": p.team,
                        "projected_k_pct": p.projected_k_pct,
                        "expected_k": p.expected_k,
                        "prob_over_5_5_k": p.prob_over_5_5_k,
                        "prob_over_6_5_k": p.prob_over_6_5_k,
                    }
                    for p in daily_report.pitcher_props
                ],
                "portfolio_plan": {
                    "total_bankroll_usd": daily_report.portfolio_plan.total_bankroll_usd,
                    "total_allocated_usd": daily_report.portfolio_plan.total_allocated_usd,
                    "total_exposure_pct": daily_report.portfolio_plan.total_exposure_pct,
                    "expected_growth_rate": (
                        daily_report.portfolio_plan.expected_portfolio_growth_rate
                    ),
                    "recommendations": [
                        {
                            "description": r.opportunity.description,
                            "model_prob": r.opportunity.model_probability,
                            "market_prob": r.opportunity.market_implied_probability,
                            "edge_pct": r.opportunity.edge,
                            "kelly_fraction": r.kelly_fraction,
                            "wager_usd": r.wager_amount_usd,
                            "expected_value_pct": r.expected_value_pct,
                        }
                        for r in daily_report.portfolio_plan.recommendations
                    ],
                },
            }
            print(json_lib.dumps(out_dict, indent=2))
        else:
            print(format_daily_briefing_terminal(daily_report))
    elif args.command == "kelly":
        import json as json_lib

        from mlb_baseball import serve
        from mlb_baseball.db import get_connection
        from mlb_baseball.model.portfolio import (
            BetOpportunity,
            KellyAllocator,
            PositionType,
            probability_to_decimal_odds,
        )

        with get_connection() as conn:
            raw_alphas = serve.fetch_prediction_market_alpha(min_edge=args.min_edge, conn=conn)

        opportunities = []
        for i, alpha_item in enumerate(raw_alphas):
            m_prob = float(alpha_item.get("model_home_win_prob") or 0.50)
            mkt_prob = float(alpha_item.get("market_home_prob") or 0.50)
            if mkt_prob <= 0 or mkt_prob >= 1:
                continue
            opp = BetOpportunity(
                opportunity_id=f"alpha_{i}",
                game_instance_key=str(alpha_item.get("game_instance_key", "")),
                market_source=str(alpha_item.get("market_source", "market")),
                position_type=PositionType.MONEYLINE,
                description=(
                    f"{alpha_item.get('away_team', 'AWAY')} @ "
                    f"{alpha_item.get('home_team', 'HOME')} "
                    f"({alpha_item.get('recommendation', 'Win')})"
                ),
                model_probability=m_prob,
                market_implied_probability=mkt_prob,
                decimal_odds=probability_to_decimal_odds(mkt_prob),
            )
            opportunities.append(opp)

        allocator = KellyAllocator(
            fraction=args.fraction,
            max_single_bet_pct=args.max_bet,
            max_total_exposure_pct=args.max_total,
            min_edge_pct=args.min_edge,
        )
        plan = allocator.allocate(opportunities, total_bankroll=args.bankroll)

        if args.json:
            out_dict = {
                "total_bankroll_usd": plan.total_bankroll_usd,
                "total_allocated_usd": plan.total_allocated_usd,
                "total_exposure_pct": plan.total_exposure_pct,
                "expected_portfolio_growth_rate": plan.expected_portfolio_growth_rate,
                "recommendations": [
                    {
                        "game_key": r.opportunity.game_instance_key,
                        "source": r.opportunity.market_source,
                        "description": r.opportunity.description,
                        "model_prob": r.opportunity.model_probability,
                        "market_prob": r.opportunity.market_implied_probability,
                        "edge_pct": r.opportunity.edge,
                        "kelly_fraction": r.kelly_fraction,
                        "wager_usd": r.wager_amount_usd,
                        "expected_value_pct": r.expected_value_pct,
                    }
                    for r in plan.recommendations
                ],
            }
            print(json_lib.dumps(out_dict, indent=2))
        else:
            print(
                f"\n=== KELLY CRITERION ALLOCATION PLAN "
                f"(Bankroll: ${plan.total_bankroll_usd:,.2f}) ==="
            )
            print(
                f"Total Allocated: ${plan.total_allocated_usd:,.2f} "
                f"({plan.total_exposure_pct * 100:.2f}% of Bankroll)"
            )
            print(f"Expected Daily Growth Rate: {plan.expected_portfolio_growth_rate * 100:.4f}%\n")
            if not plan.recommendations:
                print("No +EV opportunities meeting the minimum edge threshold.")
            else:
                header = (
                    f"{'Market / Matchup':<32} {'Model%':<8} {'Mkt%':<8} "
                    f"{'Edge%':<8} {'Kelly%':<8} {'Wager ($)':<10} {'+EV%':<8}"
                )
                print(header)
                print("-" * len(header))
                for r in plan.recommendations:
                    print(
                        f"{r.opportunity.description:<32} "
                        f"{r.opportunity.model_probability * 100:>6.1f}%  "
                        f"{r.opportunity.market_implied_probability * 100:>6.1f}%  "
                        f"{r.opportunity.edge * 100:>+6.1f}%  "
                        f"{r.kelly_fraction * 100:>6.2f}%  "
                        f"${r.wager_amount_usd:>8.2f}  "
                        f"{r.expected_value_pct * 100:>+6.1f}%"
                    )
    elif args.command == "serve":
        import json

        from mlb_baseball import serve
        from mlb_baseball.db import get_connection

        with get_connection() as conn:
            if args.mart == "daily-grid":
                data = serve.fetch_daily_betting_grid(game_date=args.date, conn=conn)
            elif args.mart == "pitcher-card":
                data = serve.fetch_pitcher_card(player_id=args.player_id, conn=conn)
            elif args.mart == "props":
                data = serve.fetch_pitcher_prop_market(
                    game_date=args.date, mlb_game_pk=args.game_pk, conn=conn
                )
            elif args.mart == "live-tracker":
                data = serve.fetch_live_game_tracker(
                    game_date=args.date, mlb_game_pk=args.game_pk, conn=conn
                )
            elif args.mart == "alpha":
                data = serve.fetch_prediction_market_alpha(min_edge=args.min_edge, conn=conn)
            else:
                data = []

        if args.json:
            print(json.dumps(data, default=str, indent=2))
        else:
            print(f"Serving Mart: serve.{args.mart} ({len(data)} rows):")
            for row in data[:20]:
                print(" ", row)
            if len(data) > 20:
                print(f"  ... and {len(data) - 20} more rows")


if __name__ == "__main__":
    main()
