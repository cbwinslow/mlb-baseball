#!/usr/bin/env python3
"""Holdout evaluation: does ``markov-v1`` beat Elo and the prediction markets?

Read-only against ``DATABASE_URL`` -- safe to point at production ``mlb``.
Opens one ``REPEATABLE READ`` read-only transaction so every query -- the
completed-game slate, the Retrosheet recomputation, the stored baselines
-- sees a single consistent snapshot even if a ``mlb predict`` / conform
run lands mid-evaluation.

For one holdout season it recomputes ``markov-v1`` home-win probabilities
for every *completed* game via :func:`sim_predict.simulate_matchup` -- the
exact per-game computation ``mlb predict`` runs -- with that game's own
date as the point-in-time cutoff. It then pulls the stored pre-game
``elo-v1`` / ``log5-v2`` / ``gbm-v1`` / ``kalshi-v1`` / ``polymarket-v1``
snapshots for those games and, for each baseline separately, scores both
models on that pair's exact shared sample: log loss, Brier, accuracy, and
a paired bootstrap 95% CI for the per-game log-loss difference.

**Starters.** By default the recomputation treats every starter as
unknown (team batting vs opposing team), because no pre-game
probable-pitcher record exists for historical seasons -- feeding the
*realized* starter would be hindsight the live forecast never had.
``--use-realized-starters`` runs the starter-informed version too; read
that as an optimistic upper bound, not the deployed system's number.

``markov-v1`` stays ``status=candidate`` until a comparison like this is
recorded (ADR-272; ``plans/04-modeling-simulation-and-experiments.md``).
It earns promotion only by beating ``elo-v1`` on log loss by at least the
project's practical margin with a CI that excludes zero; it earns a place
in a betting product only if it also beats ``kalshi-v1`` / ``polymarket-v1``
on their overlapping games.

Example::

    DATABASE_URL=postgresql:///mlb uv run python scripts/eval_markov_holdout.py \
        --season 2024 --sim-games 2000
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import random
import time
from collections.abc import Sequence

import psycopg

from mlb_baseball.model import markov, sim_predict
from mlb_baseball.model.evaluation import (
    MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT,
    Prediction,
    _common_sample,
    _scores,
    _selected_predictions,
)

DEFAULT_COMPARE = ["elo-v1", "log5-v2", "gbm-v1", "kalshi-v1", "polymarket-v1"]
BOOTSTRAP_SAMPLES = 2000
_EPSILON = 1e-15


def _completed_games(conn: psycopg.Connection, season: int, limit: int) -> list[tuple[object, ...]]:
    """Completed games for the holdout season, oldest first."""
    sql = (
        "SELECT "
        + sim_predict.GAME_FIELDS
        + ", gf.home_win"
        + sim_predict.GAME_FROM
        + "WHERE gf.season = %s AND gf.home_win IS NOT NULL "
        "AND gf.mlb_game_pk IS NOT NULL AND gf.game_date IS NOT NULL "
        "ORDER BY gf.game_date, gf.mlb_game_pk"
    )
    params: tuple[object, ...] = (season,)
    if limit:
        sql += " LIMIT %s"
        params = (season, limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _markov_predictions(
    conn: psycopg.Connection,
    games: Sequence[tuple[object, ...]],
    sim_games: int,
    *,
    use_starters: bool,
) -> tuple[list[Prediction], int]:
    """Recompute markov-v1 for each completed game. Returns the
    predictions plus a count of games skipped -- either for want of a
    cutoff league prior (too-early a season) or because the estimated
    distribution could not be simulated (a degenerate matchup). A
    multi-hour run must not die on the last game because one matchup
    hit a MarkovError."""
    league_cache: sim_predict.LeagueCache = {}
    rows: list[Prediction] = []
    skipped = 0
    started = time.monotonic()
    for done, game in enumerate(games, start=1):
        pk, gik, seas, gdate, home_t, away_t, home_sp, away_sp, home_win = game
        try:
            prob = sim_predict.simulate_matchup(
                conn,
                mlb_game_pk=str(pk),
                season=int(seas),
                game_date=gdate if isinstance(gdate, str) else str(gdate),
                home_team=str(home_t),
                away_team=str(away_t),
                home_starter=str(home_sp) if use_starters and home_sp is not None else None,
                away_starter=str(away_sp) if use_starters and away_sp is not None else None,
                league_cache=league_cache,
                n_games=sim_games,
            )
        except markov.MarkovError as error:
            print(f"  ... game {pk} skipped -- simulation failed: {error}", flush=True)
            skipped += 1
            continue
        if prob is None:
            skipped += 1
            continue
        rows.append(
            Prediction(
                game_instance_key=str(gik),
                model_version="markov-v1",
                probability=prob,
                actual=bool(home_win),
            )
        )
        if done % 200 == 0:
            rate = done / (time.monotonic() - started)
            print(f"  ... {done}/{len(games)} games ({rate:.1f}/s)", flush=True)
    return rows, skipped


def _per_game_losses(rows: Sequence[Prediction]) -> list[float]:
    """Clipped log loss for each game, aligned to ``rows`` order."""
    out = []
    for row in rows:
        p = min(max(row.probability, _EPSILON), 1 - _EPSILON)
        y = 1.0 if row.actual else 0.0
        out.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    return out


def _paired_diff_ci(
    markov_rows: Sequence[Prediction], baseline_rows: Sequence[Prediction], seed_key: str
) -> tuple[float, float, float]:
    """Paired bootstrap of mean(baseline loss - markov loss) over the
    shared games (same order in both sequences). Returns
    ``(point_estimate, ci_low, ci_high)``; positive means markov is
    better. ci excluding 0 is the "not just noise" signal.

    ``seed_key`` (the baseline's own name) is hashed into the RNG seed so
    the CI for a given baseline is stable regardless of ``--compare`` order.
    """
    m_losses = _per_game_losses(markov_rows)
    b_losses = _per_game_losses(baseline_rows)
    diffs = [b - m for b, m in zip(b_losses, m_losses, strict=True)]
    if not diffs:
        return 0.0, 0.0, 0.0
    n = len(diffs)
    point = sum(diffs) / n
    seed = int.from_bytes(hashlib.sha256(seed_key.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(BOOTSTRAP_SAMPLES))
    low = means[int(0.025 * (BOOTSTRAP_SAMPLES - 1))]
    high = means[int(0.975 * (BOOTSTRAP_SAMPLES - 1))]
    return point, low, high


def _verdict(point: float, low: float, high: float) -> str:
    if low > 0 and point >= MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT:
        return "markov-v1 better"
    if high < 0 and -point >= MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT:
        return "baseline better"
    return "within noise"


def _format(scores: dict[str, float | int | None]) -> str:
    if scores["games"] == 0 or scores["log_loss"] is None:
        return f"games={scores['games']:>5}   (no overlap)"
    return (
        f"games={scores['games']:>5}   "
        f"log_loss={scores['log_loss']:.4f}   "
        f"brier={scores['brier']:.4f}   "
        f"accuracy={scores['accuracy']:.4f}"
    )


def _report(
    label: str, markov_rows: list[Prediction], stored_by_version: dict[str, list[Prediction]]
) -> None:
    print()
    print(f"=== {label} ===")
    print(f"markov-v1 covered {len(markov_rows)} games")
    print()
    head = (
        f"  {'baseline':<14} {'shared':>7} {'markov ll':>10} {'base ll':>10} "
        f"{'Δ (95% CI)':>22}   verdict"
    )
    print(head)
    print("  " + "-" * (len(head) - 2))
    pairs = {
        version: _common_sample(markov_rows + stored_by_version[version], ["markov-v1", version])
        for version in stored_by_version
    }
    for version in stored_by_version:
        m_rows, b_rows = pairs[version]["markov-v1"], pairs[version][version]
        m_s, b_s = _scores(m_rows), _scores(b_rows)
        if m_s["games"] == 0 or m_s["log_loss"] is None or b_s["log_loss"] is None:
            print(f"  {version:<14} {m_s['games']:>7}   (no shared games)")
            continue
        point, low, high = _paired_diff_ci(m_rows, b_rows, seed_key=version)
        ci = f"{point:+.4f} [{low:+.4f},{high:+.4f}]"
        print(
            f"  {version:<14} {m_s['games']:>7} "
            f"{float(m_s['log_loss']):>10.4f} {float(b_s['log_loss']):>10.4f} "
            f"{ci:>22}   {_verdict(point, low, high)}"
        )
    print()
    for version, pair in pairs.items():
        print(f"  vs {version}:")
        print(f"    markov-v1  {_format(_scores(pair['markov-v1']))}")
        print(f"    {version:<10} {_format(_scores(pair[version]))}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--season", type=int, default=2024, help="holdout season to evaluate on")
    parser.add_argument(
        "--sim-games",
        type=int,
        default=2000,
        help="Monte Carlo count per game (production uses 5000; fewer is faster and noisier)",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        default=DEFAULT_COMPARE,
        help="stored model_versions to compare markov-v1 against",
    )
    parser.add_argument(
        "--cutoff",
        default="close",
        help="which stored pre-game snapshot to score (open/24h/6h/close)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="cap the number of games (0 = all) -- a small value is a quick smoke test",
    )
    parser.add_argument(
        "--use-realized-starters",
        action="store_true",
        help="also run the starter-informed version (hindsight; an optimistic upper bound)",
    )
    args = parser.parse_args()

    if args.sim_games < 1:
        raise SystemExit("--sim-games must be positive")
    if args.limit < 0:
        raise SystemExit("--limit must be non-negative")

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required (read-only; safe against production mlb)")

    with psycopg.connect(url) as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        games = _completed_games(conn, args.season, args.limit)
        if not games:
            raise SystemExit(f"no completed games in gold.game_feature for season {args.season}")
        print(
            f"season={args.season}  completed games={len(games)}  "
            f"sim_games={args.sim_games}  cutoff={args.cutoff}  "
            f"practical margin={MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT}"
        )

        print("recomputing markov-v1 (starters unknown) ...", flush=True)
        no_starter_rows, skipped = _markov_predictions(
            conn, games, args.sim_games, use_starters=False
        )
        starter_rows: list[Prediction] = []
        if args.use_realized_starters:
            print("recomputing markov-v1 (realized starters; hindsight) ...", flush=True)
            starter_rows, _ = _markov_predictions(conn, games, args.sim_games, use_starters=True)

        stored_by_version = {
            version: _selected_predictions(conn, [version], args.season, args.cutoff)
            for version in args.compare
        }

    if not no_starter_rows:
        raise SystemExit(
            "markov-v1 produced no predictions -- Retrosheet has no cutoff league "
            f"prior for season {args.season} ({skipped} skipped)"
        )
    print(f"\n{skipped} games skipped for want of a cutoff league prior")

    _report("starters unknown (deployed-system analog)", no_starter_rows, stored_by_version)
    if starter_rows:
        _report("realized starters (optimistic upper bound)", starter_rows, stored_by_version)

    print()
    print(
        "Δ is mean(baseline per-game log loss - markov per-game log loss); "
        "positive favours markov-v1. A verdict of 'markov-v1 better' needs the "
        f"95% CI above 0 and the point estimate >= {MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT}."
    )


if __name__ == "__main__":
    main()
