#!/usr/bin/env python3
"""Reproduce Plan 04D's real-data calibration checks from a clean clone.

Read-only against DATABASE_URL (safe against production `mlb` -- no writes).
Prints the same real-vs-simulated comparison numbers cited in
docs/DECISIONS.md's ADR-076 (run expectancy), ADR-077 (half-inning
simulator), and ADR-078 (full-game simulator), so those figures can be
regenerated and audited rather than trusted from prose alone.
"""

import argparse
import os
import random

import psycopg

from mlb_baseball.model import markov


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2019)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required (read-only; safe against production mlb)")
    seasons = [args.season]

    with psycopg.connect(url) as conn:
        re_table = markov.estimate_run_expectancy(conn, seasons)
        distribution = markov.estimate_outcome_distribution(conn, seasons)
        real_half_innings = markov.real_half_inning_runs(conn, seasons)
        real_games = markov.real_game_scores(conn, seasons)

    if not re_table or not distribution or not real_half_innings or not real_games:
        raise SystemExit(f"season {args.season} not bootstrapped -- run `mlb doctor` first")

    # Independent, separately-seeded rng per check -- matches how each
    # figure below was originally computed and cited in its own ADR, not
    # one shared stream (which would draw both checks' samples from
    # different points in the sequence and not reproduce those numbers).
    sim_half_innings = markov.simulate_half_innings(
        distribution, random.Random(args.seed), len(real_half_innings)
    )
    game_rng = random.Random(args.seed)
    sim_games = [markov.simulate_game(distribution, game_rng) for _ in range(len(real_games))]

    print(f"season={args.season} seed={args.seed}")
    print()
    print("ADR-076 run expectancy, bases-empty/0-outs:", re_table[markov.EMPTY_ZERO_OUTS])
    print()
    print("ADR-077 half-inning runs (real vs. simulated):")
    print("  real:", markov.summarize_runs(real_half_innings))
    print("  sim: ", markov.summarize_runs(sim_half_innings))
    print()
    real_total = [g.away_runs + g.home_runs for g in real_games]
    sim_total = [g.away_runs + g.home_runs for g in sim_games]
    real_innings = [g.innings for g in real_games]
    sim_innings = [g.innings for g in sim_games]
    real_home_win_rate = sum(1 for g in real_games if g.home_runs > g.away_runs) / len(real_games)
    sim_home_win_rate = sum(1 for g in sim_games if g.home_runs > g.away_runs) / len(sim_games)
    real_extra_innings_rate = sum(1 for g in real_games if g.innings > 9) / len(real_games)
    sim_extra_innings_rate = sum(1 for g in sim_games if g.innings > 9) / len(sim_games)
    print("ADR-078 full-game totals (real vs. simulated):")
    print("  real total runs:", markov.summarize_runs(real_total))
    print("  sim  total runs:", markov.summarize_runs(sim_total))
    print("  real innings played:", markov.summarize_runs(real_innings))
    print("  sim  innings played:", markov.summarize_runs(sim_innings))
    print(f"  real home win rate: {real_home_win_rate:.4f}")
    print(f"  sim  home win rate: {sim_home_win_rate:.4f}")
    print(f"  real extra-innings rate: {real_extra_innings_rate:.4f}")
    print(f"  sim  extra-innings rate: {sim_extra_innings_rate:.4f}")


if __name__ == "__main__":
    main()
