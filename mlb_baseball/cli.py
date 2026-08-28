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
import dataclasses
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
    groups = _concurrency_groups(names)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(groups)) as pool:
        try:
            results = list(pool.map(lambda names: _run_group(names, mode, profile), groups))
        except Exception as exc:
            print(f"mlb {mode}: an entire connector group failed unexpectedly ({exc})")
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
    parser = argparse.ArgumentParser(prog="mlb")
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

    # Polymorphic research dossier and report exporter (EXPORT-01)
    export_parser = subparsers.add_parser(
        "export",
        help="export publication-ready research dossiers in Markdown, Terminal, HTML, or JSON",
    )
    export_parser.add_argument(
        "--date", type=str, help="target game date (YYYY-MM-DD, default: today)"
    )
    export_parser.add_argument(
        "--format",
        type=str,
        choices=["markdown", "terminal", "html", "json"],
        default="markdown",
        help="output format (default: markdown)",
    )
    export_parser.add_argument(
        "--output", type=str, help="optional output file path to write rendered dossier"
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

    # Player archetype & pitcher similarity comps (CLUSTER-01)
    cluster_parser = subparsers.add_parser(
        "cluster",
        help="find historical pitcher twins and batter whiff vulnerability profiles (CLUSTER-01)",
    )
    cluster_parser.add_argument(
        "--velo", type=float, default=96.5, help="target fastball velocity (default: 96.5)"
    )
    cluster_parser.add_argument(
        "--ivb", type=float, default=18.5, help="target fastball IVB (default: 18.5)"
    )
    cluster_parser.add_argument("--json", action="store_true", help="output comps as JSON")

    # Comprehensive player dossier & data dump (DUMP-01)
    dump_parser = subparsers.add_parser(
        "dump",
        help="export multi-table player analytical dossiers to JSON or CSV (DUMP-01)",
    )
    dump_parser.add_argument(
        "--format", choices=["json", "csv"], default="json", help="export format (default: json)"
    )

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

    # Batter vs Pitcher micro-matchup engine (BVP-01)
    bvp_parser = subparsers.add_parser(
        "bvp",
        help="evaluate batter vs pitcher matchup with empirical Bayes shrinkage (BVP-01)",
    )
    bvp_parser.add_argument(
        "--batter-woba", type=float, default=0.360, help="batter wOBA vs hand (default: 0.360)"
    )
    bvp_parser.add_argument(
        "--pitcher-woba", type=float, default=0.300, help="pitcher wOBA vs hand (default: 0.300)"
    )
    bvp_parser.add_argument(
        "--pa", type=int, default=15, help="observed head-to-head PA (default: 15)"
    )
    bvp_parser.add_argument(
        "--raw-woba", type=float, default=0.450, help="observed head-to-head wOBA (default: 0.450)"
    )
    bvp_parser.add_argument("--json", action="store_true", help="output BvP evaluation as JSON")

    # Individual umpire strike zone bias engine (UMP-01)
    ump_parser = subparsers.add_parser(
        "umpire",
        help="quantify individual umpire strike zone dimensions and totals impact (UMP-01)",
    )
    ump_parser.add_argument("--name", type=str, default="Angel Hernandez", help="umpire name")
    ump_parser.add_argument(
        "--base-total", type=float, default=8.5, help="baseline game total runs (default: 8.5)"
    )
    ump_parser.add_argument(
        "--expansion-in",
        type=float,
        default=0.6,
        help="horizontal zone expansion in (default: 0.6)",
    )
    ump_parser.add_argument("--json", action="store_true", help="output umpire adjustment as JSON")

    # Stadium 3D vector wind & micro-climate physics (WEATHER-01)
    weather_parser = subparsers.add_parser(
        "weather",
        help="compute stadium 3D vector wind aerodynamics and air density index (WEATHER-01)",
    )
    weather_parser.add_argument(
        "--azimuth", type=float, default=22.5, help="stadium azimuth deg (default: 22.5 - Wrigley)"
    )
    weather_parser.add_argument(
        "--wind-speed", type=float, default=15.0, help="wind speed mph (default: 15.0)"
    )
    weather_parser.add_argument(
        "--wind-dir",
        type=float,
        default=202.5,
        help="meteorological wind FROM dir (default: 202.5)",
    )
    weather_parser.add_argument(
        "--temp", type=float, default=78.0, help="temperature F (default: 78.0)"
    )
    weather_parser.add_argument(
        "--altitude", type=float, default=600.0, help="stadium altitude ft (default: 600.0)"
    )
    weather_parser.add_argument(
        "--json", action="store_true", help="output weather physics as JSON"
    )

    # Dynamic bullpen fatigue decay simulator (BULLPEN-01)
    bullpen_parser = subparsers.add_parser(
        "bullpen",
        help="evaluate team bullpen fatigue decay and high-leverage hierarchy (BULLPEN-01)",
    )
    bullpen_parser.add_argument(
        "--team", type=str, default="LAD", help="team abbreviation (default: LAD)"
    )
    bullpen_parser.add_argument(
        "--json", action="store_true", help="output bullpen projection as JSON"
    )

    # Batter opposite-field line drive sinking liners (OPPO-LINER-01)
    ol_parser = subparsers.add_parser(
        "oppo-liner",
        help="evaluate oppo line drive rate, BABIP conversion, and OFLDII (OPPO-LINER-01)",
    )
    ol_parser.add_argument(
        "--ld", type=float, default=20.0, help="oppo line drive pct (default: 20.0)"
    )
    ol_parser.add_argument(
        "--babip", type=float, default=0.620, help="oppo liner babip (default: 0.620)"
    )
    ol_parser.add_argument(
        "--hard", type=float, default=40.0, help="oppo liner hard hit pct (default: 40.0)"
    )
    ol_parser.add_argument(
        "--events", type=int, default=120, help="oppo contact events (default: 120)"
    )
    ol_parser.add_argument(
        "--json", action="store_true", help="output oppo liner evaluation as JSON"
    )

    # Pitcher arm slot fatigue sag & lateral drift (SLOT-SAG-01)
    ss_parser = subparsers.add_parser(
        "slot-sag",
        help="evaluate late-outing arm slot drop, lateral drift, and ASFSI (SLOT-SAG-01)",
    )
    ss_parser.add_argument(
        "--early-deg", type=float, default=45.0, help="early slot angle deg (default: 45.0)"
    )
    ss_parser.add_argument(
        "--late-deg", type=float, default=43.5, help="late slot angle deg (default: 43.5)"
    )
    ss_parser.add_argument(
        "--early-x", type=float, default=-24.0, help="early release x in (default: -24.0)"
    )
    ss_parser.add_argument(
        "--late-x", type=float, default=-25.2, help="late release x in (default: -25.2)"
    )
    ss_parser.add_argument(
        "--pitches", type=int, default=35, help="late pitches thrown (default: 35)"
    )
    ss_parser.add_argument("--json", action="store_true", help="output slot sag evaluation as JSON")

    # Outfielder wall leap & timing elevation (WALL-LEAP-01)
    wl_parser = subparsers.add_parser(
        "wall-leap",
        help="evaluate vertical leap apex, timing precision error, and WLTEI (WALL-LEAP-01)",
    )
    wl_parser.add_argument(
        "--apex", type=float, default=18.0, help="vertical leap apex in (default: 18.0)"
    )
    wl_parser.add_argument(
        "--timing", type=float, default=95.0, help="timing error ms (default: 95.0)"
    )
    wl_parser.add_argument(
        "--catch", type=float, default=35.0, help="above wall catch pct (default: 35.0)"
    )
    wl_parser.add_argument(
        "--opps", type=int, default=12, help="wall leap opportunities (default: 12)"
    )
    wl_parser.add_argument(
        "--json", action="store_true", help="output wall leap evaluation as JSON"
    )

    # Pure-Python SVG Strike Zone 3D Isometric (ZONE-ISOMETRIC-01)
    zi_parser = subparsers.add_parser(
        "zone-isometric",
        help="generate vector SVG 3D isometric strike zone box (ZONE-ISOMETRIC-01)",
    )
    zi_parser.add_argument("--title", type=str, default="Skubal 3D Strike Zone", help="chart title")
    zi_parser.add_argument("--pitcher", type=str, default="Tarik Skubal", help="pitcher name")

    # Batter lineup protection & on-deck advantage (LINEUP-PROTECT-01)
    lp_parser = subparsers.add_parser(
        "lineup-protect",
        help="evaluate lineup protection influence and on-deck threat (LINEUP-PROTECT-01)",
    )
    lp_parser.add_argument(
        "--woba", type=float, default=0.320, help="on-deck hitter wOBA (default: 0.320)"
    )
    lp_parser.add_argument(
        "--zone", type=float, default=45.0, help="zone pct thrown to batter (default: 45.0)"
    )
    lp_parser.add_argument(
        "--fstrike", type=float, default=60.0, help="first pitch strike pct (default: 60.0)"
    )
    lp_parser.add_argument("--pa", type=int, default=120, help="plate appearances (default: 120)")
    lp_parser.add_argument(
        "--json", action="store_true", help="output lineup protection evaluation as JSON"
    )

    # Bullpen bridge sequencing & high-leverage handoff (BULLPEN-BRIDGE-01)
    bb_parser = subparsers.add_parser(
        "bullpen-bridge",
        help="evaluate bullpen bridge sequencing and handoff efficiency (BULLPEN-BRIDGE-01)",
    )
    bb_parser.add_argument(
        "--hold", type=float, default=65.0, help="hold conversion pct (default: 65.0)"
    )
    bb_parser.add_argument(
        "--leverage", type=float, default=50.0, help="leverage match rate pct (default: 50.0)"
    )
    bb_parser.add_argument(
        "--inherited", type=float, default=30.0, help="inherited runner score pct (default: 30.0)"
    )
    bb_parser.add_argument(
        "--innings", type=float, default=80.0, help="high leverage innings (default: 80.0)"
    )
    bb_parser.add_argument(
        "--json", action="store_true", help="output bullpen bridge evaluation as JSON"
    )

    # Pure-Python SVG spray chart heatmap (SPRAY-HEATMAP-01)
    sh_parser = subparsers.add_parser(
        "spray-heatmap",
        help="generate vector SVG spray chart heatmap (SPRAY-HEATMAP-01)",
    )
    sh_parser.add_argument("--title", type=str, default="Spray Chart Heatmap", help="chart title")
    sh_parser.add_argument("--batter", type=str, default="Shohei Ohtani", help="batter name")
    sh_parser.add_argument("--hand", type=str, default="L", help="batter hand R or L (default: L)")

    # Batter swing timing & tempo consistency (SWING-TEMPO-01)
    st_parser = subparsers.add_parser(
        "swing-tempo",
        help="evaluate swing timing variance, bat speed stability, and STCI (SWING-TEMPO-01)",
    )
    st_parser.add_argument(
        "--std", type=float, default=3.5, help="timing std deviation ms (default: 3.5)"
    )
    st_parser.add_argument(
        "--consistency", type=float, default=90.0, help="bat speed consistency pct (default: 90.0)"
    )
    st_parser.add_argument(
        "--contact", type=float, default=75.0, help="late count contact pct (default: 75.0)"
    )
    st_parser.add_argument(
        "--swings", type=int, default=200, help="total competitive swings (default: 200)"
    )
    st_parser.add_argument(
        "--json", action="store_true", help="output swing tempo evaluation as JSON"
    )

    # Batter breaking ball chase recognition (CHASE-RECOG-01)
    cr_parser = subparsers.add_parser(
        "chase-recog",
        help="evaluate breaking ball chase avoidance, take discipline, and BBCRI (CHASE-RECOG-01)",
    )
    cr_parser.add_argument(
        "--chase", type=float, default=32.0, help="breaking ball chase pct (default: 32.0)"
    )
    cr_parser.add_argument(
        "--take", type=float, default=68.0, help="breaking ball take pct (default: 68.0)"
    )
    cr_parser.add_argument(
        "--whiff", type=float, default=58.0, help="breaking ball whiff pct (default: 58.0)"
    )
    cr_parser.add_argument(
        "--pitches", type=int, default=200, help="breaking balls seen (default: 200)"
    )
    cr_parser.add_argument(
        "--json", action="store_true", help="output chase recog evaluation as JSON"
    )

    # Pitcher first-pitch strike command vs ambush (FIRST-PITCH-AMBUSH-01)
    fpa_parser = subparsers.add_parser(
        "first-pitch-ambush",
        help="evaluate 0-0 strike command, damage suppression, and FPCARI (FIRST-PITCH-AMBUSH-01)",
    )
    fpa_parser.add_argument(
        "--f-strike", type=float, default=60.0, help="0-0 strike pct (default: 60.0)"
    )
    fpa_parser.add_argument(
        "--hard", type=float, default=44.0, help="0-0 hard hit pct (default: 44.0)"
    )
    fpa_parser.add_argument(
        "--slg", type=float, default=0.520, help="0-0 slugging pct (default: 0.520)"
    )
    fpa_parser.add_argument("--bf", type=int, default=180, help="batters faced (default: 180)")
    fpa_parser.add_argument("--json", action="store_true", help="output first pitch ambush as JSON")

    # Catcher wild pitch & passed ball wall blocking (WALL-BLOCK-01)
    wb_parser = subparsers.add_parser(
        "wall-block",
        help="evaluate dirt pitch blocking, advance suppression, and CWBEI (WALL-BLOCK-01)",
    )
    wb_parser.add_argument(
        "--block", type=float, default=82.0, help="dirt ball block pct (default: 82.0)"
    )
    wb_parser.add_argument(
        "--suppress", type=float, default=86.0, help="runner advance suppress pct (default: 86.0)"
    )
    wb_parser.add_argument(
        "--pb", type=float, default=3.5, help="passed ball rate per 1000 (default: 3.5)"
    )
    wb_parser.add_argument(
        "--opps", type=int, default=120, help="dirt pitches with runners (default: 120)"
    )
    wb_parser.add_argument(
        "--json", action="store_true", help="output wall block evaluation as JSON"
    )

    # Pitcher pitch tunnel decision separation chart (TUNNEL-DECISION-01)
    td_parser = subparsers.add_parser(
        "tunnel-decision",
        help="generate vector SVG pitch tunnel decision separation chart (TUNNEL-DECISION-01)",
    )
    td_parser.add_argument(
        "--title", type=str, default="Skenes Fastball-Splinker Tunnel", help="chart title"
    )
    td_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter in-zone fastball contact & whiff vulnerability (HEAT-CHECK-01)
    hc_parser = subparsers.add_parser(
        "heat-check",
        help="evaluate in-zone fastball contact, whiff avoidance, and IZHSMI (HEAT-CHECK-01)",
    )
    hc_parser.add_argument(
        "--contact", type=float, default=80.0, help="in-zone fb contact pct (default: 80.0)"
    )
    hc_parser.add_argument(
        "--hard", type=float, default=42.0, help="in-zone fb hard hit pct (default: 42.0)"
    )
    hc_parser.add_argument(
        "--whiff", type=float, default=20.0, help="in-zone fb whiff pct (default: 20.0)"
    )
    hc_parser.add_argument(
        "--swings", type=int, default=150, help="in-zone fb swings (default: 150)"
    )
    hc_parser.add_argument(
        "--json", action="store_true", help="output heat check evaluation as JSON"
    )

    # Pitcher secondary pitch whiff escalation in 2-strike counts (PUTAWAY-DEPTH-01)
    pwd_parser = subparsers.add_parser(
        "putaway-depth",
        help="evaluate 2-strike secondary whiff surge, chase surge, and PWEI (PUTAWAY-DEPTH-01)",
    )
    pwd_parser.add_argument(
        "--early", type=float, default=28.0, help="early count whiff pct (default: 28.0)"
    )
    pwd_parser.add_argument(
        "--two-strike", type=float, default=38.0, help="2-strike whiff pct (default: 38.0)"
    )
    pwd_parser.add_argument(
        "--chase", type=float, default=34.0, help="2-strike chase pct (default: 34.0)"
    )
    pwd_parser.add_argument(
        "--pitches", type=int, default=150, help="2-strike secondary pitches (default: 150)"
    )
    pwd_parser.add_argument(
        "--json", action="store_true", help="output putaway depth evaluation as JSON"
    )

    # Outfielder throw accuracy & direct line target efficiency (OUTFIELD-TARGET-01)
    oft_parser = subparsers.add_parser(
        "outfield-target",
        help="evaluate outfield throw accuracy, assist conversion, and OLTAI (OUTFIELD-TARGET-01)",
    )
    oft_parser.add_argument("--pos", type=str, default="RF", help="position (default: RF)")
    oft_parser.add_argument("--acc", type=float, default=65.0, help="accuracy pct (default: 65.0)")
    oft_parser.add_argument("--arm", type=float, default=88.0, help="arm velo mph (default: 88.0)")
    oft_parser.add_argument(
        "--conv", type=float, default=60.0, help="assist conv pct (default: 60.0)"
    )
    oft_parser.add_argument("--chances", type=int, default=40, help="throw chances (default: 40)")
    oft_parser.add_argument(
        "--json", action="store_true", help="output outfield target evaluation as JSON"
    )

    # Pitcher arsenal movement & spin polar compass (POLAR-COMPASS-01)
    pc_parser = subparsers.add_parser(
        "polar-compass",
        help="generate vector SVG pitcher arsenal movement & spin polar compass (POLAR-COMPASS-01)",
    )
    pc_parser.add_argument(
        "--title", type=str, default="Paul Skenes Movement Polar Compass", help="chart title"
    )
    pc_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter opposite-field power & alley gap conversion (OPPO-GAP-01)
    og_parser = subparsers.add_parser(
        "oppo-gap",
        help="evaluate opposite-field hard contact, extra-base conversion, and OFGPI (OPPO-GAP-01)",
    )
    og_parser.add_argument(
        "--oppo", type=float, default=25.0, help="oppo contact pct (default: 25.0)"
    )
    og_parser.add_argument(
        "--hard", type=float, default=34.0, help="oppo hard hit pct (default: 34.0)"
    )
    og_parser.add_argument("--xbh", type=float, default=8.5, help="oppo XBH pct (default: 8.5)")
    og_parser.add_argument(
        "--opps", type=int, default=100, help="oppo contact chances (default: 100)"
    )
    og_parser.add_argument("--json", action="store_true", help="output oppo gap evaluation as JSON")

    # Pitcher release point spin angle stability (SPIN-ALIGN-01)
    sa_parser = subparsers.add_parser(
        "spin-align",
        help="evaluate multi-pitch spin axis alignment, release stability, ASARCI (SPIN-ALIGN-01)",
    )
    sa_parser.add_argument(
        "--axis-sd", type=float, default=28.0, help="spin axis std dev mins (default: 28.0)"
    )
    sa_parser.add_argument(
        "--z-sd", type=float, default=1.5, help="release height std dev in (default: 1.5)"
    )
    sa_parser.add_argument(
        "--x-sd", type=float, default=1.8, help="release side std dev in (default: 1.8)"
    )
    sa_parser.add_argument(
        "--pitches", type=int, default=4, help="arsenal pitch count (default: 4)"
    )
    sa_parser.add_argument(
        "--json", action="store_true", help="output spin align evaluation as JSON"
    )

    # Middle infield double-play turn speed & footwork (DP-FOOTWORK-01)
    dpf_parser = subparsers.add_parser(
        "dp-footwork",
        help="evaluate middle infield DP pivot time, relay velo, and DPFTI (DP-FOOTWORK-01)",
    )
    dpf_parser.add_argument("--pos", type=str, default="2B", help="position (default: 2B)")
    dpf_parser.add_argument(
        "--pivot", type=float, default=0.74, help="pivot time sec (default: 0.74)"
    )
    dpf_parser.add_argument(
        "--throw", type=float, default=78.0, help="throw velo mph (default: 78.0)"
    )
    dpf_parser.add_argument(
        "--conv", type=float, default=72.0, help="dp conversion pct (default: 72.0)"
    )
    dpf_parser.add_argument(
        "--opps", type=int, default=60, help="dp turn opportunities (default: 60)"
    )
    dpf_parser.add_argument(
        "--json", action="store_true", help="output dp footwork evaluation as JSON"
    )

    # Batter Statcast EV vs LA contact grid (BARREL-GRID-01)
    bg_parser = subparsers.add_parser(
        "barrel-grid",
        help="generate vector SVG Statcast contact quality barrel grid (BARREL-GRID-01)",
    )
    bg_parser.add_argument(
        "--title", type=str, default="Shohei Ohtani Statcast Contact Grid", help="chart title"
    )
    bg_parser.add_argument("--batter", type=str, default="Shohei Ohtani", help="batter name")

    # Batter pull line-drive slice power & fair conversion (PULL-SLICE-01)
    ps_parser = subparsers.add_parser(
        "pull-slice",
        help="evaluate pull line-drive fair conversion, hook avoidance, and PLDSR (PULL-SLICE-01)",
    )
    ps_parser.add_argument(
        "--pull-ld", type=float, default=18.0, help="pull LD pct (default: 18.0)"
    )
    ps_parser.add_argument(
        "--conv", type=float, default=70.0, help="fair conversion pct (default: 70.0)"
    )
    ps_parser.add_argument("--hard", type=float, default=50.0, help="hard hit pct (default: 50.0)")
    ps_parser.add_argument(
        "--opps", type=int, default=80, help="pull LD opportunities (default: 80)"
    )
    ps_parser.add_argument(
        "--json", action="store_true", help="output pull slice evaluation as JSON"
    )

    # Pitcher arm fatigue velocity decay & release drop (FATIGUE-DROP-01)
    fd_parser = subparsers.add_parser(
        "fatigue-drop",
        help="evaluate late velocity decay, vertical release drop, and PAFII (FATIGUE-DROP-01)",
    )
    fd_parser.add_argument(
        "--velo-drop", type=float, default=1.5, help="late velo drop mph (default: 1.5)"
    )
    fd_parser.add_argument(
        "--rel-drop", type=float, default=1.8, help="late release drop in (default: 1.8)"
    )
    fd_parser.add_argument(
        "--strike", type=float, default=61.0, help="late strike pct (default: 61.0)"
    )
    fd_parser.add_argument(
        "--pitches", type=int, default=150, help="pitches past 75 (default: 150)"
    )
    fd_parser.add_argument(
        "--json", action="store_true", help="output fatigue drop evaluation as JSON"
    )

    # Outfielder first-step reaction burst & jump efficiency (FIRST-STEP-01)
    fs_parser = subparsers.add_parser(
        "first-step",
        help="evaluate outfielder first-step reaction, burst distance, and FSRJI (FIRST-STEP-01)",
    )
    fs_parser.add_argument("--pos", type=str, default="CF", help="position (default: CF)")
    fs_parser.add_argument(
        "--react", type=float, default=0.40, help="reaction time sec (default: 0.40)"
    )
    fs_parser.add_argument(
        "--dist", type=float, default=32.0, help="1.5s distance ft (default: 32.0)"
    )
    fs_parser.add_argument(
        "--eff", type=float, default=86.0, help="route efficiency pct (default: 86.0)"
    )
    fs_parser.add_argument(
        "--chances", type=int, default=120, help="outfield flyball chances (default: 120)"
    )
    fs_parser.add_argument(
        "--json", action="store_true", help="output first step evaluation as JSON"
    )

    # Pitcher count-dependent pitch mix transition flow (FLOW-MIX-01)
    fm_parser = subparsers.add_parser(
        "flow-mix",
        help="generate vector SVG count transition pitch mix flow chart (FLOW-MIX-01)",
    )
    fm_parser.add_argument(
        "--title", type=str, default="Paul Skenes Count Flow Mix", help="chart title"
    )
    fm_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter high-fastball top-of-zone whiff vs damage (HIGH-HEAT-01)
    hh_parser = subparsers.add_parser(
        "high-heat",
        help="evaluate high-fastball top-of-zone whiff, damage, and HHEVI (HIGH-HEAT-01)",
    )
    hh_parser.add_argument(
        "--swing", type=float, default=60.0, help="high FB swing pct (default: 60.0)"
    )
    hh_parser.add_argument(
        "--whiff", type=float, default=26.0, help="high FB whiff pct (default: 26.0)"
    )
    hh_parser.add_argument(
        "--hard", type=float, default=36.0, help="high FB hard hit pct (default: 36.0)"
    )
    hh_parser.add_argument(
        "--opps", type=int, default=200, help="high FB opportunities (default: 200)"
    )
    hh_parser.add_argument(
        "--json", action="store_true", help="output high heat evaluation as JSON"
    )

    # Pitcher seam-shifted wake latent movement (SSW-LATENT-01)
    ssw_l_parser = subparsers.add_parser(
        "ssw-latent",
        help="evaluate seam-shifted wake non-Magnus break and SSWLMR (SSW-LATENT-01)",
    )
    ssw_l_parser.add_argument(
        "--pitch", type=str, default="Sinker", help="pitch type (default: Sinker)"
    )
    ssw_l_parser.add_argument(
        "--optical", type=int, default=75, help="optical axis minutes (default: 75)"
    )
    ssw_l_parser.add_argument(
        "--inferred", type=int, default=110, help="inferred axis minutes (default: 110)"
    )
    ssw_l_parser.add_argument(
        "--obs", type=float, default=17.5, help="observed break in (default: 17.5)"
    )
    ssw_l_parser.add_argument(
        "--mag", type=float, default=14.0, help="pure Magnus break in (default: 14.0)"
    )
    ssw_l_parser.add_argument("--pitches", type=int, default=220, help="pitch count (default: 220)")
    ssw_l_parser.add_argument(
        "--json", action="store_true", help="output ssw latent evaluation as JSON"
    )

    # Infield bunt defense charging speed & barehand (BUNT-CHARGE-01)
    bc_parser = subparsers.add_parser(
        "bunt-charge",
        help="evaluate infield bunt defense charge speed, barehand, and IBCDI (BUNT-CHARGE-01)",
    )
    bc_parser.add_argument("--pos", type=str, default="3B", help="position (default: 3B)")
    bc_parser.add_argument(
        "--speed", type=float, default=24.0, help="sprint speed fps (default: 24.0)"
    )
    bc_parser.add_argument(
        "--barehand", type=float, default=0.58, help="barehand transfer sec (default: 0.58)"
    )
    bc_parser.add_argument(
        "--conv", type=float, default=74.0, help="bunt out conversion pct (default: 74.0)"
    )
    bc_parser.add_argument("--chances", type=int, default=30, help="bunt chances (default: 30)")
    bc_parser.add_argument(
        "--json", action="store_true", help="output bunt charge evaluation as JSON"
    )

    # Pitcher release point & tunnel box chart (TUNNEL-BOX-01)
    tb_parser = subparsers.add_parser(
        "tunnel-box",
        help="generate vector SVG release window & tunnel box chart (TUNNEL-BOX-01)",
    )
    tb_parser.add_argument(
        "--title", type=str, default="Paul Skenes Release & Tunnel Box", help="chart title"
    )
    tb_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter pull-side air contact vs warning track trap (AIR-TRAP-01)
    at_parser = subparsers.add_parser(
        "air-trap",
        help="evaluate pull-air fence clearance vs warning track trap and PACDTR (AIR-TRAP-01)",
    )
    at_parser.add_argument(
        "--pull-fb", type=float, default=32.0, help="pull flyball pct (default: 32.0)"
    )
    at_parser.add_argument(
        "--trap", type=float, default=22.0, help="warning track trap pct (default: 22.0)"
    )
    at_parser.add_argument(
        "--clear", type=float, default=18.0, help="wall clearance HR pct (default: 18.0)"
    )
    at_parser.add_argument("--fb", type=int, default=120, help="total flyballs hit (default: 120)")
    at_parser.add_argument("--json", action="store_true", help="output air trap evaluation as JSON")

    # Pitcher two-strike putaway intent vs heart zone waste leakage (INTENT-LEAK-01)
    il_parser = subparsers.add_parser(
        "intent-leak",
        help="evaluate two-strike chase vs heart mistake leakage and TSPIEI (INTENT-LEAK-01)",
    )
    il_parser.add_argument(
        "--chase", type=float, default=52.0, help="chase dirt intent pct (default: 52.0)"
    )
    il_parser.add_argument(
        "--heart", type=float, default=19.0, help="heart zone leak pct (default: 19.0)"
    )
    il_parser.add_argument(
        "--k-pct", type=float, default=38.0, help="2-strike K pct (default: 38.0)"
    )
    il_parser.add_argument(
        "--pitches", type=int, default=400, help="two-strike pitch count (default: 400)"
    )
    il_parser.add_argument(
        "--json", action="store_true", help="output intent leak evaluation as JSON"
    )

    # Baserunner secondary lead distance vs pitcher pickoff threat (LEAD-SNAP-01)
    lsn_parser = subparsers.add_parser(
        "lead-snap",
        help="evaluate baserunner secondary lead distance, advance boost, and ASLI (LEAD-SNAP-01)",
    )
    lsn_parser.add_argument(
        "--prim", type=float, default=10.5, help="primary lead ft (default: 10.5)"
    )
    lsn_parser.add_argument(
        "--sec", type=float, default=20.5, help="secondary lead ft (default: 20.5)"
    )
    lsn_parser.add_argument(
        "--move", type=float, default=1.35, help="pitcher move sec (default: 1.35)"
    )
    lsn_parser.add_argument(
        "--pickoff", type=float, default=10.0, help="pickoff rate pct (default: 10.0)"
    )
    lsn_parser.add_argument("--opps", type=int, default=75, help="baserunning opps (default: 75)")
    lsn_parser.add_argument(
        "--json", action="store_true", help="output lead snap evaluation as JSON"
    )

    # Batter LA vs EV contour heatmap (LA-EV-CONTOUR-01)
    la_ev_parser = subparsers.add_parser(
        "la-ev-contour",
        help="generate vector SVG launch angle vs exit velocity contour heatmap (LA-EV-CONTOUR-01)",
    )
    la_ev_parser.add_argument(
        "--title", type=str, default="Aaron Judge LA vs EV Heatmap", help="chart title"
    )
    la_ev_parser.add_argument("--batter", type=str, default="Aaron Judge", help="batter name")

    # Batter in-zone whiff vs contact quality tradeoff (ZONE-WHIFF-01)
    zw_parser = subparsers.add_parser(
        "zone-whiff",
        help="evaluate in-zone whiff vs contact barrel tradeoff and ZCPOI (ZONE-WHIFF-01)",
    )
    zw_parser.add_argument(
        "--z-swing", type=float, default=68.0, help="zone swing pct (default: 68.0)"
    )
    zw_parser.add_argument(
        "--z-whiff", type=float, default=16.0, help="zone whiff pct (default: 16.0)"
    )
    zw_parser.add_argument(
        "--z-barrel", type=float, default=9.5, help="zone barrel per BBE pct (default: 9.5)"
    )
    zw_parser.add_argument(
        "--swings", type=int, default=350, help="total zone swings (default: 350)"
    )
    zw_parser.add_argument(
        "--json", action="store_true", help="output zone whiff evaluation as JSON"
    )

    # Pitcher spin axis gyro efficiency & active spin (ACTIVE-SPIN-01)
    as_parser = subparsers.add_parser(
        "active-spin",
        help="evaluate active spin efficiency, gyro angle, and ASMI score (ACTIVE-SPIN-01)",
    )
    as_parser.add_argument(
        "--pitch", type=str, default="4-Seam", help="pitch type (default: 4-Seam)"
    )
    as_parser.add_argument(
        "--total", type=float, default=2300.0, help="total spin RPM (default: 2300.0)"
    )
    as_parser.add_argument(
        "--active", type=float, default=2000.0, help="inferred active spin RPM (default: 2000.0)"
    )
    as_parser.add_argument(
        "--ivb", type=float, default=16.5, help="observed IVB in (default: 16.5)"
    )
    as_parser.add_argument("--hb", type=float, default=8.0, help="observed HB in (default: 8.0)")
    as_parser.add_argument("--pitches", type=int, default=200, help="pitch count (default: 200)")
    as_parser.add_argument(
        "--json", action="store_true", help="output active spin evaluation as JSON"
    )

    # Catcher low-pitch scoop & bottom-zone framing lift (LOW-SCOOP-01)
    lsc_parser = subparsers.add_parser(
        "low-scoop",
        help="evaluate catcher low-shadow scoop framing and BZSFR score (LOW-SCOOP-01)",
    )
    lsc_parser.add_argument(
        "--strike", type=float, default=48.0, help="low zone strike pct (default: 48.0)"
    )
    lsc_parser.add_argument(
        "--scoop", type=float, default=3.5, help="scoop speed fps (default: 3.5)"
    )
    lsc_parser.add_argument(
        "--drop", type=float, default=20.0, help="glove drop rate pct (default: 20.0)"
    )
    lsc_parser.add_argument(
        "--opps", type=int, default=200, help="low zone opportunities (default: 200)"
    )
    lsc_parser.add_argument(
        "--json", action="store_true", help="output low scoop evaluation as JSON"
    )

    # Pitcher spin polar clock chart (SPIN-POLAR-01)
    sp_pol_parser = subparsers.add_parser(
        "spin-polar",
        help="generate vector SVG polar spin clock chart (SPIN-POLAR-01)",
    )
    sp_pol_parser.add_argument(
        "--title", type=str, default="Paul Skenes Polar Spin Clock", help="chart title"
    )
    sp_pol_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter opposite field slash and anti-shift (SLASH-OPPO-01)
    sl_opp_parser = subparsers.add_parser(
        "slash-oppo",
        help="evaluate batter opposite field spray, anti-shift BABIP, and OFSRR (SLASH-OPPO-01)",
    )
    sl_opp_parser.add_argument(
        "--oppo", type=float, default=24.0, help="oppo contact pct (default: 24.0)"
    )
    sl_opp_parser.add_argument(
        "--oppo-ld", type=float, default=20.0, help="oppo line drive pct (default: 20.0)"
    )
    sl_opp_parser.add_argument(
        "--pull-gb", type=float, default=64.0, help="pull groundball pct (default: 64.0)"
    )
    sl_opp_parser.add_argument(
        "--bbe", type=int, default=250, help="total BBE count (default: 250)"
    )
    sl_opp_parser.add_argument(
        "--json", action="store_true", help="output slash oppo evaluation as JSON"
    )

    # Pitcher arm slot stability across arsenal (ARM-ALIGN-01)
    arm_aln_parser = subparsers.add_parser(
        "arm-align",
        help="evaluate multi-pitch arm slot stability and AAAR rating (ARM-ALIGN-01)",
    )
    arm_aln_parser.add_argument(
        "--fb-deg", type=float, default=42.0, help="fastball arm angle deg (default: 42.0)"
    )
    arm_aln_parser.add_argument(
        "--br-deg", type=float, default=43.5, help="breaking arm angle deg (default: 43.5)"
    )
    arm_aln_parser.add_argument(
        "--os-deg", type=float, default=41.0, help="offspeed arm angle deg (default: 41.0)"
    )
    arm_aln_parser.add_argument(
        "--fb-z", type=float, default=68.0, help="fastball release z in (default: 68.0)"
    )
    arm_aln_parser.add_argument(
        "--br-z", type=float, default=66.8, help="breaking release z in (default: 66.8)"
    )
    arm_aln_parser.add_argument(
        "--os-z", type=float, default=68.5, help="offspeed release z in (default: 68.5)"
    )
    arm_aln_parser.add_argument(
        "--pitches", type=int, default=250, help="pitch count (default: 250)"
    )
    arm_aln_parser.add_argument(
        "--json", action="store_true", help="output arm align evaluation as JSON"
    )

    # Outfielder wall crash hazard catch efficiency (WALL-CRASH-01)
    wcr_parser = subparsers.add_parser(
        "wall-crash",
        help="evaluate outfielder wall catch fearlessness and WEBPR runs (WALL-CRASH-01)",
    )
    wcr_parser.add_argument("--pos", type=str, default="CF", help="position (default: CF)")
    wcr_parser.add_argument(
        "--catch", type=float, default=65.0, help="wall catch pct (default: 65.0)"
    )
    wcr_parser.add_argument(
        "--collision", type=float, default=30.0, help="collision rate pct (default: 30.0)"
    )
    wcr_parser.add_argument(
        "--cushion", type=float, default=4.6, help="decel cushion ft (default: 4.6)"
    )
    wcr_parser.add_argument("--opps", type=int, default=40, help="wall opportunities (default: 40)")
    wcr_parser.add_argument("--json", action="store_true", help="output wall crash as JSON")

    # Batter spray isochrones chart (SPRAY-ISO-01)
    sp_iso_parser = subparsers.add_parser(
        "spray-iso",
        help="generate vector SVG spray chart with distance isochrones (SPRAY-ISO-01)",
    )
    sp_iso_parser.add_argument(
        "--title", type=str, default="Aaron Judge Spray & Distance", help="chart title"
    )
    sp_iso_parser.add_argument("--batter", type=str, default="Aaron Judge", help="batter name")

    # Pitcher release extension vs effective velocity (EXT-PERCEIVE-01)
    exp_p_parser = subparsers.add_parser(
        "ext-perceive",
        help="evaluate pitcher extension kinematics and effective velocity (EXT-PERCEIVE-01)",
    )
    exp_p_parser.add_argument("--ext", type=float, default=6.4, help="extension ft (default: 6.4)")
    exp_p_parser.add_argument(
        "--velo", type=float, default=94.0, help="radar velocity mph (default: 94.0)"
    )
    exp_p_parser.add_argument(
        "--ivb", type=float, default=16.5, help="induced vert break in (default: 16.5)"
    )
    exp_p_parser.add_argument(
        "--rel-z", type=float, default=5.85, help="release height ft (default: 5.85)"
    )
    exp_p_parser.add_argument("--pitches", type=int, default=200, help="pitch count (default: 200)")
    exp_p_parser.add_argument(
        "--json", action="store_true", help="output extension evaluation as JSON"
    )

    # Batter two-strike foul attrition (FOUL-ATTRITION-01)
    fat_parser = subparsers.add_parser(
        "foul-attrition",
        help="evaluate batter multi-foul endurance and starter exhaustion (FOUL-ATTRITION-01)",
    )
    fat_parser.add_argument(
        "--multi-foul", type=float, default=11.0, help="multi-foul PA pct (default: 11.0)"
    )
    fat_parser.add_argument(
        "--ppa", type=float, default=3.95, help="pitches per PA (default: 3.95)"
    )
    fat_parser.add_argument(
        "--foul", type=float, default=42.0, help="2-strike foul pct (default: 42.0)"
    )
    fat_parser.add_argument("--pa", type=int, default=500, help="total PA count (default: 500)")
    fat_parser.add_argument("--json", action="store_true", help="output foul attrition as JSON")

    # Catcher dirt ball wall suppression (BLOCK-SUPPRESS-01)
    bsp_parser = subparsers.add_parser(
        "block-suppress",
        help="evaluate catcher dirt-ball blocking, recovery speed, and DBWR (BLOCK-SUPPRESS-01)",
    )
    bsp_parser.add_argument(
        "--block", type=float, default=89.0, help="dirt ball block pct (default: 89.0)"
    )
    bsp_parser.add_argument(
        "--recov", type=float, default=0.82, help="recovery time sec (default: 0.82)"
    )
    bsp_parser.add_argument(
        "--prev", type=float, default=78.0, help="advance prev pct (default: 78.0)"
    )
    bsp_parser.add_argument(
        "--opps", type=int, default=150, help="dirt opportunities (default: 150)"
    )
    bsp_parser.add_argument("--json", action="store_true", help="output block suppress as JSON")

    # Pitch arsenal break diamond (BREAK-DIAMOND-01)
    bd_parser = subparsers.add_parser(
        "break-diamond",
        help="generate vector SVG horizontal vs vertical pitch break scatter (BREAK-DIAMOND-01)",
    )
    bd_parser.add_argument(
        "--title", type=str, default="Paul Skenes Arsenal Break", help="chart title"
    )
    bd_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter pull-air barrel conversion (PULL-BARREL-01)
    pbr_parser = subparsers.add_parser(
        "pull-barrel",
        help="evaluate batter pull-side flyball barrel conversion and true power (PULL-BARREL-01)",
    )
    pbr_parser.add_argument(
        "--pull-fb", type=float, default=30.0, help="flyball pull pct (default: 30.0)"
    )
    pbr_parser.add_argument(
        "--pull-bar", type=float, default=24.0, help="pull barrel pct (default: 24.0)"
    )
    pbr_parser.add_argument(
        "--oppo-bar", type=float, default=12.0, help="oppo barrel pct (default: 12.0)"
    )
    pbr_parser.add_argument(
        "--air-count", type=int, default=70, help="pulled air count (default: 70)"
    )
    pbr_parser.add_argument("--bbe", type=int, default=240, help="total BBE count (default: 240)")
    pbr_parser.add_argument(
        "--json", action="store_true", help="output pull barrel evaluation as JSON"
    )

    # Pitcher two-strike putaway execution (PUTAWAY-EXEC-01)
    ptw_parser = subparsers.add_parser(
        "putaway-exec",
        help="evaluate pitcher 2-strike shadow/chase targeting and execution (PUTAWAY-EXEC-01)",
    )
    ptw_parser.add_argument(
        "--shadow", type=float, default=38.0, help="shadow zone pct (default: 38.0)"
    )
    ptw_parser.add_argument(
        "--chase", type=float, default=28.0, help="chase zone pct (default: 28.0)"
    )
    ptw_parser.add_argument(
        "--heart", type=float, default=20.0, help="heart zone pct (default: 20.0)"
    )
    ptw_parser.add_argument(
        "--waste", type=float, default=14.0, help="waste zone pct (default: 14.0)"
    )
    ptw_parser.add_argument(
        "--pitches", type=int, default=300, help="2-strike pitches (default: 300)"
    )
    ptw_parser.add_argument("--json", action="store_true", help="output putaway execution as JSON")

    # Outfielder reaction and burst route efficiency (ROUTE-BURST-01)
    rbt_parser = subparsers.add_parser(
        "route-burst",
        help="evaluate outfielder reaction, burst velocity, and route (ROUTE-BURST-01)",
    )
    rbt_parser.add_argument("--pos", type=str, default="CF", help="fielding position (default: CF)")
    rbt_parser.add_argument(
        "--react", type=float, default=0.44, help="reaction time sec (default: 0.44)"
    )
    rbt_parser.add_argument(
        "--burst", type=float, default=27.0, help="burst velocity ft/s (default: 27.0)"
    )
    rbt_parser.add_argument(
        "--route", type=float, default=93.0, help="route efficiency pct (default: 93.0)"
    )
    rbt_parser.add_argument(
        "--opps", type=int, default=120, help="opportunity count (default: 120)"
    )
    rbt_parser.add_argument(
        "--json", action="store_true", help="output route burst evaluation as JSON"
    )

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

    # Pitcher release point drift & variance (REL-DRIFT-01)
    rdr_parser = subparsers.add_parser(
        "rel-drift",
        help="evaluate pitcher spatial release point dispersion and fatigue tells (REL-DRIFT-01)",
    )
    rdr_parser.add_argument(
        "--std-x", type=float, default=1.8, help="std dev rel X in inches (default: 1.8)"
    )
    rdr_parser.add_argument(
        "--std-z", type=float, default=1.6, help="std dev rel Z in inches (default: 1.6)"
    )
    rdr_parser.add_argument(
        "--late-drop", type=float, default=0.8, help="late game arm slot drop in (default: 0.8)"
    )
    rdr_parser.add_argument(
        "--pitches", type=int, default=90, help="pitch count evaluated (default: 90)"
    )
    rdr_parser.add_argument(
        "--json", action="store_true", help="output release drift evaluation as JSON"
    )

    # Batter two-strike expansion resistance (EXP-RESIST-01)
    exp_parser = subparsers.add_parser(
        "exp-resist",
        help="evaluate batter two-strike chase suppression and foul survival (EXP-RESIST-01)",
    )
    exp_parser.add_argument(
        "--chase", type=float, default=34.0, help="2-strike chase pct (default: 34.0)"
    )
    exp_parser.add_argument(
        "--o-contact", type=float, default=56.0, help="2-strike O-contact pct (default: 56.0)"
    )
    exp_parser.add_argument(
        "--foul", type=float, default=42.0, help="2-strike foul pct (default: 42.0)"
    )
    exp_parser.add_argument("--pa", type=int, default=250, help="2-strike PAs (default: 250)")
    exp_parser.add_argument(
        "--json", action="store_true", help="output expansion resistance as JSON"
    )

    # Catcher quick exchange & pop time (CATCH-XCHG-01)
    cxc_parser = subparsers.add_parser(
        "catch-xchg",
        help="evaluate catcher transfer duration, pop time decomposition, and arm (CATCH-XCHG-01)",
    )
    cxc_parser.add_argument(
        "--xchg", type=float, default=0.68, help="exchange time sec (default: 0.68)"
    )
    cxc_parser.add_argument(
        "--velo", type=float, default=82.5, help="throw velo mph (default: 82.5)"
    )
    cxc_parser.add_argument(
        "--flight", type=float, default=1.30, help="flight time sec (default: 1.30)"
    )
    cxc_parser.add_argument("--acc", type=float, default=68.0, help="accuracy pct (default: 68.0)")
    cxc_parser.add_argument(
        "--att", type=int, default=70, help="steal attempts against (default: 70)"
    )
    cxc_parser.add_argument(
        "--json", action="store_true", help="output catcher exchange evaluation as JSON"
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

    # Batter pull-side groundball defense (PULL-GB-01)
    pgb_parser = subparsers.add_parser(
        "pull-gb",
        help="evaluate pull-side groundball defense and optimal infield positioning (PULL-GB-01)",
    )
    pgb_parser.add_argument("--side", type=str, default="L", help="batter side L/R (default: L)")
    pgb_parser.add_argument(
        "--gb-pct", type=float, default=48.0, help="groundball rate pct (default: 48.0)"
    )
    pgb_parser.add_argument(
        "--pull-gb", type=float, default=62.0, help="pull groundball pct (default: 62.0)"
    )
    pgb_parser.add_argument(
        "--oppo-gb", type=float, default=16.0, help="oppo groundball pct (default: 16.0)"
    )
    pgb_parser.add_argument(
        "--hard-pull", type=float, default=38.0, help="hard pull GB pct (default: 38.0)"
    )
    pgb_parser.add_argument(
        "--gb-count", type=int, default=120, help="groundball count (default: 120)"
    )
    pgb_parser.add_argument("--json", action="store_true", help="output pull GB evaluation as JSON")

    # Pitcher top-of-zone VAA deception (VAA-TOZ-01)
    vtz_parser = subparsers.add_parser(
        "vaa-toz",
        help="evaluate top-of-zone VAA angle and rising fastball deception (VAA-TOZ-01)",
    )
    vtz_parser.add_argument("--rel-z", type=float, default=5.6, help="release Z ft (default: 5.6)")
    vtz_parser.add_argument(
        "--velo", type=float, default=96.0, help="pitch velo mph (default: 96.0)"
    )
    vtz_parser.add_argument(
        "--ivb", type=float, default=18.5, help="induced vert break in (default: 18.5)"
    )
    vtz_parser.add_argument(
        "--plate-z", type=float, default=3.35, help="plate crossing Z ft (default: 3.35)"
    )
    vtz_parser.add_argument("--ext", type=float, default=6.8, help="extension ft (default: 6.8)")
    vtz_parser.add_argument("--pitch", type=str, default="FF", help="pitch type (default: FF)")
    vtz_parser.add_argument("--json", action="store_true", help="output VAA TOZ evaluation as JSON")

    # Batter first-pitch ambush damage (AMBUSH-01)
    amb_parser = subparsers.add_parser(
        "ambush",
        help="evaluate batter 0-0 first-pitch aggression and ambush damage (AMBUSH-01)",
    )
    amb_parser.add_argument(
        "--swing", type=float, default=32.0, help="0-0 swing pct (default: 32.0)"
    )
    amb_parser.add_argument(
        "--z-swing", type=float, default=52.0, help="0-0 zone swing pct (default: 52.0)"
    )
    amb_parser.add_argument(
        "--chase", type=float, default=16.0, help="0-0 chase pct (default: 16.0)"
    )
    amb_parser.add_argument(
        "--hard-hit", type=float, default=44.0, help="0-0 hard hit pct (default: 44.0)"
    )
    amb_parser.add_argument("--slg", type=float, default=0.580, help="0-0 SLG (default: 0.580)")
    amb_parser.add_argument("--pa", type=int, default=500, help="total PAs (default: 500)")
    amb_parser.add_argument("--json", action="store_true", help="output ambush evaluation as JSON")

    # Batter spray & elevation rose chart (SPRAY-ROSE-01)
    rose_parser = subparsers.add_parser(
        "spray-rose",
        help="generate vector SVG 3D spray and elevation polar rose chart (SPRAY-ROSE-01)",
    )
    rose_parser.add_argument(
        "--title", type=str, default="Shohei Ohtani Spray & Elevation Rose", help="chart title"
    )
    rose_parser.add_argument("--batter", type=str, default="Shohei Ohtani", help="batter name")

    # Batter contact blast angle & launch window (BLAST-ANGLE-01)
    bla_parser = subparsers.add_parser(
        "blast-angle",
        help="evaluate launch angle window compression and power damage (BLAST-ANGLE-01)",
    )
    bla_parser.add_argument(
        "--mean-la", type=float, default=14.5, help="mean launch angle deg (default: 14.5)"
    )
    bla_parser.add_argument(
        "--std-la", type=float, default=24.0, help="launch angle std deg (default: 24.0)"
    )
    bla_parser.add_argument(
        "--sweet-spot", type=float, default=38.0, help="sweet spot pct (default: 38.0)"
    )
    bla_parser.add_argument(
        "--blast", type=float, default=22.0, help="power blast window pct (default: 22.0)"
    )
    bla_parser.add_argument(
        "--hard-hit", type=float, default=42.0, help="hard hit pct (default: 42.0)"
    )
    bla_parser.add_argument("--bbe", type=int, default=220, help="BBE count (default: 220)")
    bla_parser.add_argument(
        "--json", action="store_true", help="output blast angle evaluation as JSON"
    )

    # Pitcher arsenal velo delta & separation (VELO-DELTA-01)
    vdl_parser = subparsers.add_parser(
        "velo-delta",
        help="evaluate pitcher multi-pitch velocity deltas and disruption (VELO-DELTA-01)",
    )
    vdl_parser.add_argument(
        "--fb-velo", type=float, default=95.0, help="fastball velo mph (default: 95.0)"
    )
    vdl_parser.add_argument(
        "--ch-velo", type=float, default=86.5, help="changeup velo mph (default: 86.5)"
    )
    vdl_parser.add_argument(
        "--sl-velo", type=float, default=87.0, help="slider velo mph (default: 87.0)"
    )
    vdl_parser.add_argument(
        "--cb-velo", type=float, default=79.5, help="curveball velo mph (default: 79.5)"
    )
    vdl_parser.add_argument(
        "--fb-ivb", type=float, default=16.5, help="fastball IVB in (default: 16.5)"
    )
    vdl_parser.add_argument(
        "--ch-ivb", type=float, default=6.0, help="changeup IVB in (default: 6.0)"
    )
    vdl_parser.add_argument(
        "--json", action="store_true", help="output velo delta evaluation as JSON"
    )

    # Outfield throwing arm accuracy & hold rate (ARM-ACCURACY-01)
    arm_acc_parser = subparsers.add_parser(
        "arm-accuracy",
        help="evaluate outfield throwing arm accuracy and runner freeze (ARM-ACCURACY-01)",
    )
    arm_acc_parser.add_argument(
        "--velo", type=float, default=93.0, help="max throw velo mph (default: 93.0)"
    )
    arm_acc_parser.add_argument(
        "--accuracy", type=float, default=68.0, help="on-target throw pct (default: 68.0)"
    )
    arm_acc_parser.add_argument(
        "--assists", type=int, default=8, help="outfield assists (default: 8)"
    )
    arm_acc_parser.add_argument(
        "--hold", type=float, default=54.0, help="runner hold pct (default: 54.0)"
    )
    arm_acc_parser.add_argument(
        "--overthrows", type=int, default=1, help="erratic overthrows (default: 1)"
    )
    arm_acc_parser.add_argument(
        "--opps", type=int, default=140, help="opportunities (default: 140)"
    )
    arm_acc_parser.add_argument("--pos", type=str, default="RF", help="position (default: RF)")
    arm_acc_parser.add_argument(
        "--json", action="store_true", help="output arm accuracy evaluation as JSON"
    )

    # Pitch arsenal separation diamond plot (SEPARATION-PLOT-01)
    sep_parser = subparsers.add_parser(
        "separation-plot",
        help="generate vector SVG arsenal velocity vs movement plot (SEPARATION-PLOT-01)",
    )
    sep_parser.add_argument(
        "--title", type=str, default="Tarik Skubal Arsenal Separation", help="chart title"
    )
    sep_parser.add_argument("--pitcher", type=str, default="Tarik Skubal", help="pitcher name")

    # Pitcher gyro degree & spin axis (GYRO-SPIN-01)
    gyro_parser = subparsers.add_parser(
        "gyro-spin",
        help="calculate pitcher 3D gyro degree and active spin components (GYRO-SPIN-01)",
    )
    gyro_parser.add_argument("--pitch", type=str, default="SL", help="pitch type (default: SL)")
    gyro_parser.add_argument(
        "--spin", type=float, default=2650.0, help="total spin rpm (default: 2650)"
    )
    gyro_parser.add_argument(
        "--eff", type=float, default=22.0, help="spin efficiency pct (default: 22.0)"
    )
    gyro_parser.add_argument(
        "--velo", type=float, default=88.5, help="release velo mph (default: 88.5)"
    )
    gyro_parser.add_argument(
        "--pfx-x", type=float, default=2.0, help="horizontal break inches (default: 2.0)"
    )
    gyro_parser.add_argument(
        "--pfx-z", type=float, default=-1.5, help="induced vert break inches (default: -1.5)"
    )
    gyro_parser.add_argument(
        "--json", action="store_true", help="output gyro spin evaluation as JSON"
    )

    # Batter two-strike approach shortening (TWO-STRIKE-01)
    two_s_parser = subparsers.add_parser(
        "two-strike",
        help="evaluate two-strike swing shortening and contact battle efficiency (TWO-STRIKE-01)",
    )
    two_s_parser.add_argument(
        "--early-whiff", type=float, default=24.0, help="early count whiff pct (default: 24.0)"
    )
    two_s_parser.add_argument(
        "--two-whiff", type=float, default=16.5, help="two strike whiff pct (default: 16.5)"
    )
    two_s_parser.add_argument(
        "--early-len", type=float, default=7.4, help="early swing length ft (default: 7.4)"
    )
    two_s_parser.add_argument(
        "--two-len", type=float, default=6.6, help="two strike swing length ft (default: 6.6)"
    )
    two_s_parser.add_argument(
        "--k-pct", type=float, default=33.0, help="two strike K pct (default: 33.0)"
    )
    two_s_parser.add_argument("--pa", type=int, default=220, help="two strike PAs (default: 220)")
    two_s_parser.add_argument(
        "--json", action="store_true", help="output two-strike evaluation as JSON"
    )

    # Infield double play pivot kinematics (PIVOT-DP-01)
    piv_parser = subparsers.add_parser(
        "pivot-dp",
        help="evaluate middle infield double play pivot turn kinematics (PIVOT-DP-01)",
    )
    piv_parser.add_argument(
        "--turn", type=float, default=0.72, help="pivot turn time seconds (default: 0.72)"
    )
    piv_parser.add_argument(
        "--throw-velo", type=float, default=85.0, help="relay throw velo mph (default: 85.0)"
    )
    piv_parser.add_argument("--turned", type=int, default=60, help="DPs turned (default: 60)")
    piv_parser.add_argument("--opps", type=int, default=80, help="DP opportunities (default: 80)")
    piv_parser.add_argument("--pos", type=str, default="2B", help="position 2B/SS (default: 2B)")
    piv_parser.add_argument(
        "--json", action="store_true", help="output pivot DP evaluation as JSON"
    )

    # Pitch arsenal spin axis clock (SPIN-CLOCK-01)
    clk_parser = subparsers.add_parser(
        "spin-clock",
        help="generate vector SVG 12-hour pitch spin axis clock dial chart (SPIN-CLOCK-01)",
    )
    clk_parser.add_argument(
        "--title", type=str, default="Paul Skenes Arsenal Spin Clock", help="chart title"
    )
    clk_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter contact depth kinematics (CONTACT-DEPTH-01)
    cdp_parser = subparsers.add_parser(
        "contact-depth",
        help="evaluate batter point-of-impact depth and swing timing (CONTACT-DEPTH-01)",
    )
    cdp_parser.add_argument(
        "--depth",
        type=float,
        default=6.5,
        help="contact depth inches relative to plate front (default: 6.5)",
    )
    cdp_parser.add_argument(
        "--velo", type=float, default=94.0, help="pitch velo mph (default: 94.0)"
    )
    cdp_parser.add_argument(
        "--x-loc", type=float, default=-3.0, help="horizontal pitch location inches (default: -3.0)"
    )
    cdp_parser.add_argument(
        "--spray", type=float, default=-25.0, help="batted ball spray angle deg (default: -25.0)"
    )
    cdp_parser.add_argument(
        "--ev", type=float, default=102.0, help="exit velo mph (default: 102.0)"
    )
    cdp_parser.add_argument("--side", type=str, default="R", help="batter side R/L (default: R)")
    cdp_parser.add_argument(
        "--json", action="store_true", help="output contact depth evaluation as JSON"
    )

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

    # Catcher block-to-throw & secondary pop (CATCHER-POP-01)
    cpop_parser = subparsers.add_parser(
        "catcher-pop",
        help="evaluate catcher dirt-ball recovery and BTSV run savings (CATCHER-POP-01)",
    )
    cpop_parser.add_argument(
        "--pop", type=float, default=1.94, help="clean pop time seconds (default: 1.94)"
    )
    cpop_parser.add_argument(
        "--recovery", type=float, default=0.62, help="block recovery time seconds (default: 0.62)"
    )
    cpop_parser.add_argument(
        "--throw-velo", type=float, default=83.5, help="dirt throw velo mph (default: 83.5)"
    )
    cpop_parser.add_argument(
        "--wp-saved", type=int, default=16, help="wild pitches prevented (default: 16)"
    )
    cpop_parser.add_argument(
        "--dirt-cs", type=int, default=3, help="dirt caught stealing (default: 3)"
    )
    cpop_parser.add_argument("--pb", type=int, default=1, help="passed balls (default: 1)")
    cpop_parser.add_argument(
        "--json", action="store_true", help="output catcher pop evaluation as JSON"
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

    # Batter contact expected slugging & ISO (XSLG-01)
    xslg_parser = subparsers.add_parser(
        "xslg",
        help="evaluate contact-binned expected slugging and ISO power (XSLG-01)",
    )
    xslg_parser.add_argument("--barrels", type=int, default=25, help="barrel count (default: 25)")
    xslg_parser.add_argument("--solid", type=int, default=18, help="solid contact (default: 18)")
    xslg_parser.add_argument("--flares", type=int, default=32, help="flares/burners (default: 32)")
    xslg_parser.add_argument("--under", type=int, default=22, help="under flyouts (default: 22)")
    xslg_parser.add_argument(
        "--topped", type=int, default=38, help="topped grounders (default: 38)"
    )
    xslg_parser.add_argument("--weak", type=int, default=15, help="weak contact (default: 15)")
    xslg_parser.add_argument("--iso", type=float, default=0.220, help="actual ISO (default: 0.220)")
    xslg_parser.add_argument("--json", action="store_true", help="output xSLG evaluation as JSON")

    # Pitcher fastball velocity drift (VELO-DRIFT-01)
    vdr_parser = subparsers.add_parser(
        "velo-drift",
        help="evaluate intra-game fastball velocity decay and FVRI (VELO-DRIFT-01)",
    )
    vdr_parser.add_argument(
        "--early", type=float, default=96.5, help="early inn velo mph (default: 96.5)"
    )
    vdr_parser.add_argument(
        "--late", type=float, default=94.5, help="late inn velo mph (default: 94.5)"
    )
    vdr_parser.add_argument("--pitches", type=int, default=90, help="total pitches (default: 90)")
    vdr_parser.add_argument(
        "--early-spin", type=float, default=2400.0, help="early spin rpm (default: 2400)"
    )
    vdr_parser.add_argument(
        "--late-spin", type=float, default=2320.0, help="late spin rpm (default: 2320)"
    )
    vdr_parser.add_argument(
        "--json", action="store_true", help="output velo drift evaluation as JSON"
    )

    # Defensive outfield catch probability (CATCH-PROB-01)
    cp_parser = subparsers.add_parser(
        "catch-prob",
        help="evaluate Statcast 5-star outfield catch probability and OAA (CATCH-PROB-01)",
    )
    cp_parser.add_argument(
        "--dist", type=float, default=65.0, help="distance needed ft (default: 65.0)"
    )
    cp_parser.add_argument(
        "--hang", type=float, default=4.2, help="hang time seconds (default: 4.2)"
    )
    cp_parser.add_argument(
        "--angle", type=float, default=90.0, help="direction angle deg (default: 90.0)"
    )
    cp_parser.add_argument(
        "--speed", type=float, default=28.5, help="sprint speed ft/s (default: 28.5)"
    )
    cp_parser.add_argument("--caught", action="store_true", default=True, help="was caught flag")
    cp_parser.add_argument(
        "--json", action="store_true", help="output catch prob evaluation as JSON"
    )

    # 3D isometric pitch trajectory flight (FLIGHT-3D-01)
    f3d_parser = subparsers.add_parser(
        "flight-3d",
        help="generate vector SVG 3D isometric pitch flight and tunnel chart (FLIGHT-3D-01)",
    )
    f3d_parser.add_argument(
        "--title", type=str, default="Tarik Skubal 3D Pitch Tunnel", help="chart title"
    )
    f3d_parser.add_argument("--pitcher", type=str, default="Tarik Skubal", help="pitcher name")

    # Batter pull-air power (PULL-AIR-01)
    pair_parser = subparsers.add_parser(
        "pull-air",
        help="evaluate pulled-air (FB/LD) power damage multiplier (PULL-AIR-01)",
    )
    pair_parser.add_argument(
        "--pull-air", type=int, default=45, help="pulled air count (default: 45)"
    )
    pair_parser.add_argument(
        "--total-air", type=int, default=110, help="total air count (default: 110)"
    )
    pair_parser.add_argument("--pull-hr", type=int, default=22, help="pulled HRs (default: 22)")
    pair_parser.add_argument("--hr", type=int, default=25, help="total HRs (default: 25)")
    pair_parser.add_argument(
        "--json", action="store_true", help="output pull-air evaluation as JSON"
    )

    # Pitcher horizontal approach angle (HAA-01)
    haa_parser = subparsers.add_parser(
        "haa",
        help="calculate pitch horizontal approach angle and cross-body deception (HAA-01)",
    )
    haa_parser.add_argument("--pitch", type=str, default="ST", help="pitch type (default: ST)")
    haa_parser.add_argument(
        "--rel-x", type=float, default=-2.6, help="release X ft (default: -2.6)"
    )
    haa_parser.add_argument("--plate-x", type=float, default=0.8, help="plate X ft (default: 0.8)")
    haa_parser.add_argument(
        "--hb", type=float, default=17.0, help="horizontal break inches (default: 17.0)"
    )
    haa_parser.add_argument(
        "--velo", type=float, default=83.5, help="release velo mph (default: 83.5)"
    )
    haa_parser.add_argument("--json", action="store_true", help="output HAA evaluation as JSON")

    # Infield bunt defense (BUNT-01)
    bunt_parser = subparsers.add_parser(
        "bunt",
        help="evaluate infield bunt defense and lead runner elimination (BUNT-01)",
    )
    bunt_parser.add_argument(
        "--lead-outs", type=int, default=4, help="lead runner outs (default: 4)"
    )
    bunt_parser.add_argument(
        "--popups", type=int, default=3, help="bunt popups caught (default: 3)"
    )
    bunt_parser.add_argument("--hits", type=int, default=1, help="bunt hits allowed (default: 1)")
    bunt_parser.add_argument(
        "--attempts", type=int, default=22, help="total attempts (default: 22)"
    )
    bunt_parser.add_argument("--pos", type=str, default="3B", help="position (default: 3B)")
    bunt_parser.add_argument("--json", action="store_true", help="output bunt defense as JSON")

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
    babip_parser.add_argument("--ld", type=float, default=0.21, help="Line Drive% (default: 0.21)")
    babip_parser.add_argument(
        "--hard-hit", type=float, default=0.42, help="Hard-Hit% (default: 0.42)"
    )
    babip_parser.add_argument(
        "--speed", type=float, default=27.5, help="Sprint Speed ft/s (default: 27.5)"
    )
    babip_parser.add_argument("--json", action="store_true", help="output BABIP evaluation as JSON")

    # Pitcher vertical approach angle (VAA-01)
    vaa_parser = subparsers.add_parser(
        "vaa",
        help="calculate pitch vertical approach angle and flatness boost (VAA-01)",
    )
    vaa_parser.add_argument("--pitch", type=str, default="FF", help="pitch type (default: FF)")
    vaa_parser.add_argument(
        "--rel-z", type=float, default=5.6, help="release height ft (default: 5.6)"
    )
    vaa_parser.add_argument(
        "--plate-z", type=float, default=3.2, help="plate height ft (default: 3.2)"
    )
    vaa_parser.add_argument("--ivb", type=float, default=18.5, help="IVB inches (default: 18.5)")
    vaa_parser.add_argument(
        "--velo", type=float, default=96.0, help="release velocity mph (default: 96.0)"
    )
    vaa_parser.add_argument("--json", action="store_true", help="output VAA evaluation as JSON")

    # Infield fly ball popup run value (IFFB-01)
    iffb_parser = subparsers.add_parser(
        "iffb",
        help="evaluate pitcher popup induction and automatic out savings (IFFB-01)",
    )
    iffb_parser.add_argument("--iffb", type=int, default=20, help="IFFB count (default: 20)")
    iffb_parser.add_argument("--fb", type=int, default=165, help="total flyballs (default: 165)")
    iffb_parser.add_argument("--pa", type=int, default=620, help="plate appearances (default: 620)")
    iffb_parser.add_argument("--json", action="store_true", help="output IFFB evaluation as JSON")

    # Matchup comparison scouting card (COMPARE-CARD-01)
    card_parser = subparsers.add_parser(
        "matchup-card",
        help="generate vector SVG side-by-side player matchup scouting card (COMPARE-CARD-01)",
    )
    card_parser.add_argument("--batter", type=str, default="Aaron Judge", help="batter name")
    card_parser.add_argument("--pitcher", type=str, default="Gerrit Cole", help="pitcher name")

    # Batter sweet spot contact (SWEETSPOT-01)
    sws_parser = subparsers.add_parser(
        "sweetspot",
        help="evaluate sweet-spot% and ideal contact rate (SWEETSPOT-01)",
    )
    sws_parser.add_argument("--sws", type=float, default=0.36, help="Sweet-Spot% (default: 0.36)")
    sws_parser.add_argument("--hh", type=float, default=0.44, help="Hard-Hit% (default: 0.44)")
    sws_parser.add_argument(
        "--icr", type=float, default=39.5, help="Ideal Contact Rate (default: 39.5)"
    )
    sws_parser.add_argument("--std", type=float, default=23.0, help="LA Std Dev (default: 23.0)")
    sws_parser.add_argument(
        "--json", action="store_true", help="output sweet spot evaluation as JSON"
    )

    # Pitcher two-strike put-away (PUTAWAY-01)
    put_parser = subparsers.add_parser(
        "putaway",
        help="evaluate two-strike put-away conversion rate (PUTAWAY-01)",
    )
    put_parser.add_argument("--putaway", type=float, default=0.22, help="Put-Away% (default: 0.22)")
    put_parser.add_argument(
        "--pitches", type=int, default=650, help="two-strike pitches (default: 650)"
    )
    put_parser.add_argument(
        "--whiff", type=float, default=0.15, help="2-strike whiff% (default: 0.15)"
    )
    put_parser.add_argument("--json", action="store_true", help="output putaway evaluation as JSON")

    # Outfield wall defense (WALL-01)
    wall_parser = subparsers.add_parser(
        "wall",
        help="evaluate outfield wall collision catches and HR robberies (WALL-01)",
    )
    wall_parser.add_argument("--robberies", type=int, default=2, help="HR robberies (default: 2)")
    wall_parser.add_argument(
        "--wall-catches", type=int, default=5, help="wall extra-base catches (default: 5)"
    )
    wall_parser.add_argument("--fails", type=int, default=1, help="failed crashes (default: 1)")
    wall_parser.add_argument("--opps", type=int, default=25, help="opportunities (default: 25)")
    wall_parser.add_argument("--pos", type=str, default="CF", help="position (default: CF)")
    wall_parser.add_argument("--json", action="store_true", help="output wall defense as JSON")

    # Spatial strike zone hexbin map (HEXBIN-01)
    hex_parser = subparsers.add_parser(
        "hexbin",
        help="generate vector SVG 2D strike zone hexbin attack map (HEXBIN-01)",
    )
    hex_parser.add_argument(
        "--title", type=str, default="Shohei Ohtani Spatial Attack Zone", help="chart title"
    )

    # Batter zone swing vulnerability (ZONE-SWING-01)
    zsw_parser = subparsers.add_parser(
        "zone-swing",
        help="evaluate in-zone contact deficit and chase efficiency (ZONE-SWING-01)",
    )
    zsw_parser.add_argument("--z-swing", type=float, default=0.68, help="Z-Swing% (default: 0.68)")
    zsw_parser.add_argument(
        "--z-contact", type=float, default=0.84, help="Z-Contact% (default: 0.84)"
    )
    zsw_parser.add_argument("--o-swing", type=float, default=0.28, help="O-Swing% (default: 0.28)")
    zsw_parser.add_argument(
        "--o-contact", type=float, default=0.58, help="O-Contact% (default: 0.58)"
    )
    zsw_parser.add_argument(
        "--json", action="store_true", help="output zone swing evaluation as JSON"
    )

    # Starting pitcher first-pitch strike (FSTRIKE-01)
    fps_parser = subparsers.add_parser(
        "fstrike",
        help="evaluate first-pitch strike surplus run value (FSTRIKE-01)",
    )
    fps_parser.add_argument("--fps", type=float, default=0.65, help="F-Strike% (default: 0.65)")
    fps_parser.add_argument("--bf", type=int, default=700, help="batters faced (default: 700)")
    fps_parser.add_argument("--json", action="store_true", help="output FPS evaluation as JSON")

    # Catcher pop time (POPTIME-01)
    pop_parser = subparsers.add_parser(
        "pop-time",
        help="evaluate catcher pop time and caught stealing above average (POPTIME-01)",
    )
    pop_parser.add_argument("--pop", type=float, default=1.92, help="pop time s (default: 1.92)")
    pop_parser.add_argument(
        "--arm", type=float, default=86.5, help="arm velocity mph (default: 86.5)"
    )
    pop_parser.add_argument("--att", type=int, default=65, help="attempts faced (default: 65)")
    pop_parser.add_argument(
        "--json", action="store_true", help="output pop time evaluation as JSON"
    )

    # RE24 Matrix Heatmap (RE24-MAP-01)
    re24_parser = subparsers.add_parser(
        "re24-heatmap",
        help="generate vector SVG 24-state run expectancy matrix heatmap (RE24-MAP-01)",
    )
    re24_parser.add_argument(
        "--title", type=str, default="MLB 24-State Run Expectancy Matrix", help="chart title"
    )

    # Batter clutch context (CLUTCH-01)
    clutch_parser = subparsers.add_parser(
        "clutch",
        help="evaluate high-leverage WPA and clutch splits (CLUTCH-01)",
    )
    clutch_parser.add_argument(
        "--overall", type=float, default=0.335, help="overall wOBA (default: 0.335)"
    )
    clutch_parser.add_argument(
        "--pa-high", type=int, default=90, help="high LI PA count (default: 90)"
    )
    clutch_parser.add_argument(
        "--woba-high", type=float, default=0.395, help="high LI wOBA (default: 0.395)"
    )
    clutch_parser.add_argument(
        "--wpa", type=float, default=3.10, help="win probability added (default: 3.10)"
    )
    clutch_parser.add_argument(
        "--pli", type=float, default=1.12, help="average leverage faced (default: 1.12)"
    )
    clutch_parser.add_argument(
        "--json", action="store_true", help="output clutch evaluation as JSON"
    )

    # Defensive outfield arm (ARM-01)
    arm_parser = subparsers.add_parser(
        "arm",
        help="evaluate outfield throw velocity and runner hold rate (ARM-01)",
    )
    arm_parser.add_argument(
        "--velo", type=float, default=98.0, help="arm throw velocity mph (default: 98.0)"
    )
    arm_parser.add_argument(
        "--exchange", type=float, default=0.70, help="exchange transfer time s (default: 0.70)"
    )
    arm_parser.add_argument("--pos", type=str, default="RF", help="outfield position (default: RF)")
    arm_parser.add_argument("--json", action="store_true", help="output arm evaluation as JSON")

    # Pitcher arsenal diversity (ARSENAL-01)
    ars_parser = subparsers.add_parser(
        "arsenal",
        help="evaluate repertoire diversity and count predictability (ARSENAL-01)",
    )
    ars_parser.add_argument("--pitcher", type=str, default="Yu Darvish", help="pitcher name")
    ars_parser.add_argument(
        "--count", type=str, default="ALL_COUNTS", help="count state (default: ALL_COUNTS)"
    )
    ars_parser.add_argument("--json", action="store_true", help="output diversity as JSON")

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

    # Batter spray direction (SPRAY-01)
    spray_parser = subparsers.add_parser(
        "spray",
        help="evaluate directional spray and pull power concentration (SPRAY-01)",
    )
    spray_parser.add_argument("--pull", type=float, default=0.46, help="pull pct (default: 0.46)")
    spray_parser.add_argument(
        "--center", type=float, default=0.32, help="center pct (default: 0.32)"
    )
    spray_parser.add_argument("--oppo", type=float, default=0.22, help="oppo pct (default: 0.22)")
    spray_parser.add_argument(
        "--hr-pull", type=int, default=24, help="pull home runs (default: 24)"
    )
    spray_parser.add_argument(
        "--hr-total", type=int, default=28, help="total home runs (default: 28)"
    )
    spray_parser.add_argument("--json", action="store_true", help="output spray evaluation as JSON")

    # Starting pitcher times through order (TTO-01)
    tto_parser = subparsers.add_parser(
        "tto",
        help="evaluate starter times-through-the-order degradation (TTO-01)",
    )
    tto_parser.add_argument(
        "--tto1-woba", type=float, default=0.280, help="TTO 1 wOBA (default: 0.280)"
    )
    tto_parser.add_argument(
        "--tto2-woba", type=float, default=0.310, help="TTO 2 wOBA (default: 0.310)"
    )
    tto_parser.add_argument(
        "--tto3-woba", type=float, default=0.365, help="TTO 3 wOBA (default: 0.365)"
    )
    tto_parser.add_argument(
        "--tto1-k", type=float, default=0.28, help="TTO 1 K pct (default: 0.28)"
    )
    tto_parser.add_argument(
        "--tto3-k", type=float, default=0.17, help="TTO 3 K pct (default: 0.17)"
    )
    tto_parser.add_argument("--json", action="store_true", help="output TTO evaluation as JSON")

    # Environmental ballpark carry (CARRY-01)
    carry_parser = subparsers.add_parser(
        "carry",
        help="evaluate 30-ballpark trajectory carry and HR clearance (CARRY-01)",
    )
    carry_parser.add_argument(
        "--ev", type=float, default=102.0, help="exit velocity mph (default: 102.0)"
    )
    carry_parser.add_argument(
        "--la", type=float, default=28.0, help="launch angle deg (default: 28.0)"
    )
    carry_parser.add_argument(
        "--spray", type=float, default=35.0, help="spray angle deg (default: 35.0)"
    )
    carry_parser.add_argument(
        "--dist", type=float, default=365.0, help="nominal distance ft (default: 365.0)"
    )
    carry_parser.add_argument("--json", action="store_true", help="output carry evaluation as JSON")

    # Pitch break chart (BREAK-PLOT-01)
    bplot_parser = subparsers.add_parser(
        "break-plot",
        help="generate 2D vector SVG pitch movement break plot (BREAK-PLOT-01)",
    )
    bplot_parser.add_argument("--pitcher", type=str, default="Paul Skenes", help="pitcher name")

    # Batter contact damage (DAMAGE-01)
    dmg_parser = subparsers.add_parser(
        "damage",
        help="evaluate Statcast exit velo and damage rate (DAMAGE-01)",
    )
    dmg_parser.add_argument(
        "--ev", type=float, default=104.5, help="exit velocity mph (default: 104.5)"
    )
    dmg_parser.add_argument(
        "--la", type=float, default=26.0, help="launch angle deg (default: 26.0)"
    )
    dmg_parser.add_argument("--json", action="store_true", help="output damage result as JSON")

    # Live bullpen optimizer (BULLPEN-OPT-01)
    bopt_parser = subparsers.add_parser(
        "bullpen-opt",
        help="optimize live in-game reliever insertion (BULLPEN-OPT-01)",
    )
    bopt_parser.add_argument("--inning", type=int, default=8, help="current inning (default: 8)")
    bopt_parser.add_argument(
        "--score-diff", type=int, default=1, help="score differential (default: 1)"
    )
    bopt_parser.add_argument(
        "--li", type=float, default=2.40, help="leverage index (default: 2.40)"
    )
    bopt_parser.add_argument(
        "--batters", type=str, default="L,L,R", help="upcoming batters hand (default: L,L,R)"
    )
    bopt_parser.add_argument(
        "--json", action="store_true", help="output bullpen optimization as JSON"
    )

    # Pitcher workload fatigue (FATIGUE-01)
    fat_parser = subparsers.add_parser(
        "fatigue",
        help="evaluate acute-to-chronic workload and fatigue risk (FATIGUE-01)",
    )
    fat_parser.add_argument(
        "--pitches-7d", type=int, default=120, help="pitches last 7d (default: 120)"
    )
    fat_parser.add_argument(
        "--pitches-28d", type=int, default=320, help="pitches last 28d (default: 320)"
    )
    fat_parser.add_argument(
        "--velo-delta", type=float, default=-1.4, help="fastball velo delta mph (default: -1.4)"
    )
    fat_parser.add_argument(
        "--release-drop", type=float, default=-1.6, help="release drop in (default: -1.6)"
    )
    fat_parser.add_argument("--json", action="store_true", help="output fatigue evaluation as JSON")

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

    # Batter platoon split shrinkage (PLATOON-01)
    plat_parser = subparsers.add_parser(
        "platoon",
        help="evaluate batter platoon splits with Empirical Bayes (PLATOON-01)",
    )
    plat_parser.add_argument("--bats", type=str, default="L", help="bats hand (L, R, S)")
    plat_parser.add_argument(
        "--overall", type=float, default=0.330, help="overall wOBA (default: 0.330)"
    )
    plat_parser.add_argument("--pa-lhp", type=int, default=150, help="PA vs LHP (default: 150)")
    plat_parser.add_argument(
        "--woba-lhp", type=float, default=0.260, help="wOBA vs LHP (default: 0.260)"
    )
    plat_parser.add_argument("--pa-rhp", type=int, default=450, help="PA vs RHP (default: 450)")
    plat_parser.add_argument(
        "--woba-rhp", type=float, default=0.360, help="wOBA vs RHP (default: 0.360)"
    )
    plat_parser.add_argument("--json", action="store_true", help="output platoon result as JSON")

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

    # Pitched ball spin decomposition (SPIN-01)
    spin_parser = subparsers.add_parser(
        "spin",
        help="decompose raw spin into active vs gyro bullet spin (SPIN-01)",
    )
    spin_parser.add_argument(
        "--pitch-type", type=str, default="SL", help="pitch type (default: SL)"
    )
    spin_parser.add_argument(
        "--spin", type=float, default=2600.0, help="total spin rpm (default: 2600)"
    )
    spin_parser.add_argument(
        "--efficiency", type=float, default=35.0, help="spin efficiency pct (default: 35.0)"
    )
    spin_parser.add_argument("--json", action="store_true", help="output spin result as JSON")

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

    # Batter swing decisions and plate discipline (DECISION-01)
    dec_parser = subparsers.add_parser(
        "decision",
        help="evaluate batter swing decisions and SDV (DECISION-01)",
    )
    dec_parser.add_argument(
        "--heart-swing", type=float, default=0.78, help="heart zone swing pct (default: 0.78)"
    )
    dec_parser.add_argument(
        "--shadow-swing", type=float, default=0.50, help="shadow zone swing pct (default: 0.50)"
    )
    dec_parser.add_argument(
        "--chase-swing", type=float, default=0.18, help="chase zone swing pct (default: 0.18)"
    )
    dec_parser.add_argument(
        "--waste-swing", type=float, default=0.05, help="waste zone swing pct (default: 0.05)"
    )
    dec_parser.add_argument("--json", action="store_true", help="output decision result as JSON")

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

    # Pitcher physical extension and effective velocity (EXT-01)
    ext_parser = subparsers.add_parser(
        "extension",
        help="evaluate pitcher extension and effective velocity (EXT-01)",
    )
    ext_parser.add_argument(
        "--velo", type=float, default=95.0, help="radar velocity mph (default: 95.0)"
    )
    ext_parser.add_argument("--ext", type=float, default=7.2, help="extension feet (default: 7.2)")
    ext_parser.add_argument("--json", action="store_true", help="output extension result as JSON")

    # Bullpen leverage and closer volatility (LEV-01)
    lev_parser = subparsers.add_parser(
        "leverage",
        help="evaluate closer blown-save volatility index (LEV-01)",
    )
    lev_parser.add_argument(
        "--k-pct", type=float, default=0.34, help="strikeout pct (default: 0.34)"
    )
    lev_parser.add_argument("--bb-pct", type=float, default=0.06, help="walk pct (default: 0.06)")
    lev_parser.add_argument("--hr9", type=float, default=0.65, help="HR per 9 (default: 0.65)")
    lev_parser.add_argument("--json", action="store_true", help="output leverage result as JSON")

    # Seam-shifted wake aerodynamics (SSW-01)
    ssw_parser = subparsers.add_parser(
        "ssw",
        help="evaluate pitch seam-shifted wake aerodynamics (SSW-01)",
    )
    ssw_parser.add_argument(
        "--pitch-type", type=str, default="SI", help="pitch type (SI, SL, FF, CH)"
    )
    ssw_parser.add_argument("--velo", type=float, default=94.5, help="velocity mph (default: 94.5)")
    ssw_parser.add_argument(
        "--spin", type=float, default=2150, help="spin rate rpm (default: 2150)"
    )
    ssw_parser.add_argument(
        "--obs-ivb", type=float, default=6.5, help="observed IVB in (default: 6.5)"
    )
    ssw_parser.add_argument(
        "--obs-hb", type=float, default=17.5, help="observed HB in (default: 17.5)"
    )
    ssw_parser.add_argument(
        "--axis", type=float, default=45.0, help="spin axis degrees (default: 45.0)"
    )
    ssw_parser.add_argument("--json", action="store_true", help="output SSW result as JSON")

    # Catcher blocking and passed ball run value (BLOCK-01)
    block_parser = subparsers.add_parser(
        "block",
        help="evaluate catcher blocking and wild pitch run cost (BLOCK-01)",
    )
    block_parser.add_argument(
        "--catcher-runs", type=float, default=4.0, help="catcher blocking runs (default: 4.0)"
    )
    block_parser.add_argument(
        "--spikes", type=float, default=12.0, help="pitcher dirt pitches per game (default: 12.0)"
    )
    block_parser.add_argument(
        "--json", action="store_true", help="output blocking evaluation as JSON"
    )

    # Doubleheader and travel fatigue decay (TRAVEL-01)
    travel_parser = subparsers.add_parser(
        "travel",
        help="assess team travel fatigue and doubleheader drag (TRAVEL-01)",
    )
    travel_parser.add_argument("--tz", type=int, default=2, help="time zones crossed (default: 2)")
    travel_parser.add_argument(
        "--rest-hours", type=float, default=14.0, help="hours rest (default: 14.0)"
    )
    travel_parser.add_argument("--is-dh2", action="store_true", help="is doubleheader game 2")
    travel_parser.add_argument(
        "--consecutive-days", type=int, default=10, help="consecutive game days (default: 10)"
    )
    travel_parser.add_argument("--json", action="store_true", help="output travel fatigue as JSON")

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

    # Base stealing kinematics and disengagement physics (SB-01)
    steal_parser = subparsers.add_parser(
        "steal",
        help="evaluate base stealing kinematics and disengagements (SB-01)",
    )
    steal_parser.add_argument(
        "--sprint", type=float, default=28.5, help="runner sprint speed ft/s (default: 28.5)"
    )
    steal_parser.add_argument(
        "--delivery", type=float, default=1.30, help="pitcher delivery time s (default: 1.30)"
    )
    steal_parser.add_argument(
        "--pop-time", type=float, default=1.95, help="catcher pop time s (default: 1.95)"
    )
    steal_parser.add_argument(
        "--disengagements", type=int, default=0, help="pitcher disengagements (0, 1, 2)"
    )
    steal_parser.add_argument("--outs", type=int, default=1, help="outs (default: 1)")
    steal_parser.add_argument("--json", action="store_true", help="output steal result as JSON")

    # Pitch sequencing Shannon entropy (ENTROPY-01)
    entropy_parser = subparsers.add_parser(
        "entropy",
        help="calculate pitch sequencing Shannon entropy (ENTROPY-01)",
    )
    entropy_parser.add_argument(
        "--fastball", type=float, default=0.50, help="fastball share (default: 0.50)"
    )
    entropy_parser.add_argument(
        "--slider", type=float, default=0.30, help="slider share (default: 0.30)"
    )
    entropy_parser.add_argument(
        "--changeup", type=float, default=0.20, help="changeup share (default: 0.20)"
    )
    entropy_parser.add_argument("--json", action="store_true", help="output entropy as JSON")

    # Skill component aging projections (AGE-02)
    aging_parser = subparsers.add_parser(
        "aging",
        help="project multi-year skill component aging trajectories (AGE-02)",
    )
    aging_parser.add_argument("--age", type=float, default=27.0, help="current age (default: 27.0)")
    aging_parser.add_argument("--is-pitcher", action="store_true", help="player is pitcher")
    aging_parser.add_argument(
        "--velo", type=float, default=95.0, help="fastball velo mph (default: 95.0)"
    )
    aging_parser.add_argument(
        "--woba", type=float, default=0.340, help="wOBA / FIP baseline (default: 0.340)"
    )
    aging_parser.add_argument("--json", action="store_true", help="output aging projection as JSON")

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

    # Count state Markov simulation (COUNT-01)
    count_parser = subparsers.add_parser(
        "count",
        help="simulate pitch-by-pitch count state progression (COUNT-01)",
    )
    count_parser.add_argument("--balls", type=int, default=0, help="starting balls (default: 0)")
    count_parser.add_argument(
        "--strikes", type=int, default=0, help="starting strikes (default: 0)"
    )
    count_parser.add_argument(
        "--whiff-rate", type=float, default=0.25, help="whiff rate (default: 0.25)"
    )
    count_parser.add_argument("--json", action="store_true", help="output count simulation as JSON")

    # Defensive alignment and BABIP suppression (SHIFT-01)
    shift_parser = subparsers.add_parser(
        "shift",
        help="evaluate defensive alignment and spray suppression (SHIFT-01)",
    )
    shift_parser.add_argument(
        "--alignment",
        choices=["standard", "shaded_pull", "infield_in", "outfield_deep"],
        default="shaded_pull",
        help="alignment",
    )
    shift_parser.add_argument(
        "--pull-pct", type=float, default=0.52, help="batter ground ball pull pct (default: 0.52)"
    )
    shift_parser.add_argument(
        "--team-oaa", type=float, default=6.0, help="team infield OAA (default: 6.0)"
    )
    shift_parser.add_argument("--json", action="store_true", help="output shift evaluation as JSON")

    # Late-inning tactical substitution simulator (SUB-01)
    sub_parser = subparsers.add_parser(
        "sub",
        help="simulate manager late-inning pinch-hit decisions (SUB-01)",
    )
    sub_parser.add_argument("--inning", type=int, default=8, help="game inning (default: 8)")
    sub_parser.add_argument(
        "--leverage", type=float, default=1.8, help="leverage index (default: 1.8)"
    )
    sub_parser.add_argument(
        "--pitcher-hand", choices=["R", "L"], default="L", help="opposing pitcher hand (default: L)"
    )
    sub_parser.add_argument("--json", action="store_true", help="output pinch hit decision as JSON")

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

    # Win Expectancy and WPA calculator (MATH-01)
    wpa_parser = subparsers.add_parser(
        "wpa", help="calculate in-game Win Expectancy and Leverage Index for any game state"
    )
    wpa_parser.add_argument("--inning", type=int, default=1, help="current inning (1..15)")
    wpa_parser.add_argument("--bottom", action="store_true", help="bottom half of inning")
    wpa_parser.add_argument("--outs", type=int, choices=[0, 1, 2], default=0, help="current outs")
    wpa_parser.add_argument("--on1", action="store_true", help="runner on 1st base")
    wpa_parser.add_argument("--on2", action="store_true", help="runner on 2nd base")
    wpa_parser.add_argument("--on3", action="store_true", help="runner on 3rd base")
    wpa_parser.add_argument("--home-score", type=int, default=0, help="home team score")
    wpa_parser.add_argument("--away-score", type=int, default=0, help="away team score")
    wpa_parser.add_argument("--json", action="store_true", help="output result as JSON")

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
        "props", help="forecast player proposition markets (K%, outs, hits, HR)"
    )
    props_parser.add_argument("--game-pk", type=str, help="target MLB game PK to look up starters")
    props_parser.add_argument("--pitcher-k", type=float, help="manual starter K% (e.g. 0.28)")
    props_parser.add_argument(
        "--opp-k", type=float, default=0.225, help="opposing lineup K% (default: 0.225)"
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
        from mlb_baseball.daily import generate_daily_briefing
        from mlb_baseball.db import get_connection
        from mlb_baseball.export import (
            ChartSectionBuilder,
            KeyValueSectionBuilder,
            ResearchDossier,
            TableSectionBuilder,
            get_renderer,
        )

        with get_connection() as conn:
            d_report = generate_daily_briefing(target_date=args.date, conn=conn)

        dossier = ResearchDossier(
            title="MLB Quantitative Research & Matchup Dossier",
            subtitle=(
                f"Target Date: {d_report.target_date} (Generated UTC: {d_report.generated_at})"
            ),
        )

        # 1. Health Status Section
        health_pairs = [
            (c.name, "PASS" if c.ok else f"FAIL ({c.detail})") for c in d_report.health_status
        ]
        dossier.add_section(KeyValueSectionBuilder("Operational Health Verification", health_pairs))

        # 2. Matchup Forecasts Section
        if d_report.matchups:
            m_headers = ["Matchup", "Home Win%", "Away Win%", "Home Starter", "Away Starter"]
            m_rows = [
                [
                    f"{m.away_team} @ {m.home_team}",
                    f"{m.model_home_win_prob * 100:.1f}%",
                    f"{m.model_away_win_prob * 100:.1f}%",
                    m.home_starter or "TBD",
                    m.away_starter or "TBD",
                ]
                for m in d_report.matchups
            ]
            dossier.add_section(
                TableSectionBuilder("Today's Matchup Forecasts (GBM-v2 + Log5)", m_headers, m_rows)
            )

        # 3. Pitcher Strikeout Props Chart Section
        if d_report.pitcher_props:
            chart_items = [
                (f"{p.pitcher_name} ({p.team})", round(p.projected_k_pct * 100.0, 1))
                for p in d_report.pitcher_props
            ]
            dossier.add_section(
                ChartSectionBuilder("Projected Pitcher Strikeout Rates (K%)", chart_items, unit="%")
            )

        # 4. Kelly Allocations Section
        if d_report.portfolio_plan and d_report.portfolio_plan.recommendations:
            k_headers = [
                "Market / Matchup",
                "Model%",
                "Market%",
                "Edge%",
                "Kelly%",
                "Wager ($)",
                "+EV%",
            ]
            k_rows = [
                [
                    r.opportunity.description,
                    f"{r.opportunity.model_probability * 100:.1f}%",
                    f"{r.opportunity.market_implied_probability * 100:.1f}%",
                    f"{r.opportunity.edge * 100:+.1f}%",
                    f"{r.kelly_fraction * 100:.2f}%",
                    f"${r.wager_amount_usd:,.2f}",
                    f"{r.expected_value_pct * 100:+.1f}%",
                ]
                for r in d_report.portfolio_plan.recommendations
            ]
            dossier.add_section(
                TableSectionBuilder(
                    f"Kelly Criterion Capital Allocation "
                    f"(Bankroll: ${d_report.portfolio_plan.total_bankroll_usd:,.2f})",
                    k_headers,
                    k_rows,
                )
            )

        if args.format == "json":
            rendered = dossier.to_json()
        else:
            renderer = get_renderer(args.format)
            rendered = dossier.export(renderer)

        if args.output:
            with open(args.output, "w") as out_f:
                out_f.write(rendered)
            print(f"Dossier successfully exported to: {args.output}")
        else:
            print(rendered)

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

    elif args.command == "cluster":
        import json as json_lib

        from mlb_baseball.model.cluster import PitcherRepertoireVector, PitcherSimilarityEngine

        sim_eng = PitcherSimilarityEngine()
        tgt_p = PitcherRepertoireVector(
            "t1", "Target Pitcher", 2024, args.velo, args.ivb, -7.5, -9.0, 6.4
        )
        cand_lib = [
            PitcherRepertoireVector(
                "c1", "Ace Comps 1", 2023, args.velo - 0.3, args.ivb - 0.2, -7.2, -8.8, 6.3
            ),
            PitcherRepertoireVector(
                "c2", "Ace Comps 2", 2022, args.velo + 0.8, args.ivb + 0.5, -8.0, -9.5, 6.6
            ),
        ]
        top_comps = sim_eng.find_pitcher_comps(tgt_p, cand_lib, top_k=2)

        if args.json:
            c_out = [
                {
                    "pitcher_name": m.matched_pitcher_name,
                    "season": m.matched_season,
                    "similarity_pct": m.similarity_score_pct,
                    "distance": m.distance,
                    "deltas": m.feature_deltas,
                }
                for m in top_comps
            ]
            print(json_lib.dumps(c_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print("     HISTORICAL PITCHER SIMILARITY COMPS")
            print(f"     Target: {args.velo:.1f} mph | IVB: {args.ivb:+.1f} in")
            print(f"{'=' * 84}\n")
            for idx, c in enumerate(top_comps, 1):
                pname = c.matched_pitcher_name
                print(f"  #{idx} {pname} ({c.matched_season}): {c.similarity_score_pct:.1f}%")
            print("")

    elif args.command == "dump":
        from mlb_baseball.dump import PlayerDataDumpEngine, PlayerDossierDump

        dump_engine = PlayerDataDumpEngine()
        sample_dossier = PlayerDossierDump(
            player_id="660271",
            player_name="Shohei Ohtani",
            season=2024,
            position_type="batter",
            team_abbrev="LAD",
            primary_metrics={"woba": 0.425, "wrc_plus": 182.0, "barrel_pct": 0.198},
            stuff_arsenal={"stuff_plus": 115.0, "pitching_plus": 112.0},
            projection={"projected_woba": 0.405},
            zone_whiff_rates={1: 0.15, 2: 0.12, 3: 0.28},
        )
        if args.format == "csv":
            print(dump_engine.export_csv([sample_dossier]))
        else:
            print(dump_engine.export_json([sample_dossier]))

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

    elif args.command == "bvp":
        import json as json_lib

        from mlb_baseball.model.bvp import (
            BatterArsenalPreferences,
            EmpiricalBayesBvPEngine,
            PitcherArsenalMix,
        )

        bvp_eng = EmpiricalBayesBvPEngine()
        bvp_res = bvp_eng.evaluate_matchup(
            batter_id="b1",
            batter_name="Target Batter",
            pitcher_id="p1",
            pitcher_name="Target Pitcher",
            batter_woba_vs_hand=args.batter_woba,
            pitcher_woba_vs_hand=args.pitcher_woba,
            observed_pa=args.pa,
            observed_woba=args.raw_woba,
            batter_prefs=BatterArsenalPreferences(rv_slider=+1.5),
            pitcher_mix=PitcherArsenalMix(pct_slider=0.35),
        )

        if args.json:
            b_out = {
                "observed_pa": bvp_res.observed_pa,
                "raw_woba": bvp_res.raw_bvp_woba,
                "platoon_prior_woba": bvp_res.platoon_prior_woba,
                "shrunk_bvp_woba": bvp_res.shrunk_bvp_woba,
                "arsenal_rv100": bvp_res.arsenal_interaction_rv100,
                "composite_woba": bvp_res.composite_matchup_woba,
                "expected_k_pct": bvp_res.expected_k_pct,
                "expected_bb_pct": bvp_res.expected_bb_pct,
            }
            print(json_lib.dumps(b_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print("     BATTER VS PITCHER (BvP) ARSENAL INTERACTION")
            obs_str = (
                f"  {args.pa} PA @ {args.raw_woba:.3f} | Prior: {bvp_res.platoon_prior_woba:.3f}"
            )
            print(obs_str)
            print(f"{'=' * 84}\n")
            print(
                f"  • Shrunk BvP wOBA      : {bvp_res.shrunk_bvp_woba:.3f} (Regressed toward prior)"
            )
            print(f"  • Arsenal Interaction  : {bvp_res.arsenal_interaction_rv100:+.2f} RV/100")
            print(f"  • Composite Matchup    : {bvp_res.composite_matchup_woba:.3f} wOBA")
            kbb_str = (
                f"  • Expected K/BB        : {bvp_res.expected_k_pct * 100:.0f}% / "
                f"{bvp_res.expected_bb_pct * 100:.0f}%\n"
            )
            print(kbb_str)

    elif args.command == "umpire":
        import json as json_lib

        from mlb_baseball.model.umpire import UmpireBiasEngine, UmpireProfile

        u_eng = UmpireBiasEngine()
        u_prof = UmpireProfile(
            umpire_id="u1",
            umpire_name=args.name,
            games_behind_plate=110,
            zone_horizontal_expansion_in=args.expansion_in,
            zone_vertical_expansion_in=0.10,
            called_strike_accuracy_pct=92.8,
            run_impact_per_game=round(-0.55 * (args.expansion_in / 0.6), 2),
            k_rate_multiplier=round(1.0 + (args.expansion_in * 0.08), 2),
            bb_rate_multiplier=round(1.0 - (args.expansion_in * 0.08), 2),
        )
        u_adj = u_eng.evaluate_game_adjustment(u_prof, baseline_total=args.base_total)

        if args.json:
            u_out = {
                "umpire_name": u_adj.umpire_name,
                "baseline_total": u_adj.baseline_total_runs,
                "adjusted_total": u_adj.adjusted_total_runs,
                "run_delta": u_adj.run_adjustment_delta,
                "classification": u_adj.zone_classification,
            }
            print(json_lib.dumps(u_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     UMPIRE STRIKE ZONE & TOTALS IMPACT ({u_adj.umpire_name.upper()})")
            print(f"  Zone: {args.expansion_in:+.1f} in | [{u_adj.zone_classification.upper()}]")
            print(f"{'=' * 84}\n")
            print(f"  • Baseline Total Runs : {u_adj.baseline_total_runs:.1f}")
            ft_str = (
                f"  • Fair Total          : {u_adj.adjusted_total_runs:.2f} "
                f"({u_adj.run_adjustment_delta:+.2f})"
            )
            print(ft_str)
            print(f"  • Starter K Multiplier: {u_prof.k_rate_multiplier:.2f}x\n")

    elif args.command == "weather":
        import json as json_lib

        from mlb_baseball.model.weather import (
            StadiumOrientation,
            StadiumWeatherPhysicsEngine,
            WeatherConditions,
        )

        w_eng = StadiumWeatherPhysicsEngine()
        s_ori = StadiumOrientation(
            "v1",
            "Custom Venue",
            home_to_center_azimuth_deg=args.azimuth,
            altitude_feet=args.altitude,
        )
        w_cond = WeatherConditions(
            temperature_f=args.temp,
            wind_speed_mph=args.wind_speed,
            wind_from_direction_deg=args.wind_dir,
        )
        w_res = w_eng.compute_weather_impact(s_ori, w_cond)

        if args.json:
            w_out = {
                "tailwind_mph": w_res.effective_tailwind_mph,
                "crosswind_mph": w_res.effective_crosswind_mph,
                "adi": w_res.air_density_index,
                "distance_delta_ft": w_res.fly_ball_distance_delta_ft,
                "hr_multiplier": w_res.home_run_multiplier,
                "total_runs_multiplier": w_res.total_runs_multiplier,
            }
            print(json_lib.dumps(w_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print("     STADIUM 3D VECTOR WIND & MICRO-CLIMATE PHYSICS")
            w_hdr = f"  Az: {args.azimuth:.0f}° | Wind: {args.wind_speed:.0f}mph"
            print(w_hdr)
            print(f"{'=' * 84}\n")
            print(f"  • Tailwind Vector      : {w_res.effective_tailwind_mph:+.1f} mph")
            print(f"  • Air Density Index    : {w_res.air_density_index:.1f} (100=Std)")
            print(f"  • Distance Delta       : {w_res.fly_ball_distance_delta_ft:+.1f} ft")
            print(f"  • Home Run Multiplier  : {w_res.home_run_multiplier:.2f}x")
            print(f"  • Game Total Multiplier: {w_res.total_runs_multiplier:.2f}x\n")

    elif args.command == "bullpen":
        import json as json_lib

        from mlb_baseball.model.reliever import (
            BullpenWorkloadHierarchyEngine,
            RelieverProfile,
            RelieverRole,
        )

        bp_eng = BullpenWorkloadHierarchyEngine()
        sample_arms = [
            RelieverProfile(
                "r1",
                "Ace Closer",
                RelieverRole.CLOSER,
                true_talent_fip=2.60,
                true_talent_k_pct=0.35,
                pitches_yesterday=28,
                pitches_2d_ago=18,
            ),
            RelieverProfile(
                "r2",
                "Primary Setup",
                RelieverRole.SETUP,
                true_talent_fip=3.10,
                true_talent_k_pct=0.31,
                pitches_yesterday=0,
                pitches_2d_ago=12,
            ),
            RelieverProfile(
                "r3",
                "High Lev Arm",
                RelieverRole.HIGH_LEVERAGE,
                true_talent_fip=3.40,
                true_talent_k_pct=0.28,
                pitches_yesterday=0,
                pitches_2d_ago=0,
            ),
        ]
        bp_proj, bp_states = bp_eng.evaluate_bullpen(
            args.team.lower(), args.team.upper(), sample_arms
        )

        if args.json:
            bp_out = {
                "team": bp_proj.team_abbrev,
                "closer_status": bp_proj.closer_status.value,
                "setup_status": bp_proj.setup_status.value,
                "avail_high_lev_count": bp_proj.available_high_leverage_count,
                "expected_fip_today": bp_proj.expected_bullpen_fip_today,
                "fip_penalty": bp_proj.fip_penalty_delta,
            }
            print(json_lib.dumps(bp_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     DYNAMIC BULLPEN FATIGUE & HIERARCHY ({bp_proj.team_abbrev})")
            bp_hdr = (
                f"  Fatigue: {bp_proj.total_bullpen_fatigue_score:.0f} | "
                f"HL: {bp_proj.available_high_leverage_count}"
            )
            print(bp_hdr)
            print(f"{'=' * 84}\n")
            print(f"  • Closer Status        : [{bp_proj.closer_status.value.upper()}]")
            print(f"  • Setup Man Status     : [{bp_proj.setup_status.value.upper()}]")
            fip_str = (
                f"  • Expected FIP         : {bp_proj.expected_bullpen_fip_today:.2f} "
                f"({bp_proj.fip_penalty_delta:+.2f})"
            )
            print(fip_str)

    elif args.command == "oppo-liner":
        import json as json_lib

        from mlb_baseball.model.oppo_liner import (
            BatterOppoLinerEngine,
            BatterOppoLinerMetrics,
            OppoLinerEvaluationResult,
        )

        ol_eng = BatterOppoLinerEngine()
        ol_m = BatterOppoLinerMetrics(
            "b1",
            "Target Batter",
            oppo_line_drive_pct=args.ld,
            oppo_liner_babip=args.babip,
            oppo_liner_hard_hit_pct=args.hard,
            oppo_contact_events=args.events,
        )
        ol_res: OppoLinerEvaluationResult = ol_eng.evaluate_oppo_liner(ol_m)

        if args.json:
            ol_out = {
                "ofldii_score": ol_res.ofldii_score,
                "olpr_runs": ol_res.olpr_runs_produced,
                "tier": ol_res.liner_tier,
                "is_artist": ol_res.is_line_drive_artist,
            }
            print(json_lib.dumps(ol_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OPPOSITE-FIELD LINE DRIVE MASTERY [{ol_res.liner_tier}]")
            hdr_ol = (
                f"     OFLDII Score: {ol_res.ofldii_score:.1f}/160 "
                f"| Runs Produced: {ol_res.olpr_runs_produced:>+4.2f} "
                f"| Line Drive Artist: {'YES' if ol_res.is_line_drive_artist else 'NO'}"
            )
            print(hdr_ol)
            print(f"{'=' * 84}\n")
            print(f"  • Liner Profile        : {ol_res.liner_tier}\n")

    elif args.command == "slot-sag":
        import json as json_lib

        from mlb_baseball.model.slot_sag import (
            PitcherSlotSagEngine,
            PitcherSlotSagMetrics,
            SlotSagEvaluationResult,
        )

        ss_eng = PitcherSlotSagEngine()
        ss_m = PitcherSlotSagMetrics(
            "p1",
            "Target Pitcher",
            early_arm_slot_angle_deg=args.early_deg,
            late_arm_slot_angle_deg=args.late_deg,
            early_release_x_in=args.early_x,
            late_release_x_in=args.late_x,
            late_pitches_thrown=args.pitches,
        )
        ss_res: SlotSagEvaluationResult = ss_eng.evaluate_slot_sag(ss_m)

        if args.json:
            ss_out = {
                "asfsi_score": ss_res.asfsi_score,
                "fsdrs_runs": ss_res.fsdrs_runs_saved,
                "tier": ss_res.sag_tier,
                "is_replicator": ss_res.is_slot_replicator,
            }
            print(json_lib.dumps(ss_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     ARM SLOT FATIGUE SAG & LATERAL DRIFT [{ss_res.sag_tier}]")
            hdr_ss = (
                f"     ASFSI Score: {ss_res.asfsi_score:.1f}/160 "
                f"| Runs Saved: {ss_res.fsdrs_runs_saved:>+4.2f} "
                f"| Replicator: {'YES' if ss_res.is_slot_replicator else 'NO'}"
            )
            print(hdr_ss)
            print(f"{'=' * 84}\n")
            print(f"  • Stability Profile    : {ss_res.sag_tier}\n")

    elif args.command == "wall-leap":
        import json as json_lib

        from mlb_baseball.model.wall_leap import (
            OutfielderWallLeapEngine,
            OutfielderWallLeapMetrics,
            WallLeapEvaluationResult,
        )

        wl_eng = OutfielderWallLeapEngine()
        wl_m = OutfielderWallLeapMetrics(
            "f1",
            "Target Fielder",
            vertical_leap_apex_in=args.apex,
            leap_timing_precision_ms=args.timing,
            above_wall_catch_pct=args.catch,
            wall_leap_opportunities=args.opps,
        )
        wl_res: WallLeapEvaluationResult = wl_eng.evaluate_wall_leap(wl_m)

        if args.json:
            wl_out = {
                "wltei_score": wl_res.wltei_score,
                "rrvaa_runs": wl_res.rrvaa_runs_saved,
                "tier": wl_res.leap_tier,
                "is_thief": wl_res.is_wall_thief,
            }
            print(json_lib.dumps(wl_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELDER WALL LEAP & ROBBERY TIMING [{wl_res.leap_tier}]")
            hdr_wl = (
                f"     WLTEI Score: {wl_res.wltei_score:.1f}/160 "
                f"| Runs Saved: {wl_res.rrvaa_runs_saved:>+4.2f} "
                f"| Wall Thief: {'YES' if wl_res.is_wall_thief else 'NO'}"
            )
            print(hdr_wl)
            print(f"{'=' * 84}\n")
            print(f"  • Leap Profile         : {wl_res.leap_tier}\n")

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

    elif args.command == "lineup-protect":
        import json as json_lib

        from mlb_baseball.model.lineup_protect import (
            BatterLineupProtectionEngine,
            BatterProtectionMetrics,
        )

        lp_eng = BatterLineupProtectionEngine()
        lp_m = BatterProtectionMetrics(
            "b1",
            "CLI Batter",
            on_deck_woba=args.woba,
            zone_pct=args.zone,
            first_pitch_strike_pct=args.fstrike,
            pa_count=args.pa,
        )
        lp_r = lp_eng.evaluate_protection(lp_m)
        if args.json:
            print(json_lib.dumps(dataclasses.asdict(lp_r), indent=2))
        else:
            print(f"PII Score: {lp_r.pii_score:.1f}")
            print(f"LPRV Runs: {lp_r.lprv_runs:+.2f}")
            print(f"Tier: {lp_r.protection_tier}")

    elif args.command == "bullpen-bridge":
        import json as json_lib

        from mlb_baseball.model.bullpen_bridge import (
            BullpenBridgeEngine,
            BullpenBridgeMetrics,
        )

        bb_eng = BullpenBridgeEngine()
        bb_m = BullpenBridgeMetrics(
            "t1",
            "CLI Team",
            hold_pct=args.hold,
            leverage_match_rate=args.leverage,
            inherited_score_pct=args.inherited,
            high_leverage_innings=args.innings,
        )
        bb_r = bb_eng.evaluate_bridge(bb_m)
        if args.json:
            print(json_lib.dumps(dataclasses.asdict(bb_r), indent=2))
        else:
            print(f"BSEI Score: {bb_r.bsei_score:.1f}")
            print(f"HLHRS Runs Saved: {bb_r.hlhrs_runs_saved:+.2f}")
            print(f"Tier: {bb_r.bridge_tier}")

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

    elif args.command == "swing-tempo":
        import json as json_lib

        from mlb_baseball.model.swing_tempo import (
            BatterSwingTempoEngine,
            BatterSwingTempoMetrics,
        )

        swt_eng = BatterSwingTempoEngine()
        swt_m = BatterSwingTempoMetrics(
            "b1",
            "CLI Batter",
            timing_std_ms=args.std,
            bat_speed_consistency_pct=args.consistency,
            late_count_contact_pct=args.contact,
            total_swings=args.swings,
        )
        swt_r = swt_eng.evaluate_tempo(swt_m)
        if args.json:
            print(json_lib.dumps(dataclasses.asdict(swt_r), indent=2))
        else:
            print(f"STCI Score: {swt_r.stci_score:.1f}")
            print(f"LSAR Runs: {swt_r.lsar_runs:+.2f}")
            print(f"Tier: {swt_r.tempo_tier}")

    elif args.command == "chase-recog":
        import json as json_lib

        from mlb_baseball.model.chase_recog import (
            BatterChaseRecogEngine,
            BatterChaseRecogMetrics,
            ChaseRecogEvaluationResult,
        )

        cr_eng = BatterChaseRecogEngine()
        cr_m = BatterChaseRecogMetrics(
            "b1",
            "Target Batter",
            breaking_ball_chase_pct=args.chase,
            breaking_ball_take_correct_pct=args.take,
            breaking_ball_waste_whiff_pct=args.whiff,
            out_of_zone_breaking_pitches=args.pitches,
        )
        cr_res: ChaseRecogEvaluationResult = cr_eng.evaluate_chase_recog(cr_m)

        if args.json:
            cr_out = {
                "bbcri_score": cr_res.bbcri_score,
                "cdra_runs": cr_res.cdra_runs_produced,
                "tier": cr_res.recognition_tier,
                "is_hawk": cr_res.is_discipline_hawk,
            }
            print(json_lib.dumps(cr_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BREAKING BALL CHASE DISCIPLINE [{cr_res.recognition_tier}]")
            hdr_cr = (
                f"     BBCRI Score: {cr_res.bbcri_score:.1f}/160 "
                f"| Runs Produced: {cr_res.cdra_runs_produced:>+4.2f} "
                f"| Discipline Hawk: {'YES' if cr_res.is_discipline_hawk else 'NO'}"
            )
            print(hdr_cr)
            print(f"{'=' * 84}\n")
            print(f"  • Recognition Profile  : {cr_res.recognition_tier}\n")

    elif args.command == "first-pitch-ambush":
        import json as json_lib

        from mlb_baseball.model.first_pitch_ambush import (
            FirstPitchAmbushEvaluationResult,
            PitcherFirstPitchAmbushEngine,
            PitcherFirstPitchAmbushMetrics,
        )

        fpa_eng = PitcherFirstPitchAmbushEngine()
        fpa_m = PitcherFirstPitchAmbushMetrics(
            "p1",
            "Target Pitcher",
            first_pitch_strike_pct=args.f_strike,
            first_pitch_opponent_hard_hit_pct=args.hard,
            first_pitch_opponent_slug_pct=args.slg,
            total_batters_faced=args.bf,
        )
        fpa_res: FirstPitchAmbushEvaluationResult = fpa_eng.evaluate_first_pitch_ambush(fpa_m)

        if args.json:
            fpa_out = {
                "fpcari_score": fpa_res.fpcari_score,
                "fplrs_runs": fpa_res.fplrs_runs_saved,
                "tier": fpa_res.ambush_tier,
                "is_commander": fpa_res.is_commander,
            }
            print(json_lib.dumps(fpa_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     FIRST-PITCH COMMAND & AMBUSH SUPPRESSION [{fpa_res.ambush_tier}]")
            hdr_fpa = (
                f"     FPCARI Score: {fpa_res.fpcari_score:.1f}/160 "
                f"| Runs Saved: {fpa_res.fplrs_runs_saved:>+4.2f} "
                f"| Commander: {'YES' if fpa_res.is_commander else 'NO'}"
            )
            print(hdr_fpa)
            print(f"{'=' * 84}\n")
            print(f"  • Command Profile      : {fpa_res.ambush_tier}\n")

    elif args.command == "wall-block":
        import json as json_lib

        from mlb_baseball.model.wall_block import (
            CatcherWallBlockEngine,
            CatcherWallBlockMetrics,
            WallBlockEvaluationResult,
        )

        wb_eng = CatcherWallBlockEngine()
        wb_m = CatcherWallBlockMetrics(
            "c1",
            "Target Catcher",
            dirt_pitch_block_pct=args.block,
            runner_advance_suppress_pct=args.suppress,
            passed_ball_rate_per_1000=args.pb,
            dirt_pitches_with_runners=args.opps,
        )
        wb_res: WallBlockEvaluationResult = wb_eng.evaluate_wall_block(wb_m)

        if args.json:
            wb_out = {
                "cwbei_score": wb_res.cwbei_score,
                "brsaa_runs": wb_res.brsaa_runs_saved,
                "tier": wb_res.blocking_tier,
                "is_wall": wb_res.is_brick_wall,
            }
            print(json_lib.dumps(wb_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CATCHER DIRT BALL WALL BLOCKING [{wb_res.blocking_tier}]")
            hdr_wb = (
                f"     CWBEI Score: {wb_res.cwbei_score:.1f}/160 "
                f"| Runs Saved: {wb_res.brsaa_runs_saved:>+4.2f} "
                f"| Brick Wall: {'YES' if wb_res.is_brick_wall else 'NO'}"
            )
            print(hdr_wb)
            print(f"{'=' * 84}\n")
            print(f"  • Blocking Profile     : {wb_res.blocking_tier}\n")

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

    elif args.command == "heat-check":
        import json as json_lib

        from mlb_baseball.model.heat_check import (
            BatterHeatCheckEngine,
            BatterHeatCheckMetrics,
            HeatCheckEvaluationResult,
        )

        hc_eng = BatterHeatCheckEngine()
        hc_m = BatterHeatCheckMetrics(
            "b1",
            "Target Batter",
            in_zone_fb_contact_pct=args.contact,
            in_zone_fb_hard_hit_pct=args.hard,
            in_zone_fb_whiff_pct=args.whiff,
            in_zone_fb_swings_count=args.swings,
        )
        hc_res: HeatCheckEvaluationResult = hc_eng.evaluate_heat_check(hc_m)

        if args.json:
            hc_out = {
                "izhsmi_score": hc_res.izhsmi_score,
                "izfpr_runs": hc_res.izfpr_runs_produced,
                "tier": hc_res.smash_tier,
                "is_punisher": hc_res.is_heat_punisher,
            }
            print(json_lib.dumps(hc_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     IN-ZONE FASTBALL CONTACT & SMASH [{hc_res.smash_tier}]")
            hdr_hc = (
                f"     IZHSMI Score: {hc_res.izhsmi_score:.1f}/160 "
                f"| Runs Produced: {hc_res.izfpr_runs_produced:>+4.2f} "
                f"| Heat Punisher: {'YES' if hc_res.is_heat_punisher else 'NO'}"
            )
            print(hdr_hc)
            print(f"{'=' * 84}\n")
            print(f"  • Smash Profile        : {hc_res.smash_tier}\n")

    elif args.command == "putaway-depth":
        import json as json_lib

        from mlb_baseball.model.putaway_depth import (
            PitcherPutawayDepthEngine,
            PitcherPutawayDepthMetrics,
            PutawayDepthEvaluationResult,
        )

        pwd_eng = PitcherPutawayDepthEngine()
        pwd_m = PitcherPutawayDepthMetrics(
            "p1",
            "Target Pitcher",
            early_count_whiff_pct=args.early,
            two_strike_whiff_pct=args.two_strike,
            two_strike_chase_pct=args.chase,
            two_strike_secondaries_count=args.pitches,
        )
        pwd_res: PutawayDepthEvaluationResult = pwd_eng.evaluate_putaway_depth(pwd_m)

        if args.json:
            pwd_out = {
                "pwei_score": pwd_res.pwei_score,
                "whiff_delta": pwd_res.whiff_delta_pct,
                "tssaa_strikeouts": pwd_res.tssaa_strikeouts,
                "tssrv_runs": pwd_res.tssrv_runs_saved,
                "tier": pwd_res.putaway_tier,
                "is_executioner": pwd_res.is_executioner,
            }
            print(json_lib.dumps(pwd_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     SECONDARY PUTAWAY WHIFF ESCALATION [{pwd_res.putaway_tier}]")
            hdr_pwd = (
                f"     PWEI Score: {pwd_res.pwei_score:.1f}/160 "
                f"| 2S Whiff Delta: {pwd_res.whiff_delta_pct:>+4.1f}% "
                f"| TSSAA Strikeouts: {pwd_res.tssaa_strikeouts:>+4.1f}"
            )
            print(hdr_pwd)
            print(f"{'=' * 84}\n")
            print(f"  • Putaway Profile      : {pwd_res.putaway_tier}\n")

    elif args.command == "outfield-target":
        import json as json_lib

        from mlb_baseball.model.outfield_target import (
            OutfieldTargetEngine,
            OutfieldTargetEvaluationResult,
            OutfieldTargetMetrics,
        )

        oft_eng = OutfieldTargetEngine()
        oft_m = OutfieldTargetMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            throw_accuracy_pct=args.acc,
            arm_strength_mph=args.arm,
            assist_conversion_pct=args.conv,
            competitive_throw_chances=args.chances,
        )
        oft_res: OutfieldTargetEvaluationResult = oft_eng.evaluate_outfield_target(oft_m)

        if args.json:
            oft_out = {
                "oltai_score": oft_res.oltai_score,
                "oarp_runs": oft_res.oarp_runs_prevented,
                "tier": oft_res.target_tier,
                "is_sniper": oft_res.is_cannon_sniper,
            }
            print(json_lib.dumps(oft_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD THROW TARGET ACCURACY [{oft_res.target_tier}]")
            hdr_oft = (
                f"     OLTAI Score: {oft_res.oltai_score:.1f}/160 "
                f"| Runs Prevented: {oft_res.oarp_runs_prevented:>+4.2f} "
                f"| Cannon Sniper: {'YES' if oft_res.is_cannon_sniper else 'NO'}"
            )
            print(hdr_oft)
            print(f"{'=' * 84}\n")
            print(f"  • Target Profile       : {oft_res.target_tier}\n")

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

    elif args.command == "oppo-gap":
        import json as json_lib

        from mlb_baseball.model.oppo_gap import (
            BatterOppoGapEngine,
            BatterOppoGapMetrics,
            OppoGapEvaluationResult,
        )

        og_eng = BatterOppoGapEngine()
        og_m = BatterOppoGapMetrics(
            "b1",
            "Target Batter",
            oppo_contact_pct=args.oppo,
            oppo_hard_hit_pct=args.hard,
            oppo_extra_base_hit_pct=args.xbh,
            oppo_batted_balls_count=args.opps,
        )
        og_res: OppoGapEvaluationResult = og_eng.evaluate_oppo_gap(og_m)

        if args.json:
            og_out = {
                "ofgpi_score": og_res.ofgpi_score,
                "aebr_runs": og_res.aebr_runs_produced,
                "tier": og_res.oppo_tier,
                "is_monster": og_res.is_elite_monster,
            }
            print(json_lib.dumps(og_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OPPOSITE-FIELD POWER & GAP XBH [{og_res.oppo_tier}]")
            hdr_og = (
                f"     OFGPI Score: {og_res.ofgpi_score:.1f}/160 "
                f"| Runs Produced: {og_res.aebr_runs_produced:>+4.2f} "
                f"| Power Monster: {'YES' if og_res.is_elite_monster else 'NO'}"
            )
            print(hdr_og)
            print(f"{'=' * 84}\n")
            print(f"  • Power Profile        : {og_res.oppo_tier}\n")

    elif args.command == "spin-align":
        import json as json_lib

        from mlb_baseball.model.spin_align import (
            PitcherSpinAlignEngine,
            PitcherSpinAlignMetrics,
            SpinAlignEvaluationResult,
        )

        sa_eng = PitcherSpinAlignEngine()
        sa_m = PitcherSpinAlignMetrics(
            "p1",
            "Target Pitcher",
            spin_axis_std_dev_mins=args.axis_sd,
            release_height_std_dev_in=args.z_sd,
            release_side_std_dev_in=args.x_sd,
            pitch_arsenal_size=args.pitches,
        )
        sa_res: SpinAlignEvaluationResult = sa_eng.evaluate_spin_align(sa_m)

        if args.json:
            sa_out = {
                "asarci_score": sa_res.asarci_score,
                "deception_multiplier": sa_res.deception_multiplier,
                "tier": sa_res.alignment_tier,
                "is_illusionist": sa_res.is_illusionist,
            }
            print(json_lib.dumps(sa_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     ARSENAL SPIN ALIGNMENT & RELEASE STABILITY [{sa_res.alignment_tier}]")
            hdr_sa = (
                f"     ASARCI Score: {sa_res.asarci_score:.1f}/160 "
                f"| Deception Mult: {sa_res.deception_multiplier:.3f}x "
                f"| Illusionist: {'YES' if sa_res.is_illusionist else 'NO'}"
            )
            print(hdr_sa)
            print(f"{'=' * 84}\n")
            print(f"  • Alignment Profile    : {sa_res.alignment_tier}\n")

    elif args.command == "dp-footwork":
        import json as json_lib

        from mlb_baseball.model.dp_footwork import (
            DpFootworkEvaluationResult,
            InfieldDpFootworkEngine,
            InfieldDpFootworkMetrics,
        )

        dpf_eng = InfieldDpFootworkEngine()
        dpf_m = InfieldDpFootworkMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            pivot_time_sec=args.pivot,
            throw_velo_mph=args.throw,
            dp_conversion_pct=args.conv,
            dp_turn_opportunities=args.opps,
        )
        dpf_res: DpFootworkEvaluationResult = dpf_eng.evaluate_dp_footwork(dpf_m)

        if args.json:
            dpf_out = {
                "dpfti_score": dpf_res.dpfti_score,
                "dptaa_turns": dpf_res.dptaa_turns_saved,
                "dprv_runs": dpf_res.dprv_runs_saved,
                "tier": dpf_res.footwork_tier,
                "is_master": dpf_res.is_lightning_master,
            }
            print(json_lib.dumps(dpf_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     MIDDLE INFIELD DOUBLE-PLAY TURN & FOOTWORK [{dpf_res.footwork_tier}]")
            hdr_dpf = (
                f"     DPFTI Score: {dpf_res.dpfti_score:.1f}/160 "
                f"| DPTAA Turns: {dpf_res.dptaa_turns_saved:>+4.1f} "
                f"| DPRV Runs: {dpf_res.dprv_runs_saved:>+4.2f}"
            )
            print(hdr_dpf)
            print(f"{'=' * 84}\n")
            print(f"  • Footwork Profile     : {dpf_res.footwork_tier}\n")

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

    elif args.command == "pull-slice":
        import json as json_lib

        from mlb_baseball.model.pull_slice import (
            BatterPullSliceEngine,
            BatterPullSliceMetrics,
            PullSliceEvaluationResult,
        )

        ps_eng = BatterPullSliceEngine()
        ps_m = BatterPullSliceMetrics(
            "b1",
            "Target Batter",
            pull_ld_rate_pct=args.pull_ld,
            fair_pole_conversion_pct=args.conv,
            pull_ld_hard_hit_pct=args.hard,
            pull_ld_opportunities=args.opps,
        )
        ps_res: PullSliceEvaluationResult = ps_eng.evaluate_pull_slice(ps_m)

        if args.json:
            ps_out = {
                "pldsr_score": ps_res.pldsr_score,
                "fpebr_runs": ps_res.fpebr_runs_produced,
                "tier": ps_res.slice_tier,
                "is_surgeon": ps_res.is_elite_surgeon,
            }
            print(json_lib.dumps(ps_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PULL LINE-DRIVE SLICE & FAIR CONVERSION [{ps_res.slice_tier}]")
            hdr_ps = (
                f"     PLDSR Score: {ps_res.pldsr_score:.1f}/160 "
                f"| Runs Produced: {ps_res.fpebr_runs_produced:>+4.2f} "
                f"| Elite Surgeon: {'YES' if ps_res.is_elite_surgeon else 'NO'}"
            )
            print(hdr_ps)
            print(f"{'=' * 84}\n")
            print(f"  • Slice Profile        : {ps_res.slice_tier}\n")

    elif args.command == "fatigue-drop":
        import json as json_lib

        from mlb_baseball.model.fatigue_drop import (
            FatigueDropEvaluationResult,
            PitcherFatigueDropEngine,
            PitcherFatigueDropMetrics,
        )

        fd_eng = PitcherFatigueDropEngine()
        fd_m = PitcherFatigueDropMetrics(
            "p1",
            "Target Pitcher",
            late_game_velo_drop_mph=args.velo_drop,
            late_game_rel_drop_in=args.rel_drop,
            late_game_strike_pct=args.strike,
            pitches_thrown_over_75=args.pitches,
        )
        fd_res: FatigueDropEvaluationResult = fd_eng.evaluate_fatigue_drop(fd_m)

        if args.json:
            fd_out = {
                "pafii_score": fd_res.pafii_score,
                "hfvrs_runs": fd_res.hfvrs_runs_saved,
                "tier": fd_res.fatigue_tier,
                "is_workhorse": fd_res.is_steel_arm_workhorse,
            }
            print(json_lib.dumps(fd_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCHER ARM FATIGUE VELOCITY & RELEASE DECAY [{fd_res.fatigue_tier}]")
            hdr_fd = (
                f"     PAFII Score: {fd_res.pafii_score:.1f}/160 "
                f"| Late Runs Saved: {fd_res.hfvrs_runs_saved:>+4.2f} "
                f"| Workhorse: {'YES' if fd_res.is_steel_arm_workhorse else 'NO'}"
            )
            print(hdr_fd)
            print(f"{'=' * 84}\n")
            print(f"  • Endurance Profile    : {fd_res.fatigue_tier}\n")

    elif args.command == "first-step":
        import json as json_lib

        from mlb_baseball.model.first_step import (
            FirstStepEvaluationResult,
            OutfielderFirstStepEngine,
            OutfielderFirstStepMetrics,
        )

        fs_eng = OutfielderFirstStepEngine()
        fs_m = OutfielderFirstStepMetrics(
            "f1",
            "Target Outfielder",
            position=args.pos,
            reaction_time_sec=args.react,
            distance_first_1_5s_ft=args.dist,
            route_jump_efficiency_pct=args.eff,
            outfield_flyball_chances=args.chances,
        )
        fs_res: FirstStepEvaluationResult = fs_eng.evaluate_first_step(fs_m)

        if args.json:
            fs_out = {
                "fsrji_score": fs_res.fsrji_score,
                "jrp_runs": fs_res.jrp_runs_prevented,
                "tier": fs_res.jump_tier,
                "is_burster": fs_res.is_elite_burster,
            }
            print(json_lib.dumps(fs_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELDER FIRST-STEP REACTION & BURST [{fs_res.jump_tier}]")
            hdr_fs = (
                f"     FSRJI Score: {fs_res.fsrji_score:.1f}/160 "
                f"| Runs Prevented: {fs_res.jrp_runs_prevented:>+4.2f} "
                f"| Elite Burster: {'YES' if fs_res.is_elite_burster else 'NO'}"
            )
            print(hdr_fs)
            print(f"{'=' * 84}\n")
            print(f"  • Burst Profile        : {fs_res.jump_tier}\n")

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

    elif args.command == "high-heat":
        import json as json_lib

        from mlb_baseball.model.high_heat import (
            BatterHighHeatEngine,
            BatterHighHeatMetrics,
            HighHeatEvaluationResult,
        )

        hh_eng = BatterHighHeatEngine()
        hh_m = BatterHighHeatMetrics(
            "b1",
            "Target Batter",
            high_fb_swing_rate_pct=args.swing,
            high_fb_whiff_rate_pct=args.whiff,
            high_fb_hard_hit_pct=args.hard,
            high_fb_opportunities=args.opps,
        )
        hh_res: HighHeatEvaluationResult = hh_eng.evaluate_high_heat(hh_m)

        if args.json:
            hh_out = {
                "hhevi_score": hh_res.hhevi_score,
                "hfpr_runs": hh_res.hfpr_runs_produced,
                "tier": hh_res.heat_tier,
                "is_crusher": hh_res.is_elite_crusher,
            }
            print(json_lib.dumps(hh_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     HIGH-FASTBALL ELEVATION MASTERY [{hh_res.heat_tier}]")
            hdr_hh = (
                f"     HHEVI Score: {hh_res.hhevi_score:.1f}/160 "
                f"| Runs Produced: {hh_res.hfpr_runs_produced:>+4.2f} "
                f"| Elite Crusher: {'YES' if hh_res.is_elite_crusher else 'NO'}"
            )
            print(hdr_hh)
            print(f"{'=' * 84}\n")
            print(f"  • Elevation Profile    : {hh_res.heat_tier}\n")

    elif args.command == "ssw-latent":
        import json as json_lib

        from mlb_baseball.model.ssw_latent import (
            PitcherSswLatentEngine,
            PitcherSswLatentMetrics,
            SswLatentEvaluationResult,
        )

        ssw_l_eng = PitcherSswLatentEngine()
        ssw_l_m = PitcherSswLatentMetrics(
            "p1",
            "Target Pitcher",
            pitch_type=args.pitch,
            optical_axis_minutes=args.optical,
            inferred_axis_minutes=args.inferred,
            observed_break_in=args.obs,
            pure_magnus_break_in=args.mag,
            pitch_count_evaluated=args.pitches,
        )
        ssw_l_res: SswLatentEvaluationResult = ssw_l_eng.evaluate_ssw(ssw_l_m)

        if args.json:
            ssw_l_out = {
                "axis_deviation_mins": ssw_l_res.axis_deviation_mins,
                "latent_break_in": ssw_l_res.latent_ssw_break_in,
                "sswlmr_score": ssw_l_res.sswlmr_score,
                "tier": ssw_l_res.ssw_tier,
                "is_manipulator": ssw_l_res.is_elite_manipulator,
            }
            print(json_lib.dumps(ssw_l_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     SEAM-SHIFTED WAKE LATENT MOVEMENT [{ssw_l_res.ssw_tier}]")
            hdr_ssw = (
                f"     SSWLMR Score: {ssw_l_res.sswlmr_score:.1f}/160 "
                f"| Axis Gap: {ssw_l_res.axis_deviation_mins}m "
                f"| Latent Break: +{ssw_l_res.latent_ssw_break_in:.1f} in"
            )
            print(hdr_ssw)
            print(f"{'=' * 84}\n")
            print(f"  • Aerodynamic Profile  : {ssw_l_res.ssw_tier}\n")

    elif args.command == "bunt-charge":
        import json as json_lib

        from mlb_baseball.model.bunt_charge import (
            BuntChargeEvaluationResult,
            InfieldBuntChargeEngine,
            InfieldBuntChargeMetrics,
        )

        bc_eng = InfieldBuntChargeEngine()
        bc_m = InfieldBuntChargeMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            charge_sprint_speed_fps=args.speed,
            barehand_transfer_sec=args.barehand,
            bunt_out_conversion_pct=args.conv,
            bunt_chances_count=args.chances,
        )
        bc_res: BuntChargeEvaluationResult = bc_eng.evaluate_bunt_charge(bc_m)

        if args.json:
            bc_out = {
                "ibcdi_score": bc_res.ibcdi_score,
                "boaa_outs": bc_res.boaa_outs_saved,
                "bcdrv_runs": bc_res.bcdrv_runs_saved,
                "tier": bc_res.defense_tier,
                "is_eraser": bc_res.is_elite_eraser,
            }
            print(json_lib.dumps(bc_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     INFIELD BUNT CHARGE & BAREHAND DEFENSE [{bc_res.defense_tier}]")
            hdr_bc = (
                f"     IBCDI Score: {bc_res.ibcdi_score:.1f}/160 "
                f"| BOAA Outs: {bc_res.boaa_outs_saved:>+4.1f} "
                f"| BCDRV Runs: {bc_res.bcdrv_runs_saved:>+4.2f}"
            )
            print(hdr_bc)
            print(f"{'=' * 84}\n")
            print(f"  • Defense Profile      : {bc_res.defense_tier}\n")

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

    elif args.command == "air-trap":
        import json as json_lib

        from mlb_baseball.model.air_trap import (
            AirTrapEvaluationResult,
            BatterAirTrapEngine,
            BatterAirTrapMetrics,
        )

        at_eng = BatterAirTrapEngine()
        at_m = BatterAirTrapMetrics(
            "b1",
            "Target Batter",
            pull_flyball_rate_pct=args.pull_fb,
            warning_track_trap_pct=args.trap,
            wall_clearance_hr_pct=args.clear,
            flyball_count=args.fb,
        )
        at_res: AirTrapEvaluationResult = at_eng.evaluate_air_trap(at_m)

        if args.json:
            at_out = {
                "pacdtr_score": at_res.pacdtr_score,
                "tthrd_runs": at_res.tthrd_runs_lost,
                "tier": at_res.trap_tier,
                "is_clearer": at_res.is_elite_clearer,
            }
            print(json_lib.dumps(at_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PULL-AIR CONVERSION VS WARNING TRACK TRAP [{at_res.trap_tier}]")
            hdr_at = (
                f"     PACDTR Score: {at_res.pacdtr_score:.1f}/160 "
                f"| Runs Deficit: {at_res.tthrd_runs_lost:>+4.2f} "
                f"| Elite Clearer: {'YES' if at_res.is_elite_clearer else 'NO'}"
            )
            print(hdr_at)
            print(f"{'=' * 84}\n")
            print(f"  • Clearance Profile    : {at_res.trap_tier}\n")

    elif args.command == "intent-leak":
        import json as json_lib

        from mlb_baseball.model.intent_leak import (
            IntentLeakEvaluationResult,
            PitcherIntentLeakEngine,
            PitcherPutawayIntentMetrics,
        )

        il_eng = PitcherIntentLeakEngine()
        il_m = PitcherPutawayIntentMetrics(
            "p1",
            "Target Pitcher",
            chase_dirt_intent_pct=args.chase,
            heart_zone_leak_pct=args.heart,
            two_strike_k_pct=args.k_pct,
            two_strike_pitches_count=args.pitches,
        )
        il_res: IntentLeakEvaluationResult = il_eng.evaluate_intent_leak(il_m)

        if args.json:
            il_out = {
                "tspiei_score": il_res.tspiei_score,
                "hpcr_runs": il_res.hpcr_runs_prevented,
                "tier": il_res.intent_tier,
                "is_sniper": il_res.is_surgical_sniper,
            }
            print(json_lib.dumps(il_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TWO-STRIKE PUTAWAY INTENT EXECUTION [{il_res.intent_tier}]")
            hdr_il = (
                f"     TSPIEI Score: {il_res.tspiei_score:.1f}/160 "
                f"| Mistake Runs Prevented: {il_res.hpcr_runs_prevented:>+4.2f} "
                f"| Sniper: {'YES' if il_res.is_surgical_sniper else 'NO'}"
            )
            print(hdr_il)
            print(f"{'=' * 84}\n")
            print(f"  • Command Profile      : {il_res.intent_tier}\n")

    elif args.command == "lead-snap":
        import json as json_lib

        from mlb_baseball.model.lead_snap import (
            LeadSnapEvaluationResult,
            RunnerLeadSnapEngine,
            RunnerLeadSnapMetrics,
        )

        lsn_eng = RunnerLeadSnapEngine()
        lsn_m = RunnerLeadSnapMetrics(
            "r1",
            "Target Runner",
            primary_lead_distance_ft=args.prim,
            secondary_jump_distance_ft=args.sec,
            pitcher_move_time_sec=args.move,
            pickoff_throw_rate_pct=args.pickoff,
            baserunning_opportunities=args.opps,
        )
        lsn_res: LeadSnapEvaluationResult = lsn_eng.evaluate_lead_snap(lsn_m)

        if args.json:
            lsn_out = {
                "asli_score": lsn_res.asli_score,
                "advance_boost": lsn_res.advance_prob_boost_pct,
                "aslrv_runs": lsn_res.aslrv_runs_produced,
                "tier": lsn_res.lead_tier,
                "is_terror": lsn_res.is_aggressive_terror,
            }
            print(json_lib.dumps(lsn_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     SECONDARY LEAD DISTANCE & ADVANCE JUMP [{lsn_res.lead_tier}]")
            hdr_lsn = (
                f"     ASLI Score: {lsn_res.asli_score:.1f}/160 "
                f"| Advance Boost: +{lsn_res.advance_prob_boost_pct:.1f}% "
                f"| Runs: {lsn_res.aslrv_runs_produced:>+4.2f}"
            )
            print(hdr_lsn)
            print(f"{'=' * 84}\n")
            print(f"  • Lead Profile         : {lsn_res.lead_tier}\n")

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

    elif args.command == "zone-whiff":
        import json as json_lib

        from mlb_baseball.model.zone_whiff import (
            BatterZoneWhiffEngine,
            BatterZoneWhiffMetrics,
        )

        zw_eng = BatterZoneWhiffEngine()
        zw_m = BatterZoneWhiffMetrics(
            "b1",
            "Target Batter",
            zone_swing_rate_pct=args.z_swing,
            zone_whiff_rate_pct=args.z_whiff,
            zone_barrel_per_bbe_pct=args.z_barrel,
            zone_swings_count=args.swings,
        )
        zw_res = zw_eng.evaluate_zone_whiff(zw_m)

        if args.json:
            zw_out = {
                "zcpoi_score": zw_res.zcpoi_score,
                "izpsr_runs": zw_res.izpsr_runs_saved,
                "tier": zw_res.tradeoff_tier,
                "is_crusher": zw_res.is_elite_crusher,
            }
            print(json_lib.dumps(zw_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     IN-ZONE WHIFF VS CONTACT TRADEOFF [{zw_res.tradeoff_tier}]")
            hdr_zw = (
                f"     ZCPOI Score: {zw_res.zcpoi_score:.1f}/160 "
                f"| Runs: {zw_res.izpsr_runs_saved:>+4.2f} "
                f"| Elite Crusher: {'YES' if zw_res.is_elite_crusher else 'NO'}"
            )
            print(hdr_zw)
            print(f"{'=' * 84}\n")
            print(f"  • Zone Profile         : {zw_res.tradeoff_tier}\n")

    elif args.command == "active-spin":
        import json as json_lib

        from mlb_baseball.model.active_spin import (
            ActiveSpinEvaluationResult,
            PitcherActiveSpinEngine,
            PitcherActiveSpinMetrics,
        )

        as_eng = PitcherActiveSpinEngine()
        as_m = PitcherActiveSpinMetrics(
            "p1",
            "Target Pitcher",
            pitch_type=args.pitch,
            total_spin_rpm=args.total,
            inferred_active_spin_rpm=args.active,
            observed_ivb_in=args.ivb,
            observed_hb_in=args.hb,
            pitch_count_evaluated=args.pitches,
        )
        as_res: ActiveSpinEvaluationResult = as_eng.evaluate_active_spin(as_m)

        if args.json:
            as_out = {
                "active_spin_pct": as_res.active_spin_pct,
                "gyro_angle_deg": as_res.gyro_angle_deg,
                "asmi_score": as_res.asmi_score,
                "tier": as_res.spin_tier,
                "is_magnus": as_res.is_pure_magnus,
            }
            print(json_lib.dumps(as_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     ACTIVE SPIN EFFICIENCY [{as_res.spin_tier}]")
            hdr_as = (
                f"     Active Spin: {as_res.active_spin_pct:.1f}% "
                f"| Gyro Angle: {as_res.gyro_angle_deg:.1f}° "
                f"| ASMI Score: {as_res.asmi_score:.1f}/160"
            )
            print(hdr_as)
            print(f"{'=' * 84}\n")
            print(f"  • Spin Profile         : {as_res.spin_tier}")
            print(f"  • Pure Magnus Rider    : {'YES' if as_res.is_pure_magnus else 'NO'}\n")

    elif args.command == "low-scoop":
        import json as json_lib

        from mlb_baseball.model.low_scoop import (
            CatcherLowScoopEngine,
            CatcherLowScoopMetrics,
            LowScoopEvaluationResult,
        )

        lsc_eng = CatcherLowScoopEngine()
        lsc_m = CatcherLowScoopMetrics(
            "c1",
            "Target Catcher",
            low_zone_called_strike_pct=args.strike,
            upward_scoop_speed_fps=args.scoop,
            glove_drop_rate_pct=args.drop,
            low_zone_opportunities=args.opps,
        )
        lsc_res: LowScoopEvaluationResult = lsc_eng.evaluate_low_scoop(lsc_m)

        if args.json:
            lsc_out = {
                "bzsfr_score": lsc_res.bzsfr_score,
                "extra_strikes": lsc_res.extra_strikes_created,
                "lzfs_runs": lsc_res.lzfs_runs_saved,
                "tier": lsc_res.framing_tier,
                "is_lifter": lsc_res.is_elite_lifter,
            }
            print(json_lib.dumps(lsc_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BOTTOM-ZONE SCOOP FRAMING [{lsc_res.framing_tier}]")
            hdr_ls = (
                f"     BZSFR Score: {lsc_res.bzsfr_score:.1f}/160 "
                f"| Extra Strikes: {lsc_res.extra_strikes_created:>+4.1f} "
                f"| LZFS Runs: {lsc_res.lzfs_runs_saved:>+4.2f}"
            )
            print(hdr_ls)
            print(f"{'=' * 84}\n")
            print(f"  • Framing Profile      : {lsc_res.framing_tier}")
            print(f"  • Elite Lifter         : {'YES' if lsc_res.is_elite_lifter else 'NO'}\n")

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

    elif args.command == "slash-oppo":
        import json as json_lib

        from mlb_baseball.model.slash_oppo import (
            BatterSlashOppoEngine,
            BatterSlashOppoMetrics,
        )

        slo_eng = BatterSlashOppoEngine()
        slo_m = BatterSlashOppoMetrics(
            "b1",
            "Target Batter",
            oppo_contact_pct=args.oppo,
            oppo_line_drive_pct=args.oppo_ld,
            pull_groundball_pct=args.pull_gb,
            total_bbe_count=args.bbe,
        )
        slo_res = slo_eng.evaluate_slash(slo_m)

        if args.json:
            slo_out = {
                "ofsrr_score": slo_res.ofsrr_score,
                "delta_babip": slo_res.babip_adjustment,
                "ofsrv_runs": slo_res.ofsrv_runs_saved,
                "tier": slo_res.slash_tier,
                "is_artist": slo_res.is_slash_artist,
            }
            print(json_lib.dumps(slo_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OPPOSITE FIELD SLASH & ANTI-SHIFT [{slo_res.slash_tier}]")
            hdr_so = (
                f"     OFSRR Score: {slo_res.ofsrr_score:.1f}/160 "
                f"| Delta BABIP: {slo_res.babip_adjustment:>+5.3f} "
                f"| Runs: {slo_res.ofsrv_runs_saved:>+4.2f}"
            )
            print(hdr_so)
            print(f"{'=' * 84}\n")
            print(f"  • Spray Profile        : {slo_res.slash_tier}")
            print(f"  • Slash Artist         : {'YES' if slo_res.is_slash_artist else 'NO'}\n")

    elif args.command == "arm-align":
        import json as json_lib

        from mlb_baseball.model.arm_align import (
            PitcherArmAlignEngine,
            PitcherArsenalArmSlotMetrics,
        )

        aal_eng = PitcherArmAlignEngine()
        aal_m = PitcherArsenalArmSlotMetrics(
            "p1",
            "Target Pitcher",
            fastball_arm_angle_deg=args.fb_deg,
            breaking_arm_angle_deg=args.br_deg,
            offspeed_arm_angle_deg=args.os_deg,
            fastball_rel_z_in=args.fb_z,
            breaking_rel_z_in=args.br_z,
            offspeed_rel_z_in=args.os_z,
            pitch_count_evaluated=args.pitches,
        )
        aal_res = aal_eng.evaluate_alignment(aal_m)

        if args.json:
            aal_out = {
                "max_angle_gap": aal_res.max_arm_angle_gap_deg,
                "max_z_gap": aal_res.max_rel_z_gap_in,
                "aaar_score": aal_res.aaar_score,
                "tipping_multiplier": aal_res.tipping_risk_multiplier,
                "tier": aal_res.alignment_tier,
                "is_clone": aal_res.is_slot_clone,
            }
            print(json_lib.dumps(aal_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     ARSENAL ARM SLOT STABILITY [{aal_res.alignment_tier}]")
            hdr_aa = (
                f"     AAAR Score: {aal_res.aaar_score:.1f}/160 "
                f"| Max Angle Gap: {aal_res.max_arm_angle_gap_deg:.1f}° "
                f"| Max Z Gap: {aal_res.max_rel_z_gap_in:.1f} in"
            )
            print(hdr_aa)
            print(f"{'=' * 84}\n")
            print(f"  • Tipping Risk         : {aal_res.tipping_risk_multiplier:.2f}x")
            print(f"  • Deceptive Slot Clone : {'YES' if aal_res.is_slot_clone else 'NO'}\n")

    elif args.command == "wall-crash":
        import json as json_lib

        from mlb_baseball.model.wall_crash import (
            OutfielderWallCrashEngine,
            OutfielderWallCrashMetrics,
        )

        wcr_eng = OutfielderWallCrashEngine()
        wcr_m = OutfielderWallCrashMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            wall_hazard_catch_pct=args.catch,
            wall_collision_rate_pct=args.collision,
            deceleration_cushion_ft=args.cushion,
            wall_opportunities=args.opps,
        )
        wcr_res = wcr_eng.evaluate_wall_crash(wcr_m)

        if args.json:
            wcr_out = {
                "wcfi_score": wcr_res.wcfi_score,
                "surplus_catches": wcr_res.surplus_catches,
                "webpr_runs": wcr_res.webpr_runs_saved,
                "tier": wcr_res.hazard_tier,
                "is_fearless": wcr_res.is_fearless_crasher,
            }
            print(json_lib.dumps(wcr_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD WALL CRASH HAZARD DEFENSE [{wcr_res.hazard_tier}]")
            hdr_wc = (
                f"     WCFI Score: {wcr_res.wcfi_score:.1f}/160 "
                f"| Surplus Catches: {wcr_res.surplus_catches:>+4.1f} "
                f"| WEBPR Runs: {wcr_res.webpr_runs_saved:>+4.2f}"
            )
            print(hdr_wc)
            print(f"{'=' * 84}\n")
            print(f"  • Wall Approach Profile: {wcr_res.hazard_tier}")
            print(f"  • Fearless Crasher     : {'YES' if wcr_res.is_fearless_crasher else 'NO'}\n")

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

    elif args.command == "ext-perceive":
        import json as json_lib

        from mlb_baseball.model.ext_perceive import (
            PitcherExtensionKinematicsMetrics,
            PitcherExtPerceiveEngine,
        )

        ext_p_eng = PitcherExtPerceiveEngine()
        ext_p_m = PitcherExtensionKinematicsMetrics(
            "p1",
            "Target Pitcher",
            extension_ft=args.ext,
            radar_velocity_mph=args.velo,
            induced_vert_break_in=args.ivb,
            release_z_ft=args.rel_z,
            pitch_count_evaluated=args.pitches,
        )
        ext_p_res = ext_p_eng.evaluate_extension(ext_p_m)

        if args.json:
            ext_p_out = {
                "effective_velo": ext_p_res.effective_velocity_mph,
                "reaction_compression_ms": ext_p_res.reaction_time_compression_ms,
                "ever_score": ext_p_res.ever_score,
                "whiff_multiplier": ext_p_res.whiff_boost_multiplier,
                "tier": ext_p_res.extension_tier,
                "is_deceiver": ext_p_res.is_elite_deceiver,
            }
            print(json_lib.dumps(ext_p_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCHER EXTENSION & EFFECTIVE VELO [{ext_p_res.extension_tier}]")
            hdr_ep = (
                f"     EVER Score: {ext_p_res.ever_score:.1f}/160 "
                f"| Effective Velo: {ext_p_res.effective_velocity_mph:.1f} mph "
                f"| Whiff Boost: {ext_p_res.whiff_boost_multiplier:.3f}x"
            )
            print(hdr_ep)
            print(f"{'=' * 84}\n")
            print(f"  • Reaction Compression : {ext_p_res.reaction_time_compression_ms:>+4.1f} ms")
            print(f"  • Elite Deceiver       : {'YES' if ext_p_res.is_elite_deceiver else 'NO'}\n")

    elif args.command == "foul-attrition":
        import json as json_lib

        from mlb_baseball.model.foul_attrition import (
            BatterFoulAttritionEngine,
            BatterFoulAttritionMetrics,
        )

        fatr_eng = BatterFoulAttritionEngine()
        fatr_m = BatterFoulAttritionMetrics(
            "b1",
            "Target Batter",
            multi_foul_pa_rate_pct=args.multi_foul,
            pitches_per_pa=args.ppa,
            two_strike_foul_rate_pct=args.foul,
            total_pa_count=args.pa,
        )
        fatr_res = fatr_eng.evaluate_attrition(fatr_m)

        if args.json:
            fatr_out = {
                "bfai_score": fatr_res.bfai_score,
                "surplus_pitches": fatr_res.surplus_pitches_extracted,
                "srar_runs": fatr_res.srar_runs_saved,
                "tier": fatr_res.attrition_tier,
                "is_grinder": fatr_res.is_exhausting_grinder,
            }
            print(json_lib.dumps(fatr_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BATTER FOUL ATTRITION [{fatr_res.attrition_tier}]")
            hdr_fa = (
                f"     BFAI Score: {fatr_res.bfai_score:.1f}/160 "
                f"| Extra Pitches: {fatr_res.surplus_pitches_extracted:>+5.1f} "
                f"| SRAR Runs: {fatr_res.srar_runs_saved:>+4.2f}"
            )
            print(hdr_fa)
            print(f"{'=' * 84}\n")
            print(f"  • Attrition Profile    : {fatr_res.attrition_tier}")
            print(
                f"  • Exhausting Grinder   : {'YES' if fatr_res.is_exhausting_grinder else 'NO'}\n"
            )

    elif args.command == "block-suppress":
        import json as json_lib

        from mlb_baseball.model.block_suppress import (
            CatcherBlockSuppressEngine,
            CatcherDirtBlockMetrics,
        )

        bsp_eng = CatcherBlockSuppressEngine()
        bsp_m = CatcherDirtBlockMetrics(
            "c1",
            "Target Catcher",
            dirt_ball_block_pct=args.block,
            recovery_time_sec=args.recov,
            runner_advance_prevention_pct=args.prev,
            dirt_ball_opportunities=args.opps,
        )
        bsp_res = bsp_eng.evaluate_blocking(bsp_m)

        if args.json:
            bsp_out = {
                "dbwr_score": bsp_res.dbwr_score,
                "bapr_runs": bsp_res.bapr_runs_saved,
                "tier": bsp_res.blocking_tier,
                "is_brick_wall": bsp_res.is_brick_wall,
            }
            print(json_lib.dumps(bsp_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CATCHER DIRT-BALL WALL SUPPRESSION [{bsp_res.blocking_tier}]")
            hdr_bs = (
                f"     DBWR Score: {bsp_res.dbwr_score:.1f}/160 "
                f"| BAPR Runs Saved: {bsp_res.bapr_runs_saved:>+4.2f} "
                f"| Tier: {bsp_res.blocking_tier}"
            )
            print(hdr_bs)
            print(f"{'=' * 84}\n")
            print(f"  • Blocking Profile     : {bsp_res.blocking_tier}")
            print(f"  • Brick Wall Specialist: {'YES' if bsp_res.is_brick_wall else 'NO'}\n")

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

    elif args.command == "pull-barrel":
        import json as json_lib

        from mlb_baseball.model.pull_barrel import (
            BatterPullBarrelEngine,
            BatterPullBarrelMetrics,
        )

        pbr_eng = BatterPullBarrelEngine()
        pbr_m = BatterPullBarrelMetrics(
            "b1",
            "Target Batter",
            flyball_pull_pct=args.pull_fb,
            pull_barrel_pct=args.pull_bar,
            oppo_barrel_pct=args.oppo_bar,
            pulled_air_count=args.air_count,
            total_bbe_count=args.bbe,
        )
        pbr_res = pbr_eng.evaluate_pull_barrel(pbr_m)

        if args.json:
            pbr_out = {
                "pabci_score": pbr_res.pabci_score,
                "surplus_hr": pbr_res.surplus_home_runs,
                "pabsv_runs": pbr_res.pabsv_runs_saved,
                "tier": pbr_res.power_tier,
                "is_crusher": pbr_res.is_optimal_crusher,
            }
            print(json_lib.dumps(pbr_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PULL-AIR BARREL POWER CONVERSION [{pbr_res.power_tier}]")
            hdr_pb = (
                f"     PABCI Score: {pbr_res.pabci_score:.1f}/160 "
                f"| Surplus HRs: {pbr_res.surplus_home_runs:>+4.2f} "
                f"| Runs: {pbr_res.pabsv_runs_saved:>+4.2f}"
            )
            print(hdr_pb)
            print(f"{'=' * 84}\n")
            print(f"  • Power Profile        : {pbr_res.power_tier}")
            print(f"  • Optimal Power Crusher: {'YES' if pbr_res.is_optimal_crusher else 'NO'}\n")

    elif args.command == "putaway-exec":
        import json as json_lib

        from mlb_baseball.model.putaway_exec import (
            PitcherPutawayExecutionEngine,
            PitcherPutawayExecutionMetrics,
        )

        ptw_eng = PitcherPutawayExecutionEngine()
        ptw_m = PitcherPutawayExecutionMetrics(
            "p1",
            "Target Pitcher",
            two_strike_shadow_pct=args.shadow,
            two_strike_chase_pct=args.chase,
            two_strike_heart_pct=args.heart,
            two_strike_waste_pct=args.waste,
            two_strike_pitch_count=args.pitches,
        )
        ptw_res = ptw_eng.evaluate_putaway_execution(ptw_m)

        if args.json:
            ptw_out = {
                "tsper_score": ptw_res.tsper_score,
                "ptsv_runs": ptw_res.ptsv_runs_saved,
                "tier": ptw_res.execution_tier,
                "is_sniper": ptw_res.is_surgical_sniper,
            }
            print(json_lib.dumps(ptw_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TWO-STRIKE PUTAWAY COMMAND [{ptw_res.execution_tier}]")
            hdr_pt = (
                f"     TSPER Score: {ptw_res.tsper_score:.1f}/160 "
                f"| Runs Saved: {ptw_res.ptsv_runs_saved:>+4.2f} "
                f"| Tier: {ptw_res.execution_tier}"
            )
            print(hdr_pt)
            print(f"{'=' * 84}\n")
            print(f"  • Command Execution    : {ptw_res.execution_tier}")
            print(f"  • Surgical Sniper      : {'YES' if ptw_res.is_surgical_sniper else 'NO'}\n")

    elif args.command == "route-burst":
        import json as json_lib

        from mlb_baseball.model.route_burst import (
            OutfielderBurstRouteMetrics,
            OutfielderRouteBurstEngine,
        )

        rbt_eng = OutfielderRouteBurstEngine()
        rbt_m = OutfielderBurstRouteMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            reaction_time_sec=args.react,
            burst_velocity_ft_s=args.burst,
            route_efficiency_pct=args.route,
            opportunity_count=args.opps,
        )
        rbt_res = rbt_eng.evaluate_route_burst(rbt_m)

        if args.json:
            rbt_out = {
                "brfei_score": rbt_res.brfei_score,
                "oaa_jump_runs": rbt_res.oaa_jump_runs_saved,
                "tier": rbt_res.range_tier,
                "is_ballhawk": rbt_res.is_elite_ballhawk,
            }
            print(json_lib.dumps(rbt_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD BURST & ROUTE EFFICIENCY [{rbt_res.range_tier}]")
            hdr_rb = (
                f"     BRFEI Score: {rbt_res.brfei_score:.1f}/160 "
                f"| Jump Runs Saved: {rbt_res.oaa_jump_runs_saved:>+4.2f} "
                f"| Tier: {rbt_res.range_tier}"
            )
            print(hdr_rb)
            print(f"{'=' * 84}\n")
            print(f"  • Range Profile        : {rbt_res.range_tier}")
            print(f"  • Elite Ballhawk       : {'YES' if rbt_res.is_elite_ballhawk else 'NO'}\n")

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

    elif args.command == "rel-drift":
        import json as json_lib

        from mlb_baseball.model.rel_drift import (
            PitcherReleaseDispersionMetrics,
            PitcherReleaseDriftEngine,
        )

        rdr_eng = PitcherReleaseDriftEngine()
        rdr_m = PitcherReleaseDispersionMetrics(
            "p1",
            "Target Pitcher",
            std_rel_x_in=args.std_x,
            std_rel_z_in=args.std_z,
            late_game_rel_drop_in=args.late_drop,
            pitch_count_evaluated=args.pitches,
        )
        rdr_res = rdr_eng.evaluate_release_drift(rdr_m)

        if args.json:
            rdr_out = {
                "spatial_dispersion_in": rdr_res.spatial_dispersion_in,
                "mcs_score": rdr_res.mcs_score,
                "tier": rdr_res.release_tier,
                "is_metronomic": rdr_res.is_metronomic_repeater,
                "is_collapse": rdr_res.fatigue_collapse_warning,
            }
            print(json_lib.dumps(rdr_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     RELEASE POINT VARIANCE & DRIFT [{rdr_res.release_tier}]")
            hdr_rd = (
                f"     Dispersion: {rdr_res.spatial_dispersion_in:.2f} in "
                f"| MCS Score: {rdr_res.mcs_score:.1f}/160 "
                f"| Repeater: {'YES' if rdr_res.is_metronomic_repeater else 'NO'}"
            )
            print(hdr_rd)
            print(f"{'=' * 84}\n")
            print(f"  • Consistency Tier     : {rdr_res.release_tier}")
            warn_txt = "YES (ARM DROP ALERT)" if rdr_res.fatigue_collapse_warning else "NO"
            print(f"  • Fatigue Warning      : {warn_txt}\n")

    elif args.command == "exp-resist":
        import json as json_lib

        from mlb_baseball.model.exp_resist import (
            BatterExpansionResistanceEngine,
            BatterExpansionResistanceMetrics,
        )

        exp_eng = BatterExpansionResistanceEngine()
        exp_m = BatterExpansionResistanceMetrics(
            "b1",
            "Target Batter",
            two_strike_chase_pct=args.chase,
            two_strike_o_contact_pct=args.o_contact,
            two_strike_foul_pct=args.foul,
            two_strike_pa_count=args.pa,
        )
        exp_res = exp_eng.evaluate_resistance(exp_m)

        if args.json:
            exp_out = {
                "teri_score": exp_res.teri_score,
                "runs_value": exp_res.runs_value,
                "tier": exp_res.resistance_tier,
                "is_elite": exp_res.is_elite_resistor,
            }
            print(json_lib.dumps(exp_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TWO-STRIKE EXPANSION RESISTANCE [{exp_res.resistance_tier}]")
            hdr_er = (
                f"     TERI Score: {exp_res.teri_score:.1f}/160 "
                f"| Battle Runs: {exp_res.runs_value:>+4.2f} "
                f"| Tier: {exp_res.resistance_tier}"
            )
            print(hdr_er)
            print(f"{'=' * 84}\n")
            print(f"  • Resistance Strategy  : {exp_res.resistance_tier}")
            print(f"  • Elite Zone Resistor  : {'YES' if exp_res.is_elite_resistor else 'NO'}\n")

    elif args.command == "catch-xchg":
        import json as json_lib

        from mlb_baseball.model.catch_xchg import (
            CatcherExchangeEngine,
            CatcherExchangeMetrics,
        )

        cxc_eng = CatcherExchangeEngine()
        cxc_m = CatcherExchangeMetrics(
            "c1",
            "Target Catcher",
            exchange_time_sec=args.xchg,
            throw_velocity_mph=args.velo,
            throw_flight_time_sec=args.flight,
            throw_accuracy_pct=args.acc,
            stolen_base_attempts_against=args.att,
        )
        cxc_res = cxc_eng.evaluate_exchange(cxc_m)

        if args.json:
            cxc_out = {
                "total_pop_time_sec": cxc_res.total_pop_time_sec,
                "cevi_score": cxc_res.cevi_score,
                "sbd_runs_saved": cxc_res.sbd_runs_saved,
                "tier": cxc_res.transfer_tier,
                "is_lightning": cxc_res.is_lightning_transfer,
            }
            print(json_lib.dumps(cxc_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CATCHER POP TIME & EXCHANGE [{cxc_res.transfer_tier}]")
            hdr_cx = (
                f"     Pop Time: {cxc_res.total_pop_time_sec:.3f} s "
                f"| CEVI Score: {cxc_res.cevi_score:.1f} "
                f"| Runs Saved: {cxc_res.sbd_runs_saved:>+4.2f}"
            )
            print(hdr_cx)
            print(f"{'=' * 84}\n")
            print(f"  • Transfer Tier        : {cxc_res.transfer_tier}")
            print(
                f"  • Lightning Transfer   : {'YES' if cxc_res.is_lightning_transfer else 'NO'}\n"
            )

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

    elif args.command == "pull-gb":
        import json as json_lib

        from mlb_baseball.model.pull_gb import (
            BatterPullGBMetrics,
            InfieldPositioningGBEngine,
        )

        pgb_eng = InfieldPositioningGBEngine()
        pgb_m = BatterPullGBMetrics(
            "b1",
            "Target Batter",
            batter_side=args.side,
            groundball_rate_pct=args.gb_pct,
            pull_groundball_pct=args.pull_gb,
            oppo_groundball_pct=args.oppo_gb,
            hard_pull_gb_pct=args.hard_pull,
            groundball_count=args.gb_count,
        )
        pgb_res = pgb_eng.evaluate_positioning(pgb_m)

        if args.json:
            pgb_out = {
                "depth_ft": pgb_res.optimal_depth_ft,
                "gbti_score": pgb_res.gbti_score,
                "pdrs_runs": pgb_res.pdrs_runs_saved,
                "tier": pgb_res.positioning_tier,
                "is_extreme": pgb_res.requires_extreme_shading,
            }
            print(json_lib.dumps(pgb_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PULL GROUNDBALL DEFENSE & POSITIONING [{pgb_res.positioning_tier}]")
            hdr_pg = (
                f"     Depth: {pgb_res.optimal_depth_ft:.1f} ft "
                f"| GBTI Score: {pgb_res.gbti_score:.1f} "
                f"| Runs Saved: {pgb_res.pdrs_runs_saved:>+4.2f}"
            )
            print(hdr_pg)
            print(f"{'=' * 84}\n")
            print(f"  • Positioning Strategy : {pgb_res.positioning_tier}")
            ext_txt = "YES" if pgb_res.requires_extreme_shading else "NO"
            print(f"  • Extreme Pull Shading : {ext_txt}\n")

    elif args.command == "vaa-toz":
        import json as json_lib

        from mlb_baseball.model.vaa_toz import (
            PitcherTOZVAAEngine,
            PitcherTOZVAAMetrics,
        )

        vtz_eng = PitcherTOZVAAEngine()
        vtz_m = PitcherTOZVAAMetrics(
            "p1",
            "Target Pitcher",
            pitch_type=args.pitch,
            release_z_ft=args.rel_z,
            release_velo_mph=args.velo,
            induced_vert_break_in=args.ivb,
            plate_crossing_z_ft=args.plate_z,
            extension_ft=args.ext,
        )
        vtz_res = vtz_eng.evaluate_toz_vaa(vtz_m)

        if args.json:
            vtz_out = {
                "vaa_toz_deg": vtz_res.vaa_toz_deg,
                "toz_flatness_index": vtz_res.toz_flatness_index,
                "whiff_boost_multiplier": vtz_res.whiff_boost_multiplier,
                "tier": vtz_res.vaa_tier,
                "is_deadly": vtz_res.is_deadly_flat_heater,
            }
            print(json_lib.dumps(vtz_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TOP-OF-ZONE VAA DECEPTION [{vtz_res.vaa_tier}]")
            hdr_vt = (
                f"     VAA TOZ: {vtz_res.vaa_toz_deg:>+4.2f}° "
                f"| Flatness Index: {vtz_res.toz_flatness_index:.1f} "
                f"| Whiff Boost: {vtz_res.whiff_boost_multiplier:.3f}x"
            )
            print(hdr_vt)
            print(f"{'=' * 84}\n")
            print(f"  • Approach Angle Tier  : {vtz_res.vaa_tier}")
            print(
                f"  • Deadly Flat Rising   : {'YES' if vtz_res.is_deadly_flat_heater else 'NO'}\n"
            )

    elif args.command == "ambush":
        import json as json_lib

        from mlb_baseball.model.ambush import (
            BatterAmbushEngine,
            BatterAmbushMetrics,
        )

        amb_eng = BatterAmbushEngine()
        amb_m = BatterAmbushMetrics(
            "b1",
            "Target Batter",
            first_pitch_swing_pct=args.swing,
            first_pitch_zone_swing_pct=args.z_swing,
            first_pitch_chase_pct=args.chase,
            first_pitch_hard_hit_pct=args.hard_hit,
            first_pitch_slugging=args.slg,
            first_pitch_pa_count=args.pa,
        )
        amb_res = amb_eng.evaluate_ambush(amb_m)

        if args.json:
            amb_out = {
                "fpav_score": amb_res.fpav_score,
                "fpsv_runs": amb_res.fpsv_runs_saved,
                "tier": amb_res.ambush_tier,
                "is_lethal": amb_res.is_lethal_ambusher,
            }
            print(json_lib.dumps(amb_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     FIRST-PITCH AMBUSH DAMAGE [{amb_res.ambush_tier}]")
            hdr_am = (
                f"     FPAV Score: {amb_res.fpav_score:.1f}/160 "
                f"| Runs Produced: {amb_res.fpsv_runs_saved:>+4.2f} "
                f"| Tier: {amb_res.ambush_tier}"
            )
            print(hdr_am)
            print(f"{'=' * 84}\n")
            print(f"  • Early-Count Strategy : {amb_res.ambush_tier}")
            print(f"  • Lethal 0-0 Ambusher  : {'YES' if amb_res.is_lethal_ambusher else 'NO'}\n")

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

    elif args.command == "blast-angle":
        import json as json_lib

        from mlb_baseball.model.blast_angle import (
            BatterBlastAngleEngine,
            BatterBlastAngleMetrics,
        )

        bla_eng = BatterBlastAngleEngine()
        bla_m = BatterBlastAngleMetrics(
            "b1",
            "Target Batter",
            mean_launch_angle_deg=args.mean_la,
            launch_angle_std_deg=args.std_la,
            sweet_spot_pct=args.sweet_spot,
            power_blast_window_pct=args.blast,
            hard_hit_pct=args.hard_hit,
            bbe_count=args.bbe,
        )
        bla_res = bla_eng.evaluate_blast_angle(bla_m)

        if args.json:
            bla_out = {
                "lwts_score": bla_res.lwts_score,
                "basd_runs": bla_res.basd_runs_saved,
                "tier": bla_res.launch_tier,
                "is_precision": bla_res.is_precision_blaster,
            }
            print(json_lib.dumps(bla_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     LAUNCH WINDOW COMPRESSION & BLAST ANGLE [{bla_res.launch_tier}]")
            hdr_ba = (
                f"     LWTS Score: {bla_res.lwts_score:.1f}/160 "
                f"| Runs Produced: {bla_res.basd_runs_saved:>+4.2f} "
                f"| Tier: {bla_res.launch_tier}"
            )
            print(hdr_ba)
            print(f"{'=' * 84}\n")
            print(f"  • Launch Trajectory Tier : {bla_res.launch_tier}")
            print(
                f"  • Precision Power Blaster: {'YES' if bla_res.is_precision_blaster else 'NO'}\n"
            )

    elif args.command == "velo-delta":
        import json as json_lib

        from mlb_baseball.model.velo_delta import (
            PitcherArsenalSeparationMetrics,
            PitcherVeloDeltaEngine,
        )

        vdl_eng = PitcherVeloDeltaEngine()
        vdl_m = PitcherArsenalSeparationMetrics(
            "p1",
            "Target Pitcher",
            fastball_velo_mph=args.fb_velo,
            changeup_velo_mph=args.ch_velo,
            slider_velo_mph=args.sl_velo,
            curveball_velo_mph=args.cb_velo,
            fastball_ivb_in=args.fb_ivb,
            changeup_ivb_in=args.ch_ivb,
        )
        vdl_res = vdl_eng.evaluate_separation(vdl_m)

        if args.json:
            vdl_out = {
                "fb_ch_velo_delta_mph": vdl_res.fb_ch_velo_delta_mph,
                "fb_ch_ivb_delta_in": vdl_res.fb_ch_ivb_delta_in,
                "vddi_score": vdl_res.vddi_score,
                "whiff_multiplier": vdl_res.whiff_boost_multiplier,
                "tier": vdl_res.separation_tier,
                "is_elite": vdl_res.is_elite_disruptor,
            }
            print(json_lib.dumps(vdl_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     ARSENAL VELO DELTA & SEPARATION [{vdl_res.separation_tier}]")
            hdr_vd = (
                f"     Velo Gap: {vdl_res.fb_ch_velo_delta_mph:>+4.1f} mph "
                f"| Drop Gap: {vdl_res.fb_ch_ivb_delta_in:>+4.1f} in "
                f"| VDDI: {vdl_res.vddi_score:.1f} "
                f"| Whiff: {vdl_res.whiff_boost_multiplier:.3f}x"
            )
            print(hdr_vd)
            print(f"{'=' * 84}\n")
            print(f"  • Arsenal Banding Tier : {vdl_res.separation_tier}")
            print(f"  • Elite Velo Disruptor : {'YES' if vdl_res.is_elite_disruptor else 'NO'}\n")

    elif args.command == "arm-accuracy":
        import json as json_lib

        from mlb_baseball.model.arm_accuracy import (
            OutfieldArmAccuracyEngine,
            OutfieldArmAccuracyMetrics,
        )

        arm_acc_eng = OutfieldArmAccuracyEngine()
        arm_acc_m = OutfieldArmAccuracyMetrics(
            "f1",
            "Target Outfielder",
            position=args.pos,
            max_throw_velo_mph=args.velo,
            on_target_throw_pct=args.accuracy,
            outfield_assists=args.assists,
            runner_hold_pct=args.hold,
            erratic_overthrows=args.overthrows,
            opportunities_count=args.opps,
        )
        arm_acc_res = arm_acc_eng.evaluate_arm(arm_acc_m)

        if args.json:
            arm_acc_out = {
                "position": arm_acc_res.position,
                "asi_score": arm_acc_res.asi_score,
                "rfsv_runs": arm_acc_res.rfsv_runs_saved,
                "tier": arm_acc_res.arm_tier,
                "is_sniper": arm_acc_res.is_dreaded_sniper,
            }
            print(json_lib.dumps(arm_acc_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD ARM ACCURACY & RUNNER FREEZE [{arm_acc_res.arm_tier}]")
            hdr_aa = (
                f"     ASI Score: {arm_acc_res.asi_score:.1f}/160 "
                f"| Runs Saved: {arm_acc_res.rfsv_runs_saved:>+4.2f} "
                f"| Tier: {arm_acc_res.arm_tier}"
            )
            print(hdr_aa)
            print(f"{'=' * 84}\n")
            print(f"  • Arm Classification   : {arm_acc_res.arm_tier}")
            print(
                f"  • Dreaded Sniper Arm   : {'YES' if arm_acc_res.is_dreaded_sniper else 'NO'}\n"
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

    elif args.command == "gyro-spin":
        import json as json_lib

        from mlb_baseball.model.gyro_spin import (
            PitchGyroSpinEngine,
            PitchGyroSpinMetrics,
        )

        gyro_eng = PitchGyroSpinEngine()
        gyro_m = PitchGyroSpinMetrics(
            "p1",
            "Target Pitcher",
            pitch_type=args.pitch,
            total_spin_rpm=args.spin,
            spin_efficiency_pct=args.eff,
            release_velo_mph=args.velo,
            pfx_x_in=args.pfx_x,
            pfx_z_in=args.pfx_z,
        )
        gyro_res = gyro_eng.evaluate_gyro_spin(gyro_m)

        if args.json:
            gyro_out = {
                "pitch_type": gyro_res.pitch_type,
                "gyro_angle_deg": gyro_res.gyro_angle_deg,
                "active_spin_rpm": gyro_res.active_spin_rpm,
                "gyro_spin_rpm": gyro_res.gyro_spin_rpm,
                "tier": gyro_res.aerodynamic_tier,
                "is_bullet": gyro_res.is_pure_bullet_gyro,
            }
            print(json_lib.dumps(gyro_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     3D GYRO SPIN & AERODYNAMICS [{gyro_res.aerodynamic_tier}]")
            hdr_gy = (
                f"     Pitch: {gyro_res.pitch_type} "
                f"| Gyro Angle: {gyro_res.gyro_angle_deg:.1f}° "
                f"| Active Spin: {gyro_res.active_spin_rpm:.0f} rpm "
                f"| Gyro Spin: {gyro_res.gyro_spin_rpm:.0f} rpm"
            )
            print(hdr_gy)
            print(f"{'=' * 84}\n")
            print(f"  • Aerodynamic Tier   : {gyro_res.aerodynamic_tier}")
            print(f"  • Pure Bullet Gyro   : {'YES' if gyro_res.is_pure_bullet_gyro else 'NO'}\n")

    elif args.command == "two-strike":
        import json as json_lib

        from mlb_baseball.model.two_strike import (
            BatterTwoStrikeMetrics,
            TwoStrikeApproachEngine,
        )

        two_s_eng = TwoStrikeApproachEngine()
        two_s_m = BatterTwoStrikeMetrics(
            "b1",
            "Target Batter",
            early_count_whiff_pct=args.early_whiff,
            two_strike_whiff_pct=args.two_whiff,
            early_count_swing_length_ft=args.early_len,
            two_strike_swing_length_ft=args.two_len,
            two_strike_k_pct=args.k_pct,
            two_strike_pa_count=args.pa,
        )
        two_s_res = two_s_eng.evaluate_two_strike(two_s_m)

        if args.json:
            two_s_out = {
                "whiff_reduction_pct": two_s_res.whiff_reduction_pct,
                "swing_shortened_ft": two_s_res.swing_shortened_ft,
                "tsbe_score": two_s_res.tsbe_score,
                "surplus_runs": two_s_res.surplus_runs,
                "tier": two_s_res.approach_tier,
                "is_elite": two_s_res.is_elite_battler,
            }
            print(json_lib.dumps(two_s_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TWO-STRIKE APPROACH & SHORTENING [{two_s_res.approach_tier}]")
            hdr_ts = (
                f"     Whiff Cut: {two_s_res.whiff_reduction_pct:>+4.1f}% "
                f"| Shortened: {two_s_res.swing_shortened_ft:>+4.2f} ft "
                f"| TSBE Index: {two_s_res.tsbe_score:.1f} "
                f"| Runs Saved: {two_s_res.surplus_runs:>+4.2f}"
            )
            print(hdr_ts)
            print(f"{'=' * 84}\n")
            print(f"  • Approach Archetype   : {two_s_res.approach_tier}")
            print(f"  • Elite 2-Strike Batter: {'YES' if two_s_res.is_elite_battler else 'NO'}\n")

    elif args.command == "pivot-dp":
        import json as json_lib

        from mlb_baseball.model.pivot_dp import (
            InfieldPivotDPEngine,
            InfieldPivotMetrics,
        )

        piv_eng = InfieldPivotDPEngine()
        piv_m = InfieldPivotMetrics(
            "f1",
            "Target Infielder",
            position=args.pos,
            pivot_turn_time_s=args.turn,
            relay_throw_velo_mph=args.throw_velo,
            double_plays_turned=args.turned,
            double_play_opportunities=args.opps,
        )
        piv_res = piv_eng.evaluate_pivot(piv_m)

        if args.json:
            piv_out = {
                "position": piv_res.position,
                "conversion_pct": piv_res.dp_conversion_pct,
                "dpti_score": piv_res.dpti_score,
                "dpts_runs": piv_res.dpts_runs_saved,
                "tier": piv_res.pivot_tier,
                "is_lightning": piv_res.is_lightning_turner,
            }
            print(json_lib.dumps(piv_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     INFIELD DOUBLE PLAY PIVOT KINEMATICS [{piv_res.pivot_tier}]")
            hdr_pv = (
                f"     DP Conv%: {piv_res.dp_conversion_pct:.1f}% "
                f"| DPTI Score: {piv_res.dpti_score:.1f} "
                f"| Runs Saved: {piv_res.dpts_runs_saved:>+4.2f}"
            )
            print(hdr_pv)
            print(f"{'=' * 84}\n")
            print(f"  • Pivot Classification : {piv_res.pivot_tier}")
            print(f"  • Lightning Pivot Turn : {'YES' if piv_res.is_lightning_turner else 'NO'}\n")

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

    elif args.command == "contact-depth":
        import json as json_lib

        from mlb_baseball.model.contact_depth import (
            ContactDepthEngine,
            ContactKinematicsInput,
        )

        cdp_eng = ContactDepthEngine()
        cdp_m = ContactKinematicsInput(
            "b1",
            "Target Hitter",
            contact_y_inches=args.depth,
            pitch_velo_mph=args.velo,
            pitch_location_x_inches=args.x_loc,
            spray_angle_deg=args.spray,
            exit_velo_mph=args.ev,
            batter_side=args.side,
        )
        cdp_res = cdp_eng.evaluate_contact(cdp_m)

        if args.json:
            cdp_out = {
                "contact_depth_in": cdp_res.contact_depth_in,
                "optimal_depth_in": cdp_res.optimal_depth_in,
                "depth_margin_in": cdp_res.depth_margin_in,
                "timing_efficiency_pct": cdp_res.timing_efficiency_pct,
                "tier": cdp_res.depth_tier,
                "is_out_front": cdp_res.is_out_front_slugger,
            }
            print(json_lib.dumps(cdp_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     POINT OF IMPACT CONTACT DEPTH [{cdp_res.depth_tier}]")
            hdr_cd = (
                f"     Contact Depth: {cdp_res.contact_depth_in:>+4.1f} in "
                f"| Optimal: {cdp_res.optimal_depth_in:>+4.1f} in "
                f"| Margin: {cdp_res.depth_margin_in:>+4.1f} in "
                f"| Timing Eff: {cdp_res.timing_efficiency_pct:.1f}%"
            )
            print(hdr_cd)
            print(f"{'=' * 84}\n")
            print(f"  • Contact Archetype  : {cdp_res.depth_tier}")
            print(f"  • Out-Front Slugger  : {'YES' if cdp_res.is_out_front_slugger else 'NO'}\n")

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

    elif args.command == "catcher-pop":
        import json as json_lib

        from mlb_baseball.model.catcher_pop import (
            CatcherPopAndBlockEngine,
            CatcherPopAndBlockMetrics,
        )

        cpop_eng = CatcherPopAndBlockEngine()
        cpop_m = CatcherPopAndBlockMetrics(
            "c1",
            "Target Catcher",
            clean_pop_time_s=args.pop,
            block_recovery_time_s=args.recovery,
            dirt_throw_velo_mph=args.throw_velo,
            wild_pitches_prevented=args.wp_saved,
            dirt_caught_stealing=args.dirt_cs,
            passed_balls=args.pb,
        )
        cpop_res = cpop_eng.evaluate_catcher(cpop_m)

        if args.json:
            cpop_out = {
                "total_time_s": cpop_res.total_block_throw_time_s,
                "deterrence_pct": cpop_res.advancement_deterrence_pct,
                "btsv_runs": cpop_res.btsv_runs_saved,
                "tier": cpop_res.catcher_tier,
                "is_elite": cpop_res.is_elite_backstop,
            }
            print(json_lib.dumps(cpop_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CATCHER BLOCK-TO-THROW & POP [{cpop_res.catcher_tier}]")
            hdr_cp = (
                f"     Block+Throw Time: {cpop_res.total_block_throw_time_s:.2f}s "
                f"| Deterrence: {cpop_res.advancement_deterrence_pct:.1f}% "
                f"| BTSV Runs: {cpop_res.btsv_runs_saved:>+4.2f}"
            )
            print(hdr_cp)
            print(f"{'=' * 84}\n")
            print(f"  • Backstop Archetype   : {cpop_res.catcher_tier}")
            print(f"  • Elite Defense Cannon : {'YES' if cpop_res.is_elite_backstop else 'NO'}\n")

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

    elif args.command == "xslg":
        import json as json_lib

        from mlb_baseball.model.xslg import (
            BatterContactBins,
            XSLGPowerEngine,
        )

        xslg_eng = XSLGPowerEngine()
        xslg_m = BatterContactBins(
            "b1",
            "Target Hitter",
            barrel_count=args.barrels,
            solid_contact_count=args.solid,
            flare_burner_count=args.flares,
            under_count=args.under,
            topped_count=args.topped,
            weak_count=args.weak,
            actual_iso=args.iso,
        )
        xslg_res = xslg_eng.evaluate_power(xslg_m)

        if args.json:
            xslg_out = {
                "expected_xslg": xslg_res.expected_xslg,
                "expected_xiso": xslg_res.expected_xiso,
                "actual_iso": xslg_res.actual_iso,
                "tpce_pct": xslg_res.tpce_efficiency_pct,
                "tier": xslg_res.power_tier,
                "is_elite": xslg_res.is_elite_slugger,
            }
            print(json_lib.dumps(xslg_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     EXPECTED SLUGGING & ISO POWER [{xslg_res.power_tier}]")
            hdr_xs = (
                f"     xSLG: {xslg_res.expected_xslg:.3f} "
                f"| xISO: {xslg_res.expected_xiso:.3f} "
                f"| Actual ISO: {xslg_res.actual_iso:.3f} "
                f"| TPCE: {xslg_res.tpce_efficiency_pct:.1f}%"
            )
            print(hdr_xs)
            print(f"{'=' * 84}\n")
            print(f"  • Power Profile Tier   : {xslg_res.power_tier}")
            print(f"  • Elite Barrel Slugger : {'YES' if xslg_res.is_elite_slugger else 'NO'}\n")

    elif args.command == "velo-drift":
        import json as json_lib

        from mlb_baseball.model.velo_drift import (
            FastballVeloDriftEngine,
            PitcherVeloProfile,
        )

        vdr_eng = FastballVeloDriftEngine()
        vdr_m = PitcherVeloProfile(
            "p1",
            "Target Pitcher",
            early_game_velo_mph=args.early,
            late_game_velo_mph=args.late,
            pitch_count_total=args.pitches,
            early_spin_rpm=args.early_spin,
            late_spin_rpm=args.late_spin,
        )
        vdr_res = vdr_eng.evaluate_velo_drift(vdr_m)

        if args.json:
            vdr_out = {
                "velo_drift_mph": vdr_res.velo_drift_mph,
                "fvri_score": vdr_res.fvri_score,
                "hr_multiplier": vdr_res.hr_vulnerability_multiplier,
                "tier": vdr_res.fatigue_tier,
                "is_hook": vdr_res.is_severe_hook_candidate,
            }
            print(json_lib.dumps(vdr_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     FASTBALL VELOCITY DRIFT [{vdr_res.fatigue_tier}]")
            hdr_vd = (
                f"     Velo Drift: {vdr_res.velo_drift_mph:>+4.2f} mph "
                f"| FVRI Retention: {vdr_res.fvri_score:.1f}/100 "
                f"| HR Mult: {vdr_res.hr_vulnerability_multiplier:.2f}x"
            )
            print(hdr_vd)
            print(f"{'=' * 84}\n")
            print(f"  • Fatigue Classification : {vdr_res.fatigue_tier}")
            hook_txt = "YES" if vdr_res.is_severe_hook_candidate else "NO"
            print(f"  • Severe Hook Candidate  : {hook_txt}")

    elif args.command == "catch-prob":
        import json as json_lib

        from mlb_baseball.model.catch_prob import (
            OutfieldCatchProbEngine,
            OutfieldPlayOpportunity,
        )

        cp_eng = OutfieldCatchProbEngine()
        cp_m = OutfieldPlayOpportunity(
            "f1",
            "Target Fielder",
            distance_needed_ft=args.dist,
            hang_time_s=args.hang,
            direction_angle_deg=args.angle,
            sprint_speed_fps=args.speed,
            was_caught=args.caught,
        )
        cp_res = cp_eng.evaluate_opportunity(cp_m)

        if args.json:
            cp_out = {
                "catch_prob_pct": cp_res.catch_probability_pct,
                "star_rating": cp_res.star_rating,
                "oaa_added": cp_res.oaa_added,
                "is_highlight": cp_res.is_highlight_catch,
            }
            print(json_lib.dumps(cp_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD CATCH PROBABILITY [{cp_res.star_rating}]")
            hdr_cp = (
                f"     Catch Probability: {cp_res.catch_probability_pct:.1f}% "
                f"| Star Rating: {cp_res.star_rating} "
                f"| OAA Added: {cp_res.oaa_added:>+5.3f}"
            )
            print(hdr_cp)
            print(f"{'=' * 84}\n")
            print(f"  • Star Classification  : {cp_res.star_rating}")
            print(f"  • Highlight Play       : {'YES' if cp_res.is_highlight_catch else 'NO'}\n")

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

    elif args.command == "pull-air":
        import json as json_lib

        from mlb_baseball.model.pull_air import (
            BatterPullAirMetrics,
            PullAirPowerEngine,
        )

        pair_eng = PullAirPowerEngine()
        pair_m = BatterPullAirMetrics(
            "b1",
            "Target Hitter",
            pulled_air_count=args.pull_air,
            total_air_count=args.total_air,
            pulled_air_hr=args.pull_hr,
            total_hr=args.hr,
        )
        pair_res = pair_eng.evaluate_pull_air(pair_m)

        if args.json:
            pair_out = {
                "pull_air_pct": pair_res.pull_air_pct,
                "delta_league": pair_res.pulled_air_delta_league,
                "padm_multiplier": pair_res.padm_multiplier,
                "archetype": pair_res.strategy_archetype,
                "is_elite": pair_res.is_elite_pull_air_hitter,
            }
            print(json_lib.dumps(pair_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PULLED-AIR POWER POLARIZATION [{pair_res.strategy_archetype}]")
            hdr_pa = (
                f"     Pull-Air%: {pair_res.pull_air_pct:.1f}% "
                f"| Delta: {pair_res.pulled_air_delta_league:>+4.1f}% "
                f"| PADM: {pair_res.padm_multiplier:.2f}x"
            )
            print(hdr_pa)
            print(f"{'=' * 84}\n")
            print(f"  • Strategy Archetype   : {pair_res.strategy_archetype}")
            print(
                f"  • Elite Pull-Air Hitter: {'YES' if pair_res.is_elite_pull_air_hitter else 'NO'}"
            )

    elif args.command == "haa":
        import json as json_lib

        from mlb_baseball.model.haa import (
            HorizontalApproachAngleEngine,
            PitchHorizontalKinematics,
        )

        haa_eng = HorizontalApproachAngleEngine()
        haa_m = PitchHorizontalKinematics(
            "p1",
            "Target Pitcher",
            pitch_type=args.pitch,
            release_x_ft=args.rel_x,
            plate_x_ft=args.plate_x,
            pfx_x_in=args.hb,
            release_velo_mph=args.velo,
        )
        haa_res = haa_eng.evaluate_haa(haa_m)

        if args.json:
            haa_out = {
                "pitch_type": haa_res.pitch_type,
                "haa_deg": haa_res.calculated_haa_deg,
                "deception_score": haa_res.cross_body_deception_score,
                "tier": haa_res.haa_tier,
            }
            print(json_lib.dumps(haa_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     HORIZONTAL APPROACH ANGLE [{haa_res.haa_tier}]")
            hdr_ha = (
                f"     Pitch: {haa_res.pitch_type} "
                f"| HAA: {haa_res.calculated_haa_deg:>+4.2f}° "
                f"| Cross-Body Deception: {haa_res.cross_body_deception_score:.1f}/100"
            )
            print(hdr_ha)
            print(f"{'=' * 84}\n")
            print(f"  • Approach Classification: {haa_res.haa_tier}\n")

    elif args.command == "bunt":
        import json as json_lib

        from mlb_baseball.model.bunt import (
            InfieldBuntDefenseEngine,
            InfieldBuntDefenseMetrics,
        )

        bunt_eng = InfieldBuntDefenseEngine()
        bunt_m = InfieldBuntDefenseMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            lead_runner_outs=args.lead_outs,
            bunt_popups_caught=args.popups,
            bunt_hits_allowed=args.hits,
            total_bunt_attempts=args.attempts,
        )
        bunt_res = bunt_eng.evaluate_bunt_defense(bunt_m)

        if args.json:
            bunt_out = {
                "position": bunt_res.position,
                "total_bunt_runs": bunt_res.total_bunt_runs_saved,
                "lead_kill_pct": bunt_res.lead_runner_kill_pct,
                "tier": bunt_res.defense_tier,
                "is_elite": bunt_res.is_elite_bunt_defender,
            }
            print(json_lib.dumps(bunt_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     INFIELD BUNT DEFENSE [{bunt_res.defense_tier}]")
            hdr_bu = (
                f"     Lead Out Kill%: {bunt_res.lead_runner_kill_pct:.1f}% "
                f"| Bunt Runs Saved: {bunt_res.total_bunt_runs_saved:>+4.2f} "
                f"| Position: {bunt_res.position}"
            )
            print(hdr_bu)
            print(f"{'=' * 84}\n")
            print(f"  • Defense Classification : {bunt_res.defense_tier}")
            print(
                f"  • Elite Bunt Eraser      : {'YES' if bunt_res.is_elite_bunt_defender else 'NO'}"
            )

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

    elif args.command == "vaa":
        import json as json_lib

        from mlb_baseball.model.vaa import (
            PitchApproachKinematics,
            VerticalApproachAngleEngine,
        )

        vaa_eng = VerticalApproachAngleEngine()
        vaa_m = PitchApproachKinematics(
            "p1",
            "Target Pitcher",
            pitch_type=args.pitch,
            release_height_ft=args.rel_z,
            plate_z_ft=args.plate_z,
            pfx_z_in=args.ivb,
            release_velo_mph=args.velo,
        )
        vaa_res = vaa_eng.evaluate_vaa(vaa_m)

        if args.json:
            vaa_out = {
                "pitch_type": vaa_res.pitch_type,
                "vaa_deg": vaa_res.calculated_vaa_deg,
                "whiff_boost_pct": vaa_res.whiff_boost_pct,
                "tier": vaa_res.approach_tier,
            }
            print(json_lib.dumps(vaa_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     VERTICAL APPROACH ANGLE [{vaa_res.approach_tier}]")
            hdr_va = (
                f"     Pitch: {vaa_res.pitch_type} "
                f"| VAA: {vaa_res.calculated_vaa_deg:>+4.2f}° "
                f"| Whiff Boost: +{vaa_res.whiff_boost_pct:.1f}%"
            )
            print(hdr_va)
            print(f"{'=' * 84}\n")
            print(f"  • Approach Classification: {vaa_res.approach_tier}\n")

    elif args.command == "iffb":
        import json as json_lib

        from mlb_baseball.model.iffb import (
            InfieldFlyBallEngine,
            PitcherIFFBMetrics,
        )

        iffb_eng = InfieldFlyBallEngine()
        iffb_m = PitcherIFFBMetrics(
            "p1",
            "Target Pitcher",
            iffb_count=args.iffb,
            fb_count=args.fb,
            pa_faced=args.pa,
        )
        iffb_res = iffb_eng.evaluate_iffb(iffb_m)

        if args.json:
            iffb_out = {
                "iffb_pct": iffb_res.iffb_pct,
                "delta_league": iffb_res.iffb_delta_league,
                "surplus_runs": iffb_res.popup_surplus_runs,
                "tier": iffb_res.popup_tier,
                "is_elite": iffb_res.is_elite_popup_artist,
            }
            print(json_lib.dumps(iffb_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     INFIELD FLY BALL INDUCTION [{iffb_res.popup_tier}]")
            hdr_if = (
                f"     IFFB%: {iffb_res.iffb_pct:.1f}% "
                f"| Delta: {iffb_res.iffb_delta_league:>+4.1f}% "
                f"| Surplus Runs Saved: {iffb_res.popup_surplus_runs:>+4.1f}"
            )
            print(hdr_if)
            print(f"{'=' * 84}\n")
            print(f"  • Induction Tier   : {iffb_res.popup_tier}")
            print(f"  • Elite Popup Arm  : {'YES' if iffb_res.is_elite_popup_artist else 'NO'}\n")

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

    elif args.command == "sweetspot":
        import json as json_lib

        from mlb_baseball.model.sweetspot import (
            BatterContactGeometry,
            SweetSpotEngine,
        )

        sws_eng = SweetSpotEngine()
        sws_m = BatterContactGeometry(
            "b1",
            "Target Hitter",
            sweet_spot_pct=args.sws,
            hard_hit_pct=args.hh,
            ideal_contact_rate=args.icr,
            la_std_dev=args.std,
        )
        sws_res = sws_eng.evaluate_contact(sws_m)

        if args.json:
            sws_out = {
                "ideal_contact_rate": sws_res.ideal_contact_rate,
                "contact_quality_score": sws_res.contact_quality_score,
                "archetype": sws_res.launch_path_archetype,
                "is_elite": sws_res.is_elite_ball_striker,
            }
            print(json_lib.dumps(sws_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     SWEET-SPOT CONTACT GEOMETRY [{sws_res.launch_path_archetype}]")
            hdr_sw = (
                f"     Ideal Contact Rate: {sws_res.ideal_contact_rate:.1f}% "
                f"| Contact Quality Score: {sws_res.contact_quality_score:.1f}/100"
            )
            print(hdr_sw)
            print(f"{'=' * 84}\n")
            print(f"  • Launch Path Archetype : {sws_res.launch_path_archetype}")
            print(
                f"  • Elite Ball Striker    : {'YES' if sws_res.is_elite_ball_striker else 'NO'}\n"
            )

    elif args.command == "putaway":
        import json as json_lib

        from mlb_baseball.model.putaway import (
            PitcherPutAwayEngine,
            PitcherPutAwayMetrics,
        )

        put_eng = PitcherPutAwayEngine()
        put_m = PitcherPutAwayMetrics(
            "p1",
            "Target Pitcher",
            putaway_pct=args.putaway,
            two_strike_pitches=args.pitches,
            whiff_2strike_pct=args.whiff,
        )
        put_res = put_eng.evaluate_putaway(put_m)

        if args.json:
            put_out = {
                "putaway_pct": put_res.putaway_pct,
                "delta_league": put_res.putaway_delta_league,
                "pasi_runs": put_res.pasi_runs_saved,
                "tier": put_res.finisher_tier,
                "is_elite": put_res.is_elite_putaway_arm,
            }
            print(json_lib.dumps(put_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TWO-STRIKE PUT-AWAY CONVERSION [{put_res.finisher_tier}]")
            hdr_pu = (
                f"     Put-Away%: {put_res.putaway_pct * 100:.1f}% "
                f"| Delta: {put_res.putaway_delta_league * 100:>+4.1f}% "
                f"| PASI Runs Saved: {put_res.pasi_runs_saved:>+4.1f}"
            )
            print(hdr_pu)
            print(f"{'=' * 84}\n")
            print(f"  • Finisher Classification: {put_res.finisher_tier}")
            print(
                f"  • Elite Strikeout Arm    : {'YES' if put_res.is_elite_putaway_arm else 'NO'}\n"
            )

    elif args.command == "wall":
        import json as json_lib

        from mlb_baseball.model.wall import (
            OutfielderWallMetrics,
            OutfieldWallEngine,
        )

        wall_eng = OutfieldWallEngine()
        wall_m = OutfielderWallMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            hr_robberies=args.robberies,
            extra_base_wall_catches=args.wall_catches,
            wall_crashes_unsuccessful=args.fails,
            opportunities=args.opps,
        )
        wall_res = wall_eng.evaluate_wall_defense(wall_m)

        if args.json:
            wall_out = {
                "position": wall_res.position,
                "hr_robberies": wall_res.hr_robberies,
                "total_wall_runs": wall_res.total_wall_runs_saved,
                "success_pct": wall_res.wall_catch_success_pct,
                "tier": wall_res.wall_defense_tier,
            }
            print(json_lib.dumps(wall_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD WALL COLLISION & ROBBERY [{wall_res.wall_defense_tier}]")
            hdr_wl = (
                f"     HR Robberies: {wall_res.hr_robberies} "
                f"| Success Rate: {wall_res.wall_catch_success_pct:.1f}% "
                f"| Wall Runs Saved: {wall_res.total_wall_runs_saved:>+4.1f}"
            )
            print(hdr_wl)
            print(f"{'=' * 84}\n")
            print(f"  • Defense Classification : {wall_res.wall_defense_tier}")
            print(f"  • Net Wall Run Prevention: {wall_res.total_wall_runs_saved:>+4.1f} runs\n")

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

    elif args.command == "zone-swing":
        import json as json_lib

        from mlb_baseball.model.zone_swing import (
            BatterZoneSwingMetrics,
            ZoneSwingVulnerabilityEngine,
        )

        zsw_eng = ZoneSwingVulnerabilityEngine()
        zsw_m = BatterZoneSwingMetrics(
            "b1",
            "Target Hitter",
            z_swing_pct=args.z_swing,
            z_contact_pct=args.z_contact,
            o_swing_pct=args.o_swing,
            o_contact_pct=args.o_contact,
        )
        zsw_res = zsw_eng.evaluate_discipline(zsw_m)

        if args.json:
            zsw_out = {
                "zone_contact_deficit": zsw_res.zone_contact_deficit,
                "chase_efficiency_ratio": zsw_res.chase_efficiency_ratio,
                "archetype": zsw_res.vulnerability_archetype,
                "is_target": zsw_res.is_exploitable_whiff_target,
            }
            print(json_lib.dumps(zsw_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     ZONE SWING & CHASE DISCIPLINE [{zsw_res.vulnerability_archetype}]")
            hdr_zs = (
                f"     Zone Contact Deficit: {zsw_res.zone_contact_deficit:>+5.3f} "
                f"| Chase Efficiency Ratio: {zsw_res.chase_efficiency_ratio:.2f}"
            )
            print(hdr_zs)
            print(f"{'=' * 84}\n")
            print(f"  • Vulnerability Archetype: {zsw_res.vulnerability_archetype}")
            exp_whiff = "YES" if zsw_res.is_exploitable_whiff_target else "NO"
            print(f"  • Exploitable Whiff Target: {exp_whiff}\n")

    elif args.command == "fstrike":
        import json as json_lib

        from mlb_baseball.model.fstrike import (
            FirstPitchStrikeEngine,
            PitcherFStrikeMetrics,
        )

        fps_eng = FirstPitchStrikeEngine()
        fps_m = PitcherFStrikeMetrics(
            "p1",
            "Target Pitcher",
            fstrike_pct=args.fps,
            batters_faced=args.bf,
        )
        fps_res = fps_eng.evaluate_fstrike(fps_m)

        if args.json:
            fps_out = {
                "fstrike_pct": fps_res.fstrike_pct,
                "delta_league": fps_res.fps_delta_league,
                "fpsv_season": fps_res.fpsv_runs_seasonal,
                "fpsv_100": fps_res.fpsv_per_100_bf,
                "tier": fps_res.command_tier,
            }
            print(json_lib.dumps(fps_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     FIRST-PITCH STRIKE SURPLUS VALUE [{fps_res.command_tier}]")
            hdr_fp = (
                f"     F-Strike%: {fps_res.fstrike_pct * 100:.1f}% "
                f"| Delta: {fps_res.fps_delta_league * 100:>+4.1f}% "
                f"| Seasonal Surplus: {fps_res.fpsv_runs_seasonal:>+4.1f} runs"
            )
            print(hdr_fp)
            print(f"{'=' * 84}\n")
            print(f"  • Command Classification : {fps_res.command_tier}")
            print(f"  • FPSV Per 100 Batters  : {fps_res.fpsv_per_100_bf:>+4.2f} runs\n")

    elif args.command == "pop-time":
        import json as json_lib

        from mlb_baseball.model.poptime import (
            CatcherPopTimeEngine,
            CatcherPopTimeMetrics,
        )

        pop_eng = CatcherPopTimeEngine()
        pop_m = CatcherPopTimeMetrics(
            "c1",
            "Target Catcher",
            pop_time_s=args.pop,
            arm_velocity_mph=args.arm,
            attempts_faced=args.att,
        )
        pop_res = pop_eng.evaluate_pop_time(pop_m)

        if args.json:
            pop_out = {
                "pop_time_s": pop_res.pop_time_s,
                "arm_velocity_mph": pop_res.arm_velocity_mph,
                "expected_cs_pct": pop_res.expected_cs_pct,
                "csaa_runs": pop_res.csaa_runs_saved,
                "tier": pop_res.catcher_tier,
            }
            print(json_lib.dumps(pop_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CATCHER POP TIME & CAUGHT STEALING [{pop_res.catcher_tier}]")
            hdr_pt = (
                f"     Pop Time: {pop_res.pop_time_s:.2f}s "
                f"| Expected CS%: {pop_res.expected_cs_pct:.1f}% "
                f"| CSAA Runs: {pop_res.csaa_runs_saved:>+4.1f}"
            )
            print(hdr_pt)
            print(f"{'=' * 84}\n")
            print(f"  • Throwing Classification: {pop_res.catcher_tier}")
            print(f"  • Seasonal Run Value     : {pop_res.csaa_runs_saved:>+4.1f} runs\n")

    elif args.command == "re24-heatmap":
        from mlb_baseball.visual import (
            BaseOutRunExpectancyGrid,
            RunExpectancyHeatmapRenderer,
        )

        re24_renderer = RunExpectancyHeatmapRenderer()
        grid = BaseOutRunExpectancyGrid(args.title)
        chart = re24_renderer.render(grid)
        print(f"Generated Vector SVG RE24 Matrix Heatmap ({len(chart.svg_content)} bytes)")

    elif args.command == "clutch":
        import json as json_lib

        from mlb_baseball.model.clutch import (
            BatterClutchEngine,
            BatterClutchRawStats,
        )

        clutch_eng = BatterClutchEngine()
        clutch_st = BatterClutchRawStats(
            "b1",
            "Target Hitter",
            woba_overall=args.overall,
            pa_high_li=args.pa_high,
            woba_high_li=args.woba_high,
            wpa=args.wpa,
            pli=args.pli,
        )
        clutch_res = clutch_eng.evaluate_clutch(clutch_st)

        if args.json:
            clutch_out = {
                "shrunk_high_li_woba": clutch_res.shrunk_high_li_woba,
                "clutch_woba_delta": clutch_res.clutch_woba_delta,
                "clutch_index": clutch_res.clutch_index,
                "tier": clutch_res.clutch_tier,
                "is_asset": clutch_res.is_high_leverage_asset,
            }
            print(json_lib.dumps(clutch_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BATTER CLUTCH PERFORMANCE [{clutch_res.clutch_tier}]")
            hdr_cl = (
                f"     High-LI Shrunk wOBA: {clutch_res.shrunk_high_li_woba:.3f} "
                f"| Delta: {clutch_res.clutch_woba_delta:>+5.3f} "
                f"| Clutch Index: {clutch_res.clutch_index:>+5.2f}"
            )
            print(hdr_cl)
            print(f"{'=' * 84}\n")
            print(f"  • Clutch Classification : {clutch_res.clutch_tier}")
            hl_asset = "YES" if clutch_res.is_high_leverage_asset else "NO"
            print(f"  • High-Leverage Asset   : {hl_asset}\n")

    elif args.command == "arm":
        import json as json_lib

        from mlb_baseball.model.arm import (
            OutfieldArmEngine,
            OutfielderArmMetrics,
        )

        arm_eng = OutfieldArmEngine()
        arm_m = OutfielderArmMetrics(
            "f1",
            "Target Fielder",
            position=args.pos,
            arm_velocity_mph=args.velo,
            exchange_time_s=args.exchange,
        )
        arm_res = arm_eng.evaluate_arm(arm_m)

        if args.json:
            arm_out = {
                "position": arm_res.position,
                "arm_velocity_mph": arm_res.arm_velocity_mph,
                "throw_arrival_time_s": arm_res.throw_arrival_time_s,
                "hold_rate_pct": arm_res.hold_rate_pct,
                "arm_runs_saved_season": arm_res.arm_runs_saved_season,
                "tier": arm_res.arm_tier,
            }
            print(json_lib.dumps(arm_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     OUTFIELD ARM STRENGTH & RUNNER HOLD [{arm_res.arm_tier}]")
            hdr_ar = (
                f"     Velo: {arm_res.arm_velocity_mph:.1f}mph "
                f"| Arrival: {arm_res.throw_arrival_time_s:.2f}s "
                f"| Hold%: {arm_res.hold_rate_pct:.1f}% "
                f"| ARM: {arm_res.arm_runs_saved_season:>+4.1f} runs"
            )
            print(hdr_ar)
            print(f"{'=' * 84}\n")
            print(f"  • Arm Classification : {arm_res.arm_tier}")
            print(f"  • 162-Game Run Impact: {arm_res.arm_runs_saved_season:>+4.1f} runs\n")

    elif args.command == "arsenal":
        import json as json_lib

        from mlb_baseball.model.diversity import (
            ArsenalDiversityEngine,
            DiversityArsenalMix,
        )

        div_eng = ArsenalDiversityEngine()
        sample_mix = DiversityArsenalMix(
            "p1",
            args.pitcher,
            args.count,
            {"FF": 0.32, "SL": 0.26, "CH": 0.18, "CU": 0.14, "SI": 0.10},
        )
        div_res = div_eng.evaluate_diversity(sample_mix)

        if args.json:
            div_out = {
                "pitcher": div_res.pitcher_name,
                "pitch_count": div_res.pitch_count,
                "diversity_index": div_res.diversity_index,
                "entropy_bits": div_res.entropy_bits,
                "tier": div_res.repertoire_tier,
                "predictable": div_res.is_highly_predictable,
            }
            print(json_lib.dumps(div_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCH ARSENAL DIVERSITY [{div_res.repertoire_tier}]")
            hdr_di = (
                f"     Pitches: {div_res.pitch_count} "
                f"| Diversity Index: {div_res.diversity_index:.2f}/1.00 "
                f"| Entropy: {div_res.entropy_bits:.2f} bits"
            )
            print(hdr_di)
            print(f"{'=' * 84}\n")
            print(f"  • Repertoire Tier   : {div_res.repertoire_tier}")
            print(
                f"  • Predictability Risk: {'HIGH' if div_res.is_highly_predictable else 'LOW'}\n"
            )

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

    elif args.command == "spray":
        import json as json_lib

        from mlb_baseball.model.spray import (
            BatterSprayMetrics,
            SprayDirectionEngine,
        )

        spray_eng = SprayDirectionEngine()
        spray_m = BatterSprayMetrics(
            "b1",
            "Target Hitter",
            pull_pct=args.pull,
            center_pct=args.center,
            oppo_pct=args.oppo,
            hr_pull=args.hr_pull,
            hr_total=args.hr_total,
        )
        spray_res = spray_eng.evaluate_spray(spray_m)

        if args.json:
            spray_out = {
                "pull_power_concentration_pct": spray_res.pull_power_concentration_pct,
                "spray_neutrality_index": spray_res.spray_neutrality_index,
                "archetype": spray_res.spray_archetype,
                "dead_pull_liability": spray_res.is_dead_pull_liability,
            }
            print(json_lib.dumps(spray_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BATTER SPRAY & PULL POWER [{spray_res.spray_archetype}]")
            hdr_spry = (
                f"     Pull Power Concentration: {spray_res.pull_power_concentration_pct:.1f}% "
                f"| Neutrality Index: {spray_res.spray_neutrality_index:.2f}/1.00"
            )
            print(hdr_spry)
            print(f"{'=' * 84}\n")
            print(f"  • Spray Archetype     : {spray_res.spray_archetype}")
            print(
                f"  • Dead-Pull Liability : {'YES' if spray_res.is_dead_pull_liability else 'NO'}\n"
            )

    elif args.command == "tto":
        import json as json_lib

        from mlb_baseball.model.tto import (
            PitcherTTOMetrics,
            TimesThroughOrderEngine,
        )

        tto_eng = TimesThroughOrderEngine()
        tto_m = PitcherTTOMetrics(
            "p1",
            "Target Starter",
            tto1_woba=args.tto1_woba,
            tto2_woba=args.tto2_woba,
            tto3_woba=args.tto3_woba,
            tto1_k_pct=args.tto1_k,
            tto3_k_pct=args.tto3_k,
        )
        tto_res = tto_eng.evaluate_tto(tto_m)

        if args.json:
            tto_out = {
                "tto_woba_delta_3_1": tto_res.tto_woba_delta_3_1,
                "tto_k_delta_3_1": tto_res.tto_k_delta_3_1,
                "ttvi": tto_res.third_time_vulnerability_index,
                "hook_policy": tto_res.recommended_hook_policy,
            }
            print(json_lib.dumps(tto_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TIMES-THROUGH-ORDER DEGRADATION [{tto_res.recommended_hook_policy}]")
            hdr_tt = (
                f"     TTVI: {tto_res.third_time_vulnerability_index:.1f}/100 "
                f"| 3rd-Pass wOBA Delta: {tto_res.tto_woba_delta_3_1:>+5.3f} "
                f"| K% Delta: {tto_res.tto_k_delta_3_1:>+5.3f}"
            )
            print(hdr_tt)
            print(f"{'=' * 84}\n")
            print(f"  • Recommended Hook : {tto_res.recommended_hook_policy}")
            print(f"  • Familiarity Risk : {tto_res.third_time_vulnerability_index:.1f}/100\n")

    elif args.command == "carry":
        import json as json_lib

        from mlb_baseball.model.carry import (
            BallparkCarryScannerEngine,
            BattedBallTrajectory,
        )

        carry_eng = BallparkCarryScannerEngine()
        traj = BattedBallTrajectory("h1", args.ev, args.la, args.spray, args.dist)
        carry_res = carry_eng.scan_ballparks(traj)

        if args.json:
            carry_out = {
                "hr_count": carry_res.parks_hr_count,
                "total_parks": carry_res.total_parks_evaluated,
                "hr_pct": carry_res.hr_percentage,
                "hr_venues": carry_res.home_run_venues,
                "summary": carry_res.scan_summary,
            }
            print(json_lib.dumps(carry_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     30-BALLPARK CARRY SCANNER [{carry_res.scan_summary}]")
            hdr_cr = (
                f"     Distance: {carry_res.nominal_distance_ft:.0f}ft "
                f"| HR in {carry_res.parks_hr_count}/{carry_res.total_parks_evaluated} "
                f"MLB Stadiums ({carry_res.hr_percentage:.1f}%)"
            )
            print(hdr_cr)
            print(f"{'=' * 84}\n")
            hr_v = ", ".join(carry_res.home_run_venues) if carry_res.home_run_venues else "None"
            out_v = ", ".join(carry_res.out_venues) if carry_res.out_venues else "None"
            print(f"  • Home Run Venues ({len(carry_res.home_run_venues)}) : {hr_v}")
            print(f"  • Flyout Venues   ({len(carry_res.out_venues)}) : {out_v}\n")

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

    elif args.command == "damage":
        import json as json_lib

        from mlb_baseball.model.damage import (
            BattedBallContact,
            BatterContactProfile,
            ContactDamageEngine,
        )

        dmg_eng = ContactDamageEngine()
        hits = [
            BattedBallContact("c1", args.ev, args.la),
            BattedBallContact("c2", 98.0, 24.0),
            BattedBallContact("c3", 92.0, 15.0),
        ]
        profile = BatterContactProfile("b1", "Sample Batter", hits)
        dmg_res = dmg_eng.evaluate_damage(profile)

        if args.json:
            dmg_out = {
                "damage_rate_pct": dmg_res.damage_rate_pct,
                "expected_damage_value": dmg_res.expected_damage_value,
                "tier": dmg_res.damage_tier,
                "barrel_count": dmg_res.barrel_count,
            }
            print(json_lib.dumps(dmg_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BATTER CONTACT DAMAGE EVALUATION [{dmg_res.damage_tier}]")
            hdr_dm = (
                f"     Damage Rate: {dmg_res.damage_rate_pct:.1f}% "
                f"| EDV: {dmg_res.expected_damage_value:.3f} RV/BBE "
                f"| Barrels: {dmg_res.barrel_count}/{dmg_res.total_bbe}"
            )
            print(hdr_dm)
            print(f"{'=' * 84}\n")
            print(f"  • Damage Tier        : {dmg_res.damage_tier}")
            print(f"  • Expected Run Value : {dmg_res.expected_damage_value:.3f}\n")

    elif args.command == "bullpen-opt":
        import json as json_lib

        from mlb_baseball.model.bullpen_opt import (
            BullpenOptimizerEngine,
            InGameLeverageSituation,
            RelieverCandidate,
        )

        bopt_eng = BullpenOptimizerEngine()
        batters_list = [b.strip() for b in args.batters.split(",")]
        sit = InGameLeverageSituation(
            inning=args.inning,
            score_diff=args.score_diff,
            leverage_index=args.li,
            upcoming_batters_hand=batters_list,
        )
        bopt_sample_arms = [
            RelieverCandidate(
                "r1", "Lefty Specialist", "L", rest_days=2, pitches_last_3d=10, fip=2.80
            ),
            RelieverCandidate("r2", "Righty Setup", "R", rest_days=0, pitches_last_3d=40, fip=3.40),
            RelieverCandidate("r3", "Closer", "R", rest_days=1, pitches_last_3d=15, fip=2.20),
        ]
        bopt_res = bopt_eng.optimize_bullpen(sit, bopt_sample_arms)

        if args.json:
            bopt_out = {
                "top_recommendation": bopt_res.top_recommendation.name,
                "score": bopt_res.top_recommendation.net_score,
                "label": bopt_res.top_recommendation.recommendation_label,
            }
            print(json_lib.dumps(bopt_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(
                f"     LIVE BULLPEN OPTIMIZER [Inn: {bopt_res.inning} "
                f"| LI: {bopt_res.leverage_index:.2f}]"
            )
            hdr_bo = (
                f"     TOP INSERTION: {bopt_res.top_recommendation.name} "
                f"({bopt_res.top_recommendation.recommendation_label}) "
                f"| Net Score: {bopt_res.top_recommendation.net_score:.3f}"
            )
            print(hdr_bo)
            print(f"{'=' * 84}\n")
            for arm_rank in bopt_res.all_rankings:
                print(
                    f"  #{arm_rank.rank} {arm_rank.name:<20} "
                    f"Score: {arm_rank.net_score:>+6.3f} "
                    f"| Matchup: {arm_rank.matchup_advantage:>+5.2f} "
                    f"| Fatigue: {arm_rank.fatigue_penalty:>5.2f} "
                    f"[{arm_rank.recommendation_label}]"
                )
            print()

    elif args.command == "fatigue":
        import json as json_lib

        from mlb_baseball.model.fatigue import (
            PitcherFatigueEngine,
            PitcherWorkloadMetrics,
        )

        fat_eng = PitcherFatigueEngine()
        fat_metrics = PitcherWorkloadMetrics(
            "p1",
            "Target Pitcher",
            pitches_7d=args.pitches_7d,
            pitches_28d=args.pitches_28d,
            velo_delta_mph=args.velo_delta,
            release_drop_in=args.release_drop,
        )
        fat_res = fat_eng.evaluate_fatigue(fat_metrics)

        if args.json:
            fat_out = {
                "acwr": fat_res.acwr_ratio,
                "fatigue_risk_index": fat_res.fatigue_risk_index,
                "tier": fat_res.fatigue_tier,
                "velo_flag": fat_res.is_velocity_flagged,
                "mech_flag": fat_res.is_biomechanics_flagged,
            }
            print(json_lib.dumps(fat_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCHER WORKLOAD FATIGUE RISK [{fat_res.fatigue_tier}]")
            hdr_fa = (
                f"     ACWR: {fat_res.acwr_ratio:.2f} "
                f"| Fatigue Index: {fat_res.fatigue_risk_index:.1f}/100 "
                f"| Velo Flag: {'YES' if fat_res.is_velocity_flagged else 'NO'}"
            )
            print(hdr_fa)
            print(f"{'=' * 84}\n")
            print(
                f"  • Biomechanics Sag Flag : {'YES' if fat_res.is_biomechanics_flagged else 'NO'}"
            )
            print(f"  • Fatigue Classification : {fat_res.fatigue_tier}\n")

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

    elif args.command == "platoon":
        import json as json_lib

        from mlb_baseball.model.splits import (
            BatterPlatoonEngine,
            BatterPlatoonRawStats,
        )

        plat_eng = BatterPlatoonEngine()
        raw_st = BatterPlatoonRawStats(
            "b1",
            "Target Batter",
            bats_hand=args.bats,
            overall_woba=args.overall,
            pa_vs_lhp=args.pa_lhp,
            woba_vs_lhp=args.woba_lhp,
            pa_vs_rhp=args.pa_rhp,
            woba_vs_rhp=args.woba_rhp,
        )
        plat_res = plat_eng.evaluate_platoon_talent(raw_st)

        if args.json:
            plat_out = {
                "bats": plat_res.bats_hand,
                "shrunk_woba_vs_lhp": plat_res.shrunk_woba_vs_lhp,
                "shrunk_woba_vs_rhp": plat_res.shrunk_woba_vs_rhp,
                "platoon_delta": plat_res.true_talent_platoon_delta,
                "tier": plat_res.platoon_tier,
                "is_strict_platoon": plat_res.is_strict_platoon_candidate,
            }
            print(json_lib.dumps(plat_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PLATOON SPLIT SHRINKAGE [{plat_res.platoon_tier}]")
            hdr_pl = (
                f"     Bats: {plat_res.bats_hand} "
                f"| vs LHP: {plat_res.shrunk_woba_vs_lhp:.3f} "
                f"| vs RHP: {plat_res.shrunk_woba_vs_rhp:.3f}"
            )
            print(hdr_pl)
            print(f"{'=' * 84}\n")
            print(f"  • True Talent Delta    : {plat_res.true_talent_platoon_delta:.3f} wOBA")
            pl_st = "YES" if plat_res.is_strict_platoon_candidate else "NO"
            print(f"  • Strict Platoon Bench : {pl_st}\n")

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

    elif args.command == "spin":
        import json as json_lib

        from mlb_baseball.model.spin import (
            PitchSpinObservation,
            SpinDecompositionEngine,
        )

        spin_eng = SpinDecompositionEngine()
        obs = PitchSpinObservation(
            "p1",
            args.pitch_type,
            total_spin_rpm=args.spin,
            spin_efficiency_pct=args.efficiency,
        )
        spin_res = spin_eng.decompose_spin(obs)

        if args.json:
            spin_out = {
                "pitch_type": spin_res.pitch_type,
                "total_spin": spin_res.total_spin_rpm,
                "active_spin": spin_res.active_spin_rpm,
                "gyro_spin": spin_res.gyro_spin_rpm,
                "efficiency": spin_res.spin_efficiency_pct,
                "archetype": spin_res.spin_archetype,
            }
            print(json_lib.dumps(spin_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCHED BALL SPIN DECOMPOSITION [{spin_res.spin_archetype}]")
            hdr_sp = (
                f"     Total: {spin_res.total_spin_rpm:.0f}rpm "
                f"| Active: {spin_res.active_spin_rpm:.0f}rpm "
                f"| Gyro: {spin_res.gyro_spin_rpm:.0f}rpm ({spin_res.spin_efficiency_pct:.1f}%)"
            )
            print(hdr_sp)
            print(f"{'=' * 84}\n")
            print(f"  • Active Transverse Spin : {spin_res.active_spin_rpm:.0f} rpm")
            print(f"  • Non-Magnus Gyro Spin   : {spin_res.gyro_spin_rpm:.0f} rpm\n")

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

    elif args.command == "decision":
        import json as json_lib

        from mlb_baseball.model.decision import (
            BatterSwingDecisionEngine,
            BatterZoneRates,
        )

        dec_eng = BatterSwingDecisionEngine()
        rates = BatterZoneRates(
            "b1",
            "Target Batter",
            heart_swing_pct=args.heart_swing,
            shadow_swing_pct=args.shadow_swing,
            chase_swing_pct=args.chase_swing,
            waste_swing_pct=args.waste_swing,
        )
        dec_res = dec_eng.evaluate_batter_discipline(rates)

        if args.json:
            dec_out = {
                "archetype": dec_res.archetype.value,
                "discipline_grade": dec_res.discipline_grade,
                "sdv_per_100": dec_res.swing_decision_val_per_100,
                "season_run_value": dec_res.season_run_value_added,
            }
            print(json_lib.dumps(dec_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     BATTER SWING DECISIONS [{dec_res.discipline_grade}]")
            hdr_dec = (
                f"     SDV: {dec_res.swing_decision_val_per_100:+.2f} runs/100 pitches "
                f"| Season Added: {dec_res.season_run_value_added:+.1f} runs"
            )
            print(hdr_dec)
            print(f"{'=' * 84}\n")
            print(f"  • Heart Zone Swing     : {args.heart_swing * 100:.1f}%")
            print(f"  • Chase Zone Swing     : {args.chase_swing * 100:.1f}%")
            print(f"  • Net Run Impact       : {dec_res.season_run_value_added:+.1f} runs/season\n")

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

    elif args.command == "extension":
        import json as json_lib

        from mlb_baseball.model.extension import (
            PitcherExtensionEngine,
            PitcherExtensionProfile,
        )

        ext_eng = PitcherExtensionEngine()
        ext_prof = PitcherExtensionProfile(
            "p1", "Target Pitcher", release_extension_ft=args.ext, radar_velocity_mph=args.velo
        )
        ext_res = ext_eng.evaluate_effective_velocity(ext_prof)

        if args.json:
            ext_out = {
                "extension_ft": ext_res.release_extension_ft,
                "radar_velo": ext_res.radar_velocity_mph,
                "perceived_velo": ext_res.perceived_velocity_mph,
                "velo_delta": ext_res.velocity_delta_mph,
                "time_to_plate_ms": ext_res.time_to_plate_ms,
                "tier": ext_res.extension_tier,
            }
            print(json_lib.dumps(ext_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCHER EXTENSION & EFFECTIVE VELOCITY [{ext_res.extension_tier}]")
            hdr_ext = (
                f"     Radar: {ext_res.radar_velocity_mph:.1f}mph "
                f"-> Perceived: {ext_res.perceived_velocity_mph:.1f}mph "
                f"({ext_res.velocity_delta_mph:+.2f}mph)"
            )
            print(hdr_ext)
            print(f"{'=' * 84}\n")
            print(f"  • Physical Extension   : {ext_res.release_extension_ft:.1f} ft")
            print(f"  • Time-to-Plate        : {ext_res.time_to_plate_ms:.1f} ms")
            print(f"  • Perceived Velocity   : {ext_res.perceived_velocity_mph:.1f} mph\n")

    elif args.command == "leverage":
        import json as json_lib

        from mlb_baseball.model.leverage import (
            BullpenLeverageEngine,
            RelieverLeverageProfile,
        )

        lev_eng = BullpenLeverageEngine()
        lev_prof = RelieverLeverageProfile(
            "r1", "Target Reliever", k_pct=args.k_pct, bb_pct=args.bb_pct, hr_per_9=args.hr9
        )
        lev_res = lev_eng.evaluate_closer_reliability(lev_prof)

        if args.json:
            lev_out = {
                "tier": lev_res.closer_tier,
                "volatility_index": lev_res.volatility_index,
                "save_conversion_pct": lev_res.expected_save_conversion_pct,
                "is_lockdown": lev_res.is_lockdown_closer,
            }
            print(json_lib.dumps(lev_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CLOSER VOLATILITY & LEVERAGE [{lev_res.closer_tier}]")
            hdr_lev = (
                f"     Volatility: {lev_res.volatility_index:.1f}/100 "
                f"| Save Conversion: {lev_res.expected_save_conversion_pct:.1f}%"
            )
            print(hdr_lev)
            print(f"{'=' * 84}\n")
            print(f"  • Strikeout Rate       : {args.k_pct * 100:.1f}%")
            print(f"  • Walk Rate            : {args.bb_pct * 100:.1f}%")
            print(f"  • Blown Save Volatility: {lev_res.volatility_index:.1f}/100\n")

    elif args.command == "ssw":
        import json as json_lib

        from mlb_baseball.model.ssw import (
            PitchSpinKinematics,
            SeamShiftedWakeEngine,
        )

        ssw_eng = SeamShiftedWakeEngine()
        kin = PitchSpinKinematics(
            "p1",
            args.pitch_type,
            velocity_mph=args.velo,
            spin_rate_rpm=args.spin,
            observed_ivb_in=args.obs_ivb,
            observed_hb_in=args.obs_hb,
            spin_axis_deg=args.axis,
        )
        ssw_res = ssw_eng.evaluate_pitch_ssw(kin)

        if args.json:
            ssw_out = {
                "pitch_type": ssw_res.pitch_type,
                "magnus_ivb": ssw_res.magnus_ivb_in,
                "magnus_hb": ssw_res.magnus_hb_in,
                "ssw_magnitude": ssw_res.ssw_total_magnitude_in,
                "whiff_boost": ssw_res.whiff_boost_pct,
                "has_ssw": ssw_res.has_pronounced_ssw,
            }
            print(json_lib.dumps(ssw_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            ssw_tag = "PRONOUNCED SSW" if ssw_res.has_pronounced_ssw else "MAGNUS DOMINATED"
            print(f"     SEAM-SHIFTED WAKE AERODYNAMICS [{ssw_tag}]")
            hdr_ssw = (
                f"     Pitch: {args.pitch_type} @ {args.velo:.1f}mph "
                f"| SSW: {ssw_res.ssw_total_magnitude_in:.2f}in"
            )
            print(hdr_ssw)
            print(f"{'=' * 84}\n")
            print(f"  • Magnus: IVB {ssw_res.magnus_ivb_in:+.1f} | HB {ssw_res.magnus_hb_in:+.1f}")
            print(f"  • Observed Trajectory  : IVB {args.obs_ivb:+.1f}in | HB {args.obs_hb:+.1f}in")
            print(f"  • SSW Whiff Boost      : +{ssw_res.whiff_boost_pct:.1f}%")
            print(f"  • Hard-Hit Suppression : -{ssw_res.hard_hit_suppression_pct:.1f}%\n")

    elif args.command == "block":
        import json as json_lib

        from mlb_baseball.model.blocking import (
            CatcherBlockingEngine,
            CatcherBlockProfile,
            PitcherSpikeProfile,
        )

        blk_eng = CatcherBlockingEngine()
        cat_prof = CatcherBlockProfile(
            "c1", "Target Catcher", blocking_runs_above_avg=args.catcher_runs
        )
        pit_prof = PitcherSpikeProfile("p1", "Target Pitcher", dirt_pitches_per_game=args.spikes)
        blk_res = blk_eng.evaluate_blocking_matchup(cat_prof, pit_prof)

        if args.json:
            blk_out = {
                "blocking_tier": blk_res.blocking_tier,
                "expected_blocks": blk_res.expected_blocks_per_game,
                "passed_balls": blk_res.expected_passed_balls_per_game,
                "wild_pitches": blk_res.expected_wild_pitches_per_game,
                "run_cost_delta": blk_res.run_cost_delta_per_game,
            }
            print(json_lib.dumps(blk_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     CATCHER BLOCKING & RUN PREVENTION [{blk_res.blocking_tier}]")
            print(f"     Dirt Pitches: {args.spikes:.1f} | Catcher Runs: {args.catcher_runs:+.1f}")
            print(f"{'=' * 84}\n")
            print(f"  • Expected Blocks/Game : {blk_res.expected_blocks_per_game:.1f}")
            print(f"  • Passed Balls/Game    : {blk_res.expected_passed_balls_per_game:.3f}")
            print(f"  • Wild Pitches/Game    : {blk_res.expected_wild_pitches_per_game:.3f}")
            print(f"  • Run Cost Delta       : {blk_res.run_cost_delta_per_game:+.3f} runs/game\n")

    elif args.command == "travel":
        import json as json_lib

        from mlb_baseball.model.travel import (
            TeamTravelScheduleState,
            TravelFatigueEngine,
        )

        trv_eng = TravelFatigueEngine()
        trv_state = TeamTravelScheduleState(
            "t1",
            "TEAM",
            time_zones_crossed=args.tz,
            hours_of_rest_between_games=args.rest_hours,
            is_doubleheader_game_2=args.is_dh2,
            consecutive_game_days=args.consecutive_days,
        )
        trv_res = trv_eng.assess_travel_fatigue(trv_state)

        if args.json:
            trv_out = {
                "fatigue_tier": trv_res.fatigue_tier,
                "fatigue_index": trv_res.fatigue_index,
                "woba_drag_pct": trv_res.woba_drag_pct,
                "pitcher_fip_penalty": trv_res.pitcher_fip_penalty,
            }
            print(json_lib.dumps(trv_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TRAVEL & DOUBLEHEADER FATIGUE [{trv_res.fatigue_tier}]")
            fat_str = (
                f"     Fatigue: {trv_res.fatigue_index:.1f}/100 "
                f"| TZ: {args.tz} | Rest: {args.rest_hours:.1f}h"
            )
            print(fat_str)
            print(f"{'=' * 84}\n")
            print(f"  • Offensive wOBA Drag  : {trv_res.woba_drag_pct:+.1f}%")
            print(f"  • Pitching FIP Penalty : {trv_res.pitcher_fip_penalty:+.2f}\n")

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

    elif args.command == "steal":
        import json as json_lib

        from mlb_baseball.model.baserunning import (
            BaseStealingPhysicsEngine,
            CatcherArmProfile,
            PitcherDeliveryProfile,
            RunnerStealProfile,
        )

        st_eng = BaseStealingPhysicsEngine()
        r_prof = RunnerStealProfile("r1", "Target Runner", sprint_speed_ft_s=args.sprint)
        p_prof = PitcherDeliveryProfile(
            "p1",
            "Target Pitcher",
            delivery_time_s=args.delivery,
            disengagements_used=args.disengagements,
        )
        c_prof = CatcherArmProfile("c1", "Target Catcher", pop_time_s=args.pop_time)

        st_res = st_eng.evaluate_steal_attempt(r_prof, p_prof, c_prof, outs=args.outs)

        if args.json:
            st_out = {
                "success_probability": st_res.success_probability,
                "timing_margin_s": st_res.timing_margin_s,
                "breakeven_rate": st_res.breakeven_success_rate,
                "run_value_delta": st_res.expected_run_value_delta,
                "is_green_light": st_res.is_green_light,
            }
            print(json_lib.dumps(st_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            gl_tag = "GREEN LIGHT" if st_res.is_green_light else "RED LIGHT"
            hdr_st = (
                f"     P(SB): {st_res.success_probability * 100:.1f}% "
                f"| Margin: {st_res.timing_margin_s:+.2f}s"
            )
            print(f"     BASE STEAL DECISION [{gl_tag}]")
            print(hdr_st)
            print(f"{'=' * 84}\n")
            print(f"  • Runner Time to Bag   : {st_res.runner_time_to_bag_s:.2f}s")
            print(f"  • Defense Time to Bag  : {st_res.defense_time_to_bag_s:.2f}s")
            print(f"  • Breakeven Win Rate   : {st_res.breakeven_success_rate * 100:.1f}%")
            print(f"  • Expected Run Delta   : {st_res.expected_run_value_delta:+.3f} runs\n")

    elif args.command == "entropy":
        import json as json_lib

        from mlb_baseball.model.entropy import (
            PitchArsenalDistribution,
            PitchSequencingEntropyEngine,
        )

        ent_eng = PitchSequencingEntropyEngine()
        ars = PitchArsenalDistribution(
            "p1",
            "Target Pitcher",
            {"FF": args.fastball, "SL": args.slider, "CH": args.changeup},
        )
        ent_res = ent_eng.evaluate_arsenal_entropy(ars)

        if args.json:
            ent_out = {
                "shannon_entropy_bits": ent_res.shannon_entropy_bits,
                "normalized_entropy": ent_res.normalized_entropy,
                "predictability_score": ent_res.predictability_score,
                "repetition_penalty": ent_res.repetition_contact_penalty_pct,
            }
            print(json_lib.dumps(ent_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            ent_hdr = (
                f"     H: {ent_res.shannon_entropy_bits:.2f} "
                f"| Norm: {ent_res.normalized_entropy:.2f}"
            )
            print(f"     PITCH ENTROPY (Pred: {ent_res.predictability_score:.1f}/100)")
            print(ent_hdr)
            print(f"{'=' * 84}\n")
            print(f"  • Contact Boost: +{ent_res.repetition_contact_penalty_pct:.1f}% on repeat\n")

    elif args.command == "aging":
        import json as json_lib

        from mlb_baseball.model.aging import (
            PlayerTalentBaseline,
            SkillAgingProjectionEngine,
        )

        ag_eng = SkillAgingProjectionEngine()
        p_card = PlayerTalentBaseline(
            "p1",
            "Target Player",
            current_age=args.age,
            is_pitcher=args.is_pitcher,
            fastball_velo_mph=args.velo,
            woba_or_fip=args.woba,
        )
        ag_proj = ag_eng.project_multi_year_trajectory(p_card, horizon_years=3)

        if args.json:
            ag_out = [
                {
                    "year": p.year_offset,
                    "age": p.projected_age,
                    "primary_metric": p.projected_woba_or_fip,
                    "velo": p.projected_fastball_velo_mph,
                    "sprint": p.projected_sprint_speed_ft_s,
                }
                for p in ag_proj
            ]
            print(json_lib.dumps(ag_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            role_lbl = "Pitcher" if args.is_pitcher else "Hitter"
            print(f"     SKILL COMPONENT AGING TRAJECTORY ({role_lbl} Age {args.age:.0f})")
            print(f"{'=' * 84}\n")
            for ag_p in ag_proj:
                row_str = (
                    f"  • +{ag_p.year_offset} Yr: {ag_p.projected_woba_or_fip:.3f} "
                    f"| Velo: {ag_p.projected_fastball_velo_mph:.1f}"
                )
                print(row_str)
            print()

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

    elif args.command == "count":
        import json as json_lib

        from mlb_baseball.model.count import PitchCountMarkovEngine

        c_eng = PitchCountMarkovEngine()
        c_res = c_eng.simulate_plate_appearance(
            starting_balls=args.balls,
            starting_strikes=args.strikes,
            whiff_base_rate=args.whiff_rate,
        )

        if args.json:
            cnt_out = {
                "terminal_outcome": c_res.terminal_outcome.value,
                "total_pitches": c_res.total_pitches,
                "count_history": c_res.count_history,
                "pitch_outcomes": c_res.pitch_outcomes,
            }
            print(json_lib.dumps(cnt_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     PITCH COUNT MARKOV AT-BAT SIMULATION ({args.balls}-{args.strikes} Start)")
            out_str = (
                f"     [{c_res.terminal_outcome.value.upper()}] | Pitches: {c_res.total_pitches}"
            )
            print(out_str)
            print(f"{'=' * 84}\n")
            print(f"  • Count Sequence       : {' -> '.join(c_res.count_history)}")
            print(f"  • Pitch Outcomes       : {', '.join(c_res.pitch_outcomes)}\n")

    elif args.command == "shift":
        import json as json_lib

        from mlb_baseball.model.shift import (
            AlignmentType,
            BatterBattedBallTendencies,
            DefensiveAlignmentEngine,
            DefensiveAlignmentProfile,
        )

        sh_eng = DefensiveAlignmentEngine()
        align_enum = AlignmentType(args.alignment)
        def_prof = DefensiveAlignmentProfile("team1", align_enum, infield_oaa_season=args.team_oaa)
        bat_tend = BatterBattedBallTendencies(
            "b1", "Target Batter", pull_pct_ground_balls=args.pull_pct
        )
        sh_res = sh_eng.evaluate_defensive_matchup(def_prof, bat_tend)

        if args.json:
            shop_out = {
                "alignment": sh_res.alignment.value,
                "expected_babip": sh_res.expected_babip,
                "babip_delta": sh_res.babip_delta_vs_league,
                "ground_ball_out_rate": sh_res.ground_ball_out_rate,
                "run_prevention": sh_res.expected_run_prevention_per_game,
            }
            print(json_lib.dumps(shop_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(
                f"     DEFENSIVE ALIGNMENT & SPRAY SUPPRESSION ({sh_res.alignment.value.upper()})"
            )
            print(
                f"     Batter Pull%: {args.pull_pct * 100:.0f}% | Infield OAA: {args.team_oaa:+.1f}"
            )
            print(f"{'=' * 84}\n")
            babip_str = (
                f"  • BABIP: {sh_res.expected_babip:.3f} ({sh_res.babip_delta_vs_league:+.2f})"
            )
            print(babip_str)
            print(f"  • Ground Ball Out Rate : {sh_res.ground_ball_out_rate * 100:.1f}%")
            print(
                f"  • Run Prevention       : {sh_res.expected_run_prevention_per_game:+.2f} runs\n"
            )

    elif args.command == "sub":
        import json as json_lib

        from mlb_baseball.model.sub import (
            BatterCard,
            TacticalSubstitutionEngine,
        )

        sub_eng = TacticalSubstitutionEngine()
        weak_starter = BatterCard("b1", "Starter", bats="L", woba_vs_rhp=0.315, woba_vs_lhp=0.230)
        power_bench = BatterCard(
            "b2", "Power Bench", bats="R", woba_vs_rhp=0.320, woba_vs_lhp=0.375
        )

        sub_rec = sub_eng.evaluate_pinch_hit(
            current_batter=weak_starter,
            opposing_pitcher_hand=args.pitcher_hand,
            bench_players=[power_bench],
            inning=args.inning,
            leverage_index=args.leverage,
        )

        if args.json:
            sub_out = {
                "should_substitute": sub_rec.should_substitute,
                "substitute_name": sub_rec.recommended_substitute_name,
                "expected_gain": sub_rec.expected_woba_gain,
                "rationale": sub_rec.rationale,
            }
            print(json_lib.dumps(sub_out, indent=2))
        else:
            print(f"\n{'=' * 84}")
            print(f"     TACTICAL PINCH-HIT SIMULATOR (INNING {args.inning})")
            sub_tag = "YES (RECOMMENDED)" if sub_rec.should_substitute else "NO"
            print(f"     Should Pinch Hit: [{sub_tag}] | Leverage: {args.leverage:.1f}")
            print(f"{'=' * 84}\n")
            if sub_rec.should_substitute:
                print(f"  • Recommended Sub      : {sub_rec.recommended_substitute_name}")
                print(f"  • Expected wOBA Gain   : +{sub_rec.expected_woba_gain:.3f}")
            print(f"  • Rationale            : {sub_rec.rationale}\n")

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
    elif args.command == "wpa":
        import json as json_lib

        from mlb_baseball.model.wpa import InGameSituation, WinExpectancyEngine

        engine = WinExpectancyEngine()
        situation = InGameSituation(
            inning=args.inning,
            is_bottom_half=args.bottom,
            outs=args.outs,
            on1=args.on1,
            on2=args.on2,
            on3=args.on3,
            home_score=args.home_score,
            away_score=args.away_score,
        )
        we_home = engine.calculate_win_expectancy(situation)
        we_away = 1.0 - we_home

        # Compute leverage index against an out transition
        hypo_out = InGameSituation(
            inning=args.inning,
            is_bottom_half=args.bottom,
            outs=min(2, args.outs + 1),
            on1=args.on1,
            on2=args.on2,
            on3=args.on3,
            home_score=args.home_score,
            away_score=args.away_score,
        )
        wpa_res = engine.evaluate_play_transition(situation, hypo_out)

        runners_desc = (
            ("1st " if args.on1 else "")
            + ("2nd " if args.on2 else "")
            + ("3rd" if args.on3 else "")
        ).strip() or "Empty"

        half_str = "Bot" if args.bottom else "Top"

        if args.json:
            out_dict = {
                "inning": args.inning,
                "half": half_str,
                "outs": args.outs,
                "runners": runners_desc,
                "home_score": args.home_score,
                "away_score": args.away_score,
                "home_win_expectancy": round(we_home, 4),
                "away_win_expectancy": round(we_away, 4),
                "leverage_index": wpa_res.leverage_index,
            }
            print(json_lib.dumps(out_dict, indent=2))
        else:
            print("\n=== WIN EXPECTANCY & LEVERAGE INDEX ===")
            print(
                f"Situation: {half_str} {args.inning} | {args.outs} out | Runners: {runners_desc}"
            )
            print(
                f"Score: Away {args.away_score} - Home {args.home_score} "
                f"(Margin: {situation.score_margin:+d})"
            )
            print(f"Home Win Expectancy: {we_home * 100:.1f}%")
            print(f"Away Win Expectancy: {we_away * 100:.1f}%")
            print(f"Leverage Index (LI):  {wpa_res.leverage_index:.2f}x (Normal = 1.0x)\n")
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
