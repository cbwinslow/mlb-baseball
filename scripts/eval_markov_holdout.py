#!/usr/bin/env python3
"""Holdout evaluation: does ``markov-v1`` beat Elo and the prediction markets?

Read-only against ``DATABASE_URL`` -- safe to point at production ``mlb``,
it never writes (opens a read-only transaction and only SELECTs).

For one holdout season it recomputes ``markov-v1`` home-win probabilities
for every *completed* game, using :func:`sim_predict.simulate_matchup` --
the exact per-game computation ``mlb predict`` writes for upcoming games,
with the same point-in-time cutoff (the game's own date). It then pulls
the stored pre-game ``elo-v1`` / ``log5-v2`` / ``gbm-v1`` / ``kalshi-v1``
/ ``polymarket-v1`` snapshots for those same games, restricts every model
to the exact common sample, and prints log loss / Brier / accuracy.

``markov-v1`` stays ``status=candidate`` until a comparison like this is
recorded (ADR-272; ``plans/04-modeling-simulation-and-experiments.md``
acceptance gate). Beating Elo is necessary; beating the market on the
overlapping games is what a betting product actually needs.

Example::

    DATABASE_URL=postgresql:///mlb uv run python scripts/eval_markov_holdout.py \
        --season 2024 --sim-games 2000
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Sequence

import psycopg

from mlb_baseball.model import sim_predict
from mlb_baseball.model.evaluation import (
    Prediction,
    _common_sample,
    _scores,
    _selected_predictions,
)

DEFAULT_COMPARE = ["elo-v1", "log5-v2", "gbm-v1", "kalshi-v1", "polymarket-v1"]


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
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql, (season,))
        return cur.fetchall()


def _markov_predictions(
    conn: psycopg.Connection, games: Sequence[tuple[object, ...]], sim_games: int
) -> tuple[list[Prediction], int]:
    """Recompute markov-v1 for each completed game. Returns the
    predictions plus a count of games skipped for want of a cutoff
    league prior (too-early a season)."""
    league_cache: sim_predict.LeagueCache = {}
    rows: list[Prediction] = []
    skipped = 0
    started = time.monotonic()
    for done, game in enumerate(games, start=1):
        (pk, gik, seas, gdate, home_t, away_t, home_sp, away_sp, home_win) = game
        prob = sim_predict.simulate_matchup(
            conn,
            mlb_game_pk=str(pk),
            season=int(seas),  # type: ignore[call-overload]
            game_date=gdate,  # type: ignore[arg-type]
            home_team=str(home_t),
            away_team=str(away_t),
            home_starter=str(home_sp) if home_sp is not None else None,
            away_starter=str(away_sp) if away_sp is not None else None,
            league_cache=league_cache,
            n_games=sim_games,
        )
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


def _format(scores: dict[str, float | int | None]) -> str:
    if scores["games"] == 0 or scores["log_loss"] is None:
        return f"games={scores['games']:>5}   (no overlap)"
    return (
        f"games={scores['games']:>5}   "
        f"log_loss={scores['log_loss']:.4f}   "
        f"brier={scores['brier']:.4f}   "
        f"accuracy={scores['accuracy']:.4f}"
    )


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
    args = parser.parse_args()

    if args.sim_games < 1:
        raise SystemExit("--sim-games must be positive")

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required (read-only; safe against production mlb)")

    with psycopg.connect(url) as conn:
        conn.read_only = True
        games = _completed_games(conn, args.season, args.limit)
        if not games:
            raise SystemExit(f"no completed games in gold.game_feature for season {args.season}")
        print(
            f"season={args.season}  completed games={len(games)}  "
            f"sim_games={args.sim_games}  cutoff={args.cutoff}"
        )
        print("recomputing markov-v1 ...", flush=True)
        markov_rows, skipped = _markov_predictions(conn, games, args.sim_games)
        if not markov_rows:
            raise SystemExit(
                "markov-v1 produced no predictions -- Retrosheet likely has no "
                f"cutoff league prior for season {args.season} ({skipped} skipped)"
            )

        stored_by_version = {
            version: _selected_predictions(conn, [version], args.season, args.cutoff)
            for version in args.compare
        }

    print()
    print(
        f"markov-v1 predicted {len(markov_rows)} / {len(games)} games "
        f"({skipped} had no cutoff league prior)"
    )
    print()
    print("Each row is markov-v1 vs one model on their exact shared games:")
    print()
    header = f"  {'baseline':<14} {'shared':>7} {'markov ll':>12} {'baseline ll':>12}   winner"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for version in args.compare:
        pair = _common_sample(markov_rows + stored_by_version[version], ["markov-v1", version])
        m_scores = _scores(pair["markov-v1"])
        b_scores = _scores(pair[version])
        n = m_scores["games"]
        if n == 0 or m_scores["log_loss"] is None or b_scores["log_loss"] is None:
            print(f"  {version:<14} {n:>7}   (no shared games)")
            continue
        m_ll = float(m_scores["log_loss"])
        b_ll = float(b_scores["log_loss"])
        winner = "markov-v1" if m_ll < b_ll else version if b_ll < m_ll else "tie"
        print(f"  {version:<14} {n:>7} {m_ll:>12.4f} {b_ll:>12.4f}   {winner}")
    print()
    print("Full scorecard on each pair's shared sample:")
    print()
    for version in args.compare:
        pair = _common_sample(markov_rows + stored_by_version[version], ["markov-v1", version])
        print(f"  vs {version}:")
        print(f"    markov-v1  {_format(_scores(pair['markov-v1']))}")
        print(f"    {version:<10} {_format(_scores(pair[version]))}")
    print()
    print(
        "markov-v1 earns promotion past `candidate` only if it beats elo-v1 on "
        "log loss; it earns a place in a betting product only if it also beats "
        "kalshi-v1 / polymarket-v1 on their overlapping games."
    )


if __name__ == "__main__":
    main()
