#!/usr/bin/env python3
"""Reproduce Plan 04D's real-data calibration checks from a clean clone.

Read-only against DATABASE_URL (safe against production `mlb` -- no writes).
Prints the same real-vs-simulated comparison numbers cited in
docs/DECISIONS.md's ADR-076 (run expectancy), ADR-077 (half-inning
simulator), ADR-078 (full-game simulator), ADR-079 (held-out-season
check), and ADR-080 (home/away split), so those figures can be
regenerated and audited rather than trusted from prose alone.

By default `--estimate-seasons` matches `--season`, reproducing those
ADRs' in-sample diagnostic exactly. Pass `--estimate-seasons` with
seasons strictly before `--season` for a genuinely held-out check (e.g.
`--estimate-seasons 2015 2016 2017 2018 --season 2019`) -- see ADR-079.
"""

import argparse
import os
import random
from collections.abc import Sequence

import psycopg

from mlb_baseball.model import markov


def _classify_seasons(eval_season: int, estimate_seasons: Sequence[int]) -> str:
    """Classify how `estimate_seasons` relates to `eval_season`, or raise
    ValueError for a combination that can never be a valid calibration
    check. A naive `eval_season not in estimate_seasons` check (this
    script's first version) mislabels two real cases: a future estimate
    season (e.g. estimating from 2020 to evaluate 2019) reads as
    "held-out" when it's actually data leakage from the future, and an
    estimate list that includes the eval season alongside other seasons
    (e.g. [2018, 2019] evaluating 2019) reads as "in-sample" when it's
    really a mix of in-sample and held-out data, not a clean version of
    either. Any future season is rejected outright; the other two cases
    get their own distinct labels instead of being folded into one."""
    if any(season > eval_season for season in estimate_seasons):
        raise ValueError(
            f"estimate_seasons {list(estimate_seasons)} includes a season after "
            f"eval season {eval_season} -- that would use future data, which can "
            "never be a valid calibration check"
        )
    if list(estimate_seasons) == [eval_season]:
        return "in-sample (estimate season matches eval season exactly)"
    if eval_season in estimate_seasons:
        return (
            "mixed (estimate seasons include the eval season plus others -- "
            "not a clean held-out check)"
        )
    return "held-out (every estimate season strictly precedes eval season)"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--season", type=int, default=2019, help="season real data is drawn from")
    parser.add_argument(
        "--estimate-seasons",
        type=int,
        nargs="+",
        default=None,
        help="seasons to estimate the outcome distribution from (defaults to [--season], "
        "i.e. in-sample)",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    eval_seasons = [args.season]
    estimate_seasons = (
        args.estimate_seasons if args.estimate_seasons is not None else list(eval_seasons)
    )
    try:
        season_mode = _classify_seasons(args.season, estimate_seasons)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required (read-only; safe against production mlb)")

    with psycopg.connect(url) as conn:
        re_table = markov.estimate_run_expectancy(conn, estimate_seasons)
        distribution = markov.estimate_outcome_distribution(conn, estimate_seasons)
        away_distribution = markov.estimate_outcome_distribution(
            conn, estimate_seasons, bat_home="0"
        )
        home_distribution = markov.estimate_outcome_distribution(
            conn, estimate_seasons, bat_home="1"
        )
        real_half_innings = markov.real_half_inning_runs(conn, eval_seasons)
        real_games = markov.real_game_scores(conn, eval_seasons)

    if not re_table or not distribution:
        raise SystemExit(f"estimate seasons {estimate_seasons} not bootstrapped")
    if not away_distribution or not home_distribution:
        raise SystemExit(f"estimate seasons {estimate_seasons} has no home/away-split data")
    if not real_half_innings or not real_games:
        raise SystemExit(f"eval season {args.season} not bootstrapped")

    # Independent, separately-seeded rng per check -- matches how each
    # figure below was originally computed and cited in its own ADR, not
    # one shared stream (which would draw both checks' samples from
    # different points in the sequence and not reproduce those numbers).
    sim_half_innings = markov.simulate_half_innings(
        distribution, random.Random(args.seed), len(real_half_innings)
    )
    # max_innings=60, well above simulate_game's own 30-inning default:
    # running thousands of independent games is an order-statistics
    # problem, not a single-game one -- the *maximum* inning count across
    # ~2,400+ trials routinely exceeds any one real game's longest-on-
    # record figure (confirmed directly: a held-out 2015-2018 estimate,
    # seed=1, hit exactly 31 innings in one simulated game, one past the
    # library default, with no other sign of a degenerate distribution).
    # 60 leaves comfortable headroom without masking a genuinely
    # degenerate distribution, which would still raise well before that.
    # (simulate_home_win_rate, the Monte Carlo path in sim_predict, runs
    # far more trials still and defaults max_innings to 100 for the same
    # order-statistics reason -- see its docstring.)
    game_rng = random.Random(args.seed)
    sim_games = [
        markov.simulate_game(distribution, game_rng, max_innings=60) for _ in range(len(real_games))
    ]
    split_game_rng = random.Random(args.seed)
    sim_split_games = [
        markov.simulate_game(
            away_distribution, split_game_rng, max_innings=60, home_distribution=home_distribution
        )
        for _ in range(len(real_games))
    ]

    print(f"eval_season={args.season} estimate_seasons={estimate_seasons} seed={args.seed}")
    print(season_mode)
    print()
    print("ADR-076 run expectancy, bases-empty/0-outs:", re_table[markov.EMPTY_ZERO_OUTS])
    print()
    print("ADR-077 half-inning runs (real vs. simulated):")
    print("  real:", markov.summarize_runs(real_half_innings))
    print("  sim: ", markov.summarize_runs(sim_half_innings))
    print()
    real_total = [g.away_runs + g.home_runs for g in real_games]
    sim_total = [g.away_runs + g.home_runs for g in sim_games]
    # summarize_runs is generic descriptive-stats logic (count/mean/median/
    # p90/max over a list of ints) despite its run-total-shaped name --
    # reused here for innings played, a different domain but the same
    # statistical shape.
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
    print()
    split_home_win_rate = sum(1 for g in sim_split_games if g.home_runs > g.away_runs) / len(
        sim_split_games
    )
    split_away_mean = sum(g.away_runs for g in sim_split_games) / len(sim_split_games)
    split_home_mean = sum(g.home_runs for g in sim_split_games) / len(sim_split_games)
    print("ADR-080 home/away split (combined-distribution sim vs. split-distribution sim):")
    print(f"  real home win rate:                {real_home_win_rate:.4f}")
    print(f"  combined-distribution home win rate: {sim_home_win_rate:.4f}")
    print(f"  split-distribution    home win rate: {split_home_win_rate:.4f}")
    print(
        f"  split-distribution away/home run means: {split_away_mean:.3f} / {split_home_mean:.3f}"
    )


if __name__ == "__main__":
    main()
