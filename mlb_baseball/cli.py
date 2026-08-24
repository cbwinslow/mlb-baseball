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
        "--model", type=str, default="gbm-v1", help="model version (default: gbm-v1)"
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
        "--model", type=str, default="gbm-v1", help="model version to evaluate (default: gbm-v1)"
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
                        "WHERE p.model_version = 'gbm-v1' AND g.home_score IS NOT NULL "
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
