"""Base/out state Markov chain estimation from real play-by-play data (Plan 04D).

Models each half-inning as a Markov chain over the 24 transient base/out
states (8 base configurations x 3 out counts) plus one absorbing TERMINAL
state (3 outs, half-inning over -- base occupancy stops mattering once the
inning ends, so every 3-outs row collapses into this single state
regardless of what bases were occupied on it).

The transition matrix is estimated directly from raw.retrosheet_event: one
row already carries both its own pre-play state (outs_ct, base1/2/3_run_id)
and everything needed to derive its post-play state (event_outs_ct,
bat_dest_id, run1/2/3_dest_id) -- see mlb_baseball/sql/
markov_transition_counts.sql's own docstring for the destination-code
mapping, confirmed directly against real data, and why no sequential
per-game walk is needed (unlike every other retrosheet_event consumer's
rolling-window shape, this is a single aggregate GROUP BY over
independently self-describing rows).

Scope: Retrosheet-covered eras only (1910-2025), same honest gap every
sibling retrosheet_event-only module documents (team_rate.py, starter.py) --
no 2026+ raw.mlb_playbyplay equivalent exists here yet.
"""

from __future__ import annotations

import math
import random
from collections.abc import Hashable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, TypeVar

import numpy as np
import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.sql import read_sql

_TRANSITION_COUNTS_SQL = read_sql("markov_transition_counts.sql")
_MATCHUP_COUNTS_SQL = read_sql("markov_transition_counts_matchup.sql")
_HALF_INNING_RUNS_SQL = read_sql("markov_half_inning_runs.sql")
_GAME_SCORES_SQL = read_sql("markov_game_scores.sql")
_PITCHER_ARSENAL_SQL = read_sql("pitcher_arsenal_select.sql")
_BATTER_ARSENAL_SQL = read_sql("batter_arsenal_select.sql")

# Tango, Lichtman & Dolphin, The Book: ~350 PA before a rate is trusted
# over the league prior. Used as M in the Layer-2 matchup shrink.
MATCHUP_PRIOR_PA = 350

# simulate_home_win_rate: fraction of Monte Carlo trials that may stay tied
# at max_innings before the estimated distribution is declared degenerate.
# ~10% of simulated games reach extras (ADR-079) and the estimated
# distribution's extras run long (no automatic-runner rule); a genuinely
# tie-breakable distribution resolves essentially all of those. 1% failing
# is already well beyond sampling luck.
_UNRESOLVED_TRIAL_LIMIT = 0.01

# Per-trial inning cap for the win-rate Monte Carlo. Was 30 (ADR-078), which
# a valid but low-scoring distribution could hit by sampling luck; 100 is
# comfortably past that while still bounding a truly stuck distribution.
# Recorded in sim_predict's model parameters since it shifts the estimate.
SIM_MAX_INNINGS = 100


@dataclass(frozen=True)
class BaseOutState:
    outs: int
    on1: bool = False
    on2: bool = False
    on3: bool = False


# The shared absorbing state every 3-outs transition collapses into --
# base occupancy is meaningless once the half-inning is over.
TERMINAL = BaseOutState(outs=3)

# The state every half-inning starts from -- a module-level singleton
# rather than constructed in a default argument (ruff B008: a mutable-
# looking call in a default is evaluated once at def time, which is
# actually fine for a frozen dataclass, but the singleton is clearer).
EMPTY_ZERO_OUTS = BaseOutState(0, False, False, False)

TRANSIENT_STATES: tuple[BaseOutState, ...] = tuple(
    BaseOutState(o, b1, b2, b3)
    for o in (0, 1, 2)
    for b1 in (False, True)
    for b2 in (False, True)
    for b3 in (False, True)
)


class MarkovError(ValueError):
    """A base/out transition dataset failed a physical or probability invariant."""


class DegenerateSimulation(MarkovError):
    """A simulated game could not be resolved: the estimated distribution has
    no positive-probability path that breaks a tie. A subclass of
    :class:`MarkovError` (so existing ``except MarkovError`` still catches it),
    but distinct so a caller can tell "this one matchup's distribution is
    degenerate -- skip it" apart from a genuine data-contract violation like
    "no observed outcomes for state" that must not be swallowed."""


@dataclass(frozen=True)
class TransitionCountRow:
    pre_outs: int
    pre_b1: bool
    pre_b2: bool
    pre_b3: bool
    post_outs: int
    post_b1: bool
    post_b2: bool
    post_b3: bool
    runs_scored: int
    n: int


def _pre_state(row: TransitionCountRow) -> BaseOutState:
    return BaseOutState(row.pre_outs, row.pre_b1, row.pre_b2, row.pre_b3)


def _post_state(row: TransitionCountRow) -> BaseOutState:
    if row.post_outs >= 3:
        return TERMINAL
    return BaseOutState(row.post_outs, row.post_b1, row.post_b2, row.post_b3)


def _validate_row_conservation(row: TransitionCountRow) -> None:
    # n <= 0, not just < 0: a row with n=0 contributes nothing to a
    # pre-state's total, and a pre-state whose only rows all have n=0
    # would divide by zero when normalized to probabilities downstream.
    if row.n <= 0:
        raise MarkovError(f"non-positive row count: {row}")
    if row.runs_scored < 0:
        raise MarkovError(f"negative runs_scored: {row}")
    # pre_outs is always 0, 1, or 2 for any real pre-play state (a
    # half-inning has already ended by 3 outs, so no further play can
    # start from there) -- a row outside that range would silently
    # construct a BaseOutState absent from TRANSIENT_STATES and be
    # skipped rather than rejected further downstream.
    if row.pre_outs < 0 or row.pre_outs > 2:
        raise MarkovError(f"invalid pre_outs (must be 0, 1, or 2): {row}")
    if row.post_outs < row.pre_outs:
        raise MarkovError(f"outs decreased: {row}")
    if row.post_outs > 3:
        raise MarkovError(f"post_outs > 3: {row}")
    # At most pre_b1+pre_b2+pre_b3 existing runners plus the batter can
    # possibly score or end up occupying a base on this one play -- a row
    # claiming more movers than that existed is a real encoding bug, not a
    # baseball possibility (a runner can't be created out of thin air).
    pre_occupants = int(row.pre_b1) + int(row.pre_b2) + int(row.pre_b3) + 1
    movers = row.runs_scored + int(row.post_b1) + int(row.post_b2) + int(row.post_b3)
    if movers > pre_occupants:
        raise MarkovError(
            f"more people ended up on base/scoring ({movers}) than existed "
            f"before the play ({pre_occupants}): {row}"
        )


_OutcomeKey = TypeVar("_OutcomeKey", bound=Hashable)


def _validate_probabilities_sum_to_one(
    probabilities: dict[_OutcomeKey, float], tolerance: float = 1e-9
) -> None:
    total = sum(probabilities.values())
    if abs(total - 1.0) > tolerance:
        raise MarkovError(f"outgoing probabilities sum to {total}, not 1.0")


def build_transition_matrix(
    rows: Iterable[TransitionCountRow],
) -> dict[BaseOutState, dict[BaseOutState, float]]:
    """Aggregate raw (pre_state, post_state, n) count rows into a per-state
    probability distribution over post-states. Validates baseball's own
    physical conservation rules against every input row and that each
    pre-state's outgoing probabilities sum to 1 before returning -- raises
    MarkovError (never a silently partial or invalid result) on violation."""
    counts: dict[BaseOutState, dict[BaseOutState, int]] = {}
    for row in rows:
        _validate_row_conservation(row)
        pre = _pre_state(row)
        post = _post_state(row)
        bucket = counts.setdefault(pre, {})
        bucket[post] = bucket.get(post, 0) + row.n

    matrix: dict[BaseOutState, dict[BaseOutState, float]] = {}
    for pre, post_counts in counts.items():
        total = sum(post_counts.values())
        post_probs = {post: n / total for post, n in post_counts.items()}
        _validate_probabilities_sum_to_one(post_probs)
        matrix[pre] = post_probs
    return matrix


def _retrosheet_tables_ready(conn: psycopg.Connection) -> bool:
    # Two-table dependency, two-table gate (matching team_rate.py/
    # offense.py/starter.py's established convention, issue #9 item 2):
    # raw.retrosheet_event and raw.retrosheet_gameinfo are landed by two
    # different connectors -- a fresh clone or partial bootstrap that's
    # only ingested one of them would otherwise hit an UndefinedTable
    # error here instead of the same clean "not ready yet" every sibling
    # retrosheet_event consumer gives.
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
    return bool(event_exists) and bool(gameinfo_exists)


def _fetch_transition_counts(
    conn: psycopg.Connection, seasons: Sequence[int], bat_home: Literal["0", "1"] | None = None
) -> list[TransitionCountRow]:
    if not _retrosheet_tables_ready(conn):
        return []
    with conn.cursor() as cur:
        cur.execute(
            _TRANSITION_COUNTS_SQL, {"seasons": [str(s) for s in seasons], "bat_home": bat_home}
        )
        return [TransitionCountRow(*row) for row in cur.fetchall()]


def _validate_seasons(seasons: Sequence[int]) -> None:
    if not seasons:
        raise ValueError("seasons must not be empty")


def estimate_transition_matrix(
    conn: psycopg.Connection, seasons: Sequence[int]
) -> dict[BaseOutState, dict[BaseOutState, float]]:
    """Estimate the base/out transition matrix from real Retrosheet
    play-by-play for the given regular-season years. Returns an empty
    dict, matching every sibling retrosheet_event consumer's "not ready
    yet" contract, if either source table hasn't been bootstrapped."""
    _validate_seasons(seasons)
    rows = _fetch_transition_counts(conn, seasons)
    return build_transition_matrix(rows)


def _immediate_expected_runs(rows: Iterable[TransitionCountRow]) -> dict[BaseOutState, float]:
    """Expected runs scored on the very next play from each pre-state,
    marginalized over every observed outcome (count-weighted average of
    row.runs_scored across every row sharing that pre-state) -- this is
    exactly sum_post P(pre->post) * E[runs | pre->post] by construction,
    the "immediate reward" term the run-expectancy linear system needs.
    Validates each row the same way build_transition_matrix does -- this
    function is called independently in estimate_run_expectancy and is
    also tested directly, so it must not rely on a caller having already
    validated via build_transition_matrix first."""
    totals: dict[BaseOutState, int] = {}
    weighted_runs: dict[BaseOutState, int] = {}
    for row in rows:
        _validate_row_conservation(row)
        pre = _pre_state(row)
        totals[pre] = totals.get(pre, 0) + row.n
        weighted_runs[pre] = weighted_runs.get(pre, 0) + row.n * row.runs_scored
    return {pre: weighted_runs[pre] / totals[pre] for pre in totals}


def run_expectancy(
    matrix: dict[BaseOutState, dict[BaseOutState, float]],
    immediate_runs: dict[BaseOutState, float],
) -> dict[BaseOutState, float]:
    """Solve the absorbing Markov chain for expected remaining runs scored
    from each transient base/out state through the end of the half-inning
    -- the classic RE24 table. RE(TERMINAL) = 0 by definition (the
    half-inning is over); every transient state's RE is the fixed point of
    RE(s) = sum_post P(s->post) * (runs(s->post) + RE(post)). Solved
    directly via the standard absorbing-Markov-chain identity
    (I - Q) @ RE = r (Q the transient-to-transient sub-matrix, r the
    immediate-reward vector) rather than iteratively -- Q here is
    exactly-known once probabilities are already estimated, no sampling
    noise to average out, so a direct linear solve is both exact and
    simpler than an iterative fixed-point search.

    A state absent from `matrix` (no observed outgoing transitions at all
    -- possible with a small or narrow real sample, e.g. a rare bases-
    loaded configuration in a short season range) defaults to RE=0 rather
    than raising: its row in Q stays all-zero, which the linear system
    already resolves to RE=0 on its own (the same value TERMINAL has) --
    a documented "insufficient data" fallback, not a claim that such a
    state truly has zero expected runs. Callers estimating from a narrow
    sample should check `matrix` for missing pre-states directly if this
    distinction matters for their use."""
    states = TRANSIENT_STATES
    index = {state: i for i, state in enumerate(states)}
    n = len(states)
    q = np.zeros((n, n))
    r = np.zeros(n)
    for pre, post_probs in matrix.items():
        if pre not in index:
            continue  # pre-states are always transient by construction
        i = index[pre]
        r[i] = immediate_runs.get(pre, 0.0)
        for post, probability in post_probs.items():
            if post in index:
                q[i, index[post]] = probability
    try:
        re = np.linalg.solve(np.eye(n) - q, r)
    except np.linalg.LinAlgError as error:
        raise MarkovError(f"singular matrix in run expectancy solve: {error}") from error
    return {state: float(re[i]) for state, i in index.items()}


def estimate_run_expectancy(
    conn: psycopg.Connection, seasons: Sequence[int]
) -> dict[BaseOutState, float]:
    """Estimate the RE24-style run-expectancy table from real Retrosheet
    play-by-play for the given regular-season years. Returns an empty
    dict, matching estimate_transition_matrix's "not ready yet" contract,
    if either source table hasn't been bootstrapped -- not a full table of
    zeros, which run_expectancy's own "unobserved state defaults to 0"
    behavior would otherwise produce from an empty matrix."""
    _validate_seasons(seasons)
    rows = _fetch_transition_counts(conn, seasons)
    if not rows:
        return {}
    matrix = build_transition_matrix(rows)
    immediate_runs = _immediate_expected_runs(rows)
    return run_expectancy(matrix, immediate_runs)


@dataclass(frozen=True)
class Outcome:
    post: BaseOutState
    runs: int


def build_outcome_distribution(
    rows: Iterable[TransitionCountRow],
) -> dict[BaseOutState, dict[Outcome, float]]:
    """Aggregate raw (pre_state, post_state, runs_scored, n) rows into a
    per-state probability distribution over (post_state, runs_scored)
    outcomes -- unlike build_transition_matrix, this keeps runs_scored as
    part of the sampled outcome instead of discarding it. A simulator needs
    this: "which post-state" and "how many runs scored getting there" are
    correlated (the same (pre, post) pair can arise from plays that scored
    different numbers of runs), so they must be sampled jointly from one
    distribution per pre-state, not independently from two separate
    marginal distributions -- doing the latter could combine a state
    transition with a run total that never actually co-occurred in the
    real data. Same validation as build_transition_matrix; raises
    MarkovError on any physical/probability violation."""
    counts: dict[BaseOutState, dict[Outcome, int]] = {}
    for row in rows:
        _validate_row_conservation(row)
        pre = _pre_state(row)
        outcome = Outcome(_post_state(row), row.runs_scored)
        bucket = counts.setdefault(pre, {})
        bucket[outcome] = bucket.get(outcome, 0) + row.n

    distribution: dict[BaseOutState, dict[Outcome, float]] = {}
    for pre, outcome_counts in counts.items():
        total = sum(outcome_counts.values())
        probs = {outcome: n / total for outcome, n in outcome_counts.items()}
        _validate_probabilities_sum_to_one(probs)
        distribution[pre] = probs
    return distribution


def shrink_outcome_distribution(
    raw: dict[BaseOutState, dict[Outcome, float]],
    league: dict[BaseOutState, dict[Outcome, float]],
    n: int,
    m: int = MATCHUP_PRIOR_PA,
) -> dict[BaseOutState, dict[Outcome, float]]:
    """Mix a matchup-specific outcome distribution toward the league prior.

    For every pre-state present in ``league`` (and any extra state that
    only the matchup sample saw):

    ``p = (n / (n + M)) * p_raw + (M / (n + M)) * p_league``

    then renormalize that state's outgoing mass to 1. ``n`` is the
    matchup's plate-appearance count (``bat_event_fl = 'T'`` events only,
    never the raw transition-row total, which also counts steals, wild
    pitches, and other non-PA events the chain keeps). ``M`` defaults to
    :data:`MATCHUP_PRIOR_PA` (350, *The Book*).

    ``n = 0`` returns a copy of ``league``: a matchup with no history is
    the league distribution, not a zeroed chain that would hang the
    simulator. A pre-state missing from ``raw`` copies the league
    distribution for that state (the matchup has no evidence there).
    """
    if n < 0:
        raise MarkovError(f"n must be non-negative, got {n}")
    if m <= 0:
        raise MarkovError(f"m must be positive, got {m}")
    if n == 0:
        return {pre: dict(outcomes) for pre, outcomes in league.items()}
    weight = n / (n + m)
    prior_weight = 1.0 - weight
    states = set(league) | set(raw)
    mixed: dict[BaseOutState, dict[Outcome, float]] = {}
    for pre in states:
        raw_outcomes = raw.get(pre, {})
        league_outcomes = league.get(pre, {})
        if not raw_outcomes:
            mixed[pre] = dict(league_outcomes)
            continue
        keys = set(raw_outcomes) | set(league_outcomes)
        blended = {
            outcome: weight * raw_outcomes.get(outcome, 0.0)
            + prior_weight * league_outcomes.get(outcome, 0.0)
            for outcome in keys
        }
        total = sum(blended.values())
        if total <= 0:
            raise MarkovError(f"shrink produced no mass for state {pre}")
        probs = {outcome: mass / total for outcome, mass in blended.items() if mass > 0}
        _validate_probabilities_sum_to_one(probs)
        mixed[pre] = probs
    return mixed


def _validate_bat_home(bat_home: str | None) -> None:
    """A typo like 'home'/'away' would otherwise silently match zero SQL
    rows (``bat_home_id`` only ever holds '0'/'1') and return an empty
    distribution instead of failing loudly."""
    if bat_home is not None and bat_home not in ("0", "1"):
        raise MarkovError(f"bat_home must be '0', '1', or None, got {bat_home!r}")


def estimate_outcome_distribution(
    conn: psycopg.Connection, seasons: Sequence[int], bat_home: Literal["0", "1"] | None = None
) -> dict[BaseOutState, dict[Outcome, float]]:
    """Estimate the joint (post_state, runs_scored) outcome distribution
    from real Retrosheet play-by-play for the given regular-season years
    -- the input simulate_half_inning/simulate_half_innings need. Returns
    an empty dict, matching estimate_transition_matrix's "not ready yet"
    contract, if either source table hasn't been bootstrapped.

    `bat_home` optionally scopes to one batting side only ('1' = home,
    '0' = away) -- None (the default) combines both sides into one
    league-average distribution, matching every prior Plan 04D package's
    behavior. Real per-play scoring rates genuinely differ by batting
    side in most seasons (verified directly against real data, ADR-080)
    -- pass '1'/'0' to get each side's own distribution for
    `simulate_game`'s optional `home_distribution` parameter. Raises
    MarkovError for any other value -- a typo like 'home'/'away' would
    otherwise silently match zero SQL rows (bat_home_id only ever
    contains '0'/'1') and return an empty distribution instead of
    failing loudly."""
    _validate_seasons(seasons)
    _validate_bat_home(bat_home)
    rows = _fetch_transition_counts(conn, seasons, bat_home)
    return build_outcome_distribution(rows)


def fetch_matchup_transition_counts(
    conn: psycopg.Connection,
    seasons: Sequence[int],
    *,
    bat_home: Literal["0", "1"] | None = None,
    batting_team: str | None = None,
    pitching_team: str | None = None,
    pit_id: str | None = None,
    exclude_game_id: str | None = None,
    before_date: date | None = None,
) -> tuple[list[TransitionCountRow], int]:
    """Return ``(transition rows, n_pa)`` for one Retrosheet matchup slice.

    The low-level primitive behind :func:`estimate_matchup_distribution`;
    call that instead unless you need the raw rows and PA count (e.g. to
    build a cutoff-aware league prior once and reuse it across a slate).

    Every filter is point-in-time safe: ``exclude_game_id`` drops the
    target game and ``before_date`` keeps only games played strictly
    before it. Returns ``([], 0)`` when the Retrosheet tables are absent.

    ``n_pa`` is ``bat_event_fl = 'T'`` (The Book's sample). Non-PA
    events (SB, WP, …) still enter the chain; they just do not inflate
    the prior weight. If the flag is absent or never 'T', fall back to
    the raw transition total so a real sample is not treated as n=0.

    ``bat_home`` ('1' = home half, '0' = away half) optionally scopes to
    one batting side; per-play scoring rates differ by side (ADR-080).
    """
    _validate_bat_home(bat_home)
    if not _retrosheet_tables_ready(conn):
        return [], 0
    with conn.cursor() as cur:
        cur.execute(
            _MATCHUP_COUNTS_SQL,
            {
                "seasons": [str(s) for s in seasons],
                "bat_home": bat_home,
                "batting_team": batting_team,
                "pitching_team": pitching_team,
                "pit_id": pit_id,
                "exclude_game_id": exclude_game_id,
                "before_date": before_date,
            },
        )
        rows: list[TransitionCountRow] = []
        n_pa = 0
        for rec in cur.fetchall():
            # The SQL SELECTs the 10 TransitionCountRow fields, then n_pa
            # last -- index rather than star-unpack so a future column
            # added mid-list can't silently shift the mapping.
            rows.append(TransitionCountRow(*rec[:-1]))
            n_pa += int(rec[-1] or 0)
    if n_pa == 0:
        n_pa = sum(row.n for row in rows)
    return rows, n_pa


def estimate_matchup_distribution(
    conn: psycopg.Connection,
    seasons: Sequence[int],
    *,
    bat_home: Literal["0", "1"] | None = None,
    batting_team: str | None = None,
    pitching_team: str | None = None,
    pit_id: str | None = None,
    pitcher_min_pa: int = 0,
    exclude_game_id: str | None = None,
    before_date: date | None = None,
    prior_pa: int = MATCHUP_PRIOR_PA,
    league: dict[BaseOutState, dict[Outcome, float]] | None = None,
) -> dict[BaseOutState, dict[Outcome, float]]:
    """League-shrunk outcome distribution for one matchup.

    Counts Retrosheet events for the optional pitching/batting/pitcher
    filters, then mixes that sample toward the *same-cutoff* league
    distribution with :func:`shrink_outcome_distribution`. The league
    prior uses the same ``bat_home`` / ``exclude_game_id`` /
    ``before_date`` filters — shrinking toward a future-informed or
    wrong-batting-side league average would leak the target game (and
    every later game in ``seasons``) into a sparse matchup, or mix in
    the other half-inning's scoring rate (ADR-080).

    ``bat_home`` ('1' = this team batting at home, '0' = on the road)
    scopes both the sample and the prior to one half-inning. ``None``
    combines both, matching the league estimator's default.

    ``pit_id`` scopes the sample to one starting pitcher. When
    ``pitcher_min_pa`` is set and that pitcher's sample has fewer than
    ``pitcher_min_pa`` plate appearances, the pitcher filter is dropped
    and the sample falls back to batting-team vs pitching-team — a thin
    starter history is worse evidence than the team-level matchup, and
    both then shrink toward the same league prior.

    Pass a precomputed ``league`` to avoid refetching it for every
    side of every game on a slate. The caller must build that prior
    with the same cutoff *and the same ``bat_home``*.

    A matchup with no matching rows at all (unknown team, first meeting,
    missing tables) returns the cutoff league distribution unchanged.
    Shrink ``n`` is plate appearances (``bat_event_fl = 'T'``), not
    every transition.
    """
    _validate_seasons(seasons)
    _validate_bat_home(bat_home)
    if league is None:
        league_rows, _league_n = fetch_matchup_transition_counts(
            conn,
            seasons,
            bat_home=bat_home,
            exclude_game_id=exclude_game_id,
            before_date=before_date,
        )
        league = build_outcome_distribution(league_rows) if league_rows else {}
    if not league:
        return {}
    rows, n_pa = fetch_matchup_transition_counts(
        conn,
        seasons,
        bat_home=bat_home,
        batting_team=batting_team,
        pitching_team=pitching_team,
        pit_id=pit_id,
        exclude_game_id=exclude_game_id,
        before_date=before_date,
    )
    if pit_id is not None and n_pa < pitcher_min_pa:
        rows, n_pa = fetch_matchup_transition_counts(
            conn,
            seasons,
            bat_home=bat_home,
            batting_team=batting_team,
            pitching_team=pitching_team,
            exclude_game_id=exclude_game_id,
            before_date=before_date,
        )
    raw = build_outcome_distribution(rows) if rows else {}
    return shrink_outcome_distribution(raw, league, n_pa, m=prior_pa)


def simulate_half_inning_steps(
    distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    start: BaseOutState = EMPTY_ZERO_OUTS,
) -> Iterator[int]:
    """Yield the runs scored by each individual play of a simulated
    half-inning, one at a time, stopping once TERMINAL (3 outs) is
    reached. `simulate_half_inning` is just `sum(...)` over this; a
    caller that needs to react to the score after every play --
    `simulate_game`'s walk-off check, which must be able to end a
    half-inning the instant the home team takes the lead rather than
    waiting for all 3 outs -- needs this lower-level generator instead.
    Same injected-`random.Random`/dead-end-state contract as
    `simulate_half_inning`."""
    state = start
    while state != TERMINAL:
        outcomes = distribution.get(state)
        if not outcomes:
            raise MarkovError(f"no observed outcomes for state {state}, cannot simulate")
        chosen = rng.choices(list(outcomes.keys()), weights=list(outcomes.values()), k=1)[0]
        yield chosen.runs
        state = chosen.post


def simulate_half_inning(
    distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    start: BaseOutState = EMPTY_ZERO_OUTS,
) -> int:
    """Simulate one half-inning by sampling outcomes from `distribution`
    starting at `start` (bases empty, 0 outs by default) until reaching
    TERMINAL, summing runs scored along the way. `rng` is an injected
    random.Random instance -- a caller seeds it for deterministic,
    reproducible simulation runs; this function never seeds its own.
    Raises MarkovError if a reached state has no observed outcomes at all
    (e.g. a rare configuration absent from a narrow real sample) rather
    than silently hanging or returning a nonsensical result."""
    return sum(simulate_half_inning_steps(distribution, rng, start))


def simulate_half_innings(
    distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    count: int,
    start: BaseOutState = EMPTY_ZERO_OUTS,
) -> list[int]:
    """Simulate `count` independent half-innings, returning each one's
    total runs scored -- the Monte Carlo sample a calibration check
    compares against the real historical per-half-inning run
    distribution."""
    if count < 0:
        raise MarkovError(f"count must be non-negative, got {count}")
    return [simulate_half_inning(distribution, rng, start) for _ in range(count)]


@dataclass(frozen=True)
class GameResult:
    away_runs: int
    home_runs: int
    innings: int


def simulate_game(
    distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    regulation_innings: int = 9,
    max_innings: int = 30,
    home_distribution: dict[BaseOutState, dict[Outcome, float]] | None = None,
) -> GameResult:
    """Simulate a full game -- both teams alternating half-innings --
    applying baseball's actual game-ending rules instead of always
    playing a fixed number of complete innings: if the home team is
    already leading after the top of the `regulation_innings`th inning
    (or any inning after it), the bottom half is skipped entirely (no
    need to bat); if the home team takes the lead mid-half-inning in the
    bottom of the `regulation_innings`th inning or later, the game ends
    immediately on that play (a walk-off) via `simulate_half_inning_steps`
    rather than finishing the half-inning's remaining outs. Extra
    innings continue for as long as the score is tied after a completed
    (or walked-off) inning at or past `regulation_innings`.

    The away team always draws from `distribution`. The home team draws
    from `home_distribution` if given, otherwise from `distribution` too
    (the original, backward-compatible behavior -- no team-specific
    modeling at all). Splitting the two is real, not cosmetic: real
    per-play scoring rates genuinely differ by batting side in most
    seasons (verified directly against real data, ADR-080), which one
    combined league-average `distribution` can't capture.

    Unlike a single half-inning (guaranteed to reach TERMINAL in finitely
    many steps, since outs never decrease), a tied extra-innings game has
    no such structural guarantee -- it terminates "almost surely" for any
    real, non-degenerate estimated distribution, but not for a narrow or
    degenerate one (e.g. a distribution with zero probability of ever
    breaking a tie). `max_innings` (default 30 -- MLB's longest games on
    record run to 25-26 innings; :func:`simulate_home_win_rate` overrides
    it to :data:`SIM_MAX_INNINGS` for its Monte Carlo) is a defensive
    bound raising :class:`DegenerateSimulation` if exceeded, rather than
    hanging forever, matching `simulate_half_inning`'s own "fail loudly,
    don't hang" contract for a dead-end state. Must be strictly greater
    than `regulation_innings` --
    equal would leave no room for even one extra inning, so any tied
    regulation game would immediately hit this guard instead of ever
    getting a chance to resolve."""
    if regulation_innings < 1:
        raise MarkovError(f"regulation_innings must be at least 1, got {regulation_innings}")
    if max_innings <= regulation_innings:
        raise MarkovError(
            f"max_innings ({max_innings}) must be greater than regulation_innings "
            f"({regulation_innings}) -- equal leaves no room for even one extra inning"
        )
    home_dist = home_distribution if home_distribution is not None else distribution
    away_runs = 0
    home_runs = 0
    inning = 0
    while True:
        inning += 1
        if inning > max_innings:
            raise DegenerateSimulation(
                f"game still tied after {max_innings} innings -- no sampled path broke the tie"
            )
        away_runs += simulate_half_inning(distribution, rng)
        if inning >= regulation_innings and home_runs > away_runs:
            break  # home already ahead after the top half; no need to bat
        if inning >= regulation_innings:
            for runs in simulate_half_inning_steps(home_dist, rng):
                home_runs += runs
                if home_runs > away_runs:
                    break  # walk-off: the game ends on this exact play
        else:
            home_runs += simulate_half_inning(home_dist, rng)
        if inning >= regulation_innings and home_runs != away_runs:
            break  # decided in regulation or later; anything but a tie ends it
    return GameResult(away_runs=away_runs, home_runs=home_runs, innings=inning)


def simulate_home_win_rate(
    away_distribution: dict[BaseOutState, dict[Outcome, float]],
    home_distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    n_games: int,
    regulation_innings: int = 9,
    max_innings: int = SIM_MAX_INNINGS,
) -> float:
    """Fraction of simulated games the home side wins.

    ``n_games`` must be positive. Each trial calls :func:`simulate_game`
    with the away side drawing from ``away_distribution`` and the home
    side from ``home_distribution``. Ties cannot occur in
    ``simulate_game`` (extra innings continue until a winner), so the
    rate is wins / n_games with no push handling.

    A single trial that is still tied at ``max_innings`` is *not* proof the
    distribution is degenerate: a valid low-scoring distribution with a
    positive tie-breaking path can still, by sampling luck, stay tied for
    100 innings (the estimated distribution has no automatic-runner rule, so
    its extras run longer than the modern game -- ADR-079). Such a trial is
    dropped and the rate is taken over the games that *did* resolve. Only
    when an implausible fraction of trials fail to resolve
    (``_UNRESOLVED_TRIAL_LIMIT``) is the distribution declared degenerate and
    :class:`DegenerateSimulation` raised -- at which point the caller
    (``sim_predict.predict``) skips just that one matchup, keeping the rest
    of the slate and log5/Elo/GBM (same transaction).
    """
    if n_games < 1:
        raise MarkovError(f"n_games must be positive, got {n_games}")
    wins = 0
    unresolved = 0
    for _ in range(n_games):
        try:
            result = simulate_game(
                away_distribution,
                rng,
                regulation_innings=regulation_innings,
                max_innings=max_innings,
                home_distribution=home_distribution,
            )
        except DegenerateSimulation:
            unresolved += 1
            continue
        if result.home_runs > result.away_runs:
            wins += 1
    resolved = n_games - unresolved
    # max(1, ...) so a single unlucky trial never trips the guard even at the
    # small n_games tests and callers use -- it is a fraction-of-a-large-run
    # signal, not a "one is too many" one.
    if resolved == 0 or unresolved > max(1, n_games * _UNRESOLVED_TRIAL_LIMIT):
        raise DegenerateSimulation(
            f"{unresolved}/{n_games} simulated games never broke a tie within "
            f"{max_innings} innings -- the estimated distribution is degenerate"
        )
    return wins / resolved


def real_half_inning_runs(conn: psycopg.Connection, seasons: Sequence[int]) -> list[int]:
    """Real per-half-inning run totals from Retrosheet play-by-play for the
    given regular-season years -- one value per (game, inning, side), what
    `simulate_half_innings`' output is compared against for Plan 04D's
    calibration check ("Calibrate composed distributions against held-out
    seasons and real forward results"). Returns an empty list, matching
    every other estimator here's "not ready yet" contract, if either
    source table hasn't been bootstrapped."""
    _validate_seasons(seasons)
    if not _retrosheet_tables_ready(conn):
        return []
    with conn.cursor() as cur:
        cur.execute(_HALF_INNING_RUNS_SQL, {"seasons": [str(s) for s in seasons]})
        return [int(total_runs) for _game_id, _inning, _side, total_runs in cur.fetchall()]


def real_game_scores(conn: psycopg.Connection, seasons: Sequence[int]) -> list[GameResult]:
    """Real final game scores from Retrosheet for the given regular-season
    years -- one `GameResult` per game, what `simulate_game`'s output is
    compared against for Plan 04D's game-level calibration check. Returns
    an empty list, matching every other estimator here's "not ready yet"
    contract, if either source table hasn't been bootstrapped."""
    _validate_seasons(seasons)
    if not _retrosheet_tables_ready(conn):
        return []
    with conn.cursor() as cur:
        cur.execute(_GAME_SCORES_SQL, {"seasons": [str(s) for s in seasons]})
        return [
            GameResult(away_runs=away_runs, home_runs=home_runs, innings=innings)
            for _game_id, away_runs, home_runs, innings in cur.fetchall()
        ]


def summarize_runs(values: Sequence[int]) -> dict[str, float]:
    """Basic descriptive stats for a per-half-inning run distribution --
    used to compare a simulated distribution (simulate_half_innings)
    against the real one (real_half_inning_runs). Deliberately just
    descriptive stats, not a pass/fail threshold: unlike run expectancy
    (which has published RE24 tables to compare against), this project has
    no established tolerance yet for "close enough" on a full distributional
    comparison -- reporting the real numbers honestly is what's shippable
    now, not an invented bar. Raises MarkovError on empty input rather than
    silently returning NaN/zero stats for a comparison that never actually
    ran."""
    if not values:
        raise MarkovError("cannot summarize an empty run distribution")
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 0:
        median = (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    else:
        median = float(ordered[n // 2])
    # Nearest-rank percentile: the ceil(p*n)-th smallest value (1-indexed).
    p90_rank = math.ceil(0.9 * n)
    return {
        "count": float(n),
        "mean": sum(ordered) / n,
        "median": median,
        "p90": float(ordered[p90_rank - 1]),
        "max": float(ordered[-1]),
    }


@dataclass(frozen=True)
class PitchArsenal:
    """Pitcher arsenal composition and effectiveness across pitch types."""

    player_id: str
    season: int
    pitch_usage: dict[str, float]
    run_values_per_100: dict[str, float]
    woba_against: dict[str, float]
    whiff_pct: dict[str, float]


@dataclass(frozen=True)
class BatterArsenalProfile:
    """Batter performance and plate discipline vs specific pitch types."""

    player_id: str
    season: int
    pitches_seen: dict[str, int]
    run_values_per_100: dict[str, float]
    woba: dict[str, float]
    whiff_pct: dict[str, float]


def fetch_pitcher_arsenal(
    conn: psycopg.Connection, pitcher_id: str, season: int
) -> PitchArsenal | None:
    """Fetch pitcher arsenal statistics from raw.statcast_pitcher_arsenal_stat."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitcher_arsenal_stat')")
        (table_exists,) = fetch_one(cur)
        if not table_exists:
            return None

        cur.execute(_PITCHER_ARSENAL_SQL, {"player_id": str(pitcher_id), "season": str(season)})
        rows = cur.fetchall()
        if not rows:
            return None

        pitch_usage: dict[str, float] = {}
        run_values: dict[str, float] = {}
        woba_against: dict[str, float] = {}
        whiff_pct: dict[str, float] = {}

        for _pid, ptype, usage, rv100, woba, whiff in rows:
            if ptype:
                if usage is not None:
                    pitch_usage[ptype] = float(usage)
                if rv100 is not None:
                    run_values[ptype] = float(rv100)
                if woba is not None:
                    woba_against[ptype] = float(woba)
                if whiff is not None:
                    whiff_pct[ptype] = float(whiff)

        return PitchArsenal(
            player_id=str(pitcher_id),
            season=season,
            pitch_usage=pitch_usage,
            run_values_per_100=run_values,
            woba_against=woba_against,
            whiff_pct=whiff_pct,
        )


def fetch_batter_arsenal(
    conn: psycopg.Connection, batter_id: str, season: int
) -> BatterArsenalProfile | None:
    """Fetch batter pitch-type profile from raw.statcast_batter_arsenal."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_batter_arsenal')")
        (table_exists,) = fetch_one(cur)
        if not table_exists:
            return None

        cur.execute(_BATTER_ARSENAL_SQL, {"player_id": str(batter_id), "season": str(season)})
        rows = cur.fetchall()
        if not rows:
            return None

        pitches_seen: dict[str, int] = {}
        run_values: dict[str, float] = {}
        woba: dict[str, float] = {}
        whiff_pct: dict[str, float] = {}

        for _pid, ptype, cnt, rv100, woba_val, whiff in rows:
            if ptype:
                if cnt is not None:
                    pitches_seen[ptype] = int(cnt)
                if rv100 is not None:
                    run_values[ptype] = float(rv100)
                if woba_val is not None:
                    woba[ptype] = float(woba_val)
                if whiff is not None:
                    whiff_pct[ptype] = float(whiff)

        return BatterArsenalProfile(
            player_id=str(batter_id),
            season=season,
            pitches_seen=pitches_seen,
            run_values_per_100=run_values,
            woba=woba,
            whiff_pct=whiff_pct,
        )


def compute_arsenal_matchup_edge(pitcher: PitchArsenal, batter: BatterArsenalProfile) -> float:
    """Compute expected run value edge per 100 pitches for a batter facing a pitcher.

    Positive edge indicates batter advantage; negative indicates pitcher advantage.
    """
    total_usage = sum(pitcher.pitch_usage.values())
    if total_usage <= 0:
        return 0.0

    matchup_edge = 0.0
    for ptype, usage in pitcher.pitch_usage.items():
        norm_usage = usage / total_usage
        batter_rv = batter.run_values_per_100.get(ptype, 0.0)
        pitcher_rv = pitcher.run_values_per_100.get(ptype, 0.0)
        # Batter advantage is batter run value minus pitcher run value
        matchup_edge += norm_usage * (batter_rv - pitcher_rv)

    return matchup_edge


def adjust_outcome_distribution_for_matchup(
    base_distribution: dict[BaseOutState, dict[Outcome, float]],
    edge_runs_per_100: float,
    scale_factor: float = 0.05,
) -> dict[BaseOutState, dict[Outcome, float]]:
    """Adjust a base/out outcome distribution for a specific matchup edge.

    Scales scoring and advancing transition probabilities using an odds multiplier,
    then re-normalizes each state's outgoing distribution so sum of probabilities is 1.0.
    """
    if abs(edge_runs_per_100) < 1e-6:
        return base_distribution

    multiplier = math.exp(scale_factor * edge_runs_per_100)
    inverse_multiplier = 1.0 / multiplier

    adjusted: dict[BaseOutState, dict[Outcome, float]] = {}

    for pre, outcome_probs in base_distribution.items():
        new_counts: dict[Outcome, float] = {}
        for outcome, prob in outcome_probs.items():
            # Scoring or non-out advancing play
            is_positive = (outcome.runs > 0) or (
                outcome.post != TERMINAL and outcome.post.outs == pre.outs
            )
            weight = multiplier if is_positive else inverse_multiplier
            new_counts[outcome] = prob * weight

        total_weight = sum(new_counts.values())
        if total_weight > 0:
            adjusted[pre] = {outcome: w / total_weight for outcome, w in new_counts.items()}
        else:
            adjusted[pre] = outcome_probs

    return adjusted


def simulate_matchup_game(
    base_distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    home_edge_runs_per_100: float = 0.0,
    away_edge_runs_per_100: float = 0.0,
    regulation_innings: int = 9,
    max_innings: int = 30,
) -> GameResult:
    """Simulate a game between two teams with specific pitch-arsenal matchup edges."""
    home_dist = adjust_outcome_distribution_for_matchup(base_distribution, home_edge_runs_per_100)
    away_dist = adjust_outcome_distribution_for_matchup(base_distribution, away_edge_runs_per_100)

    return simulate_game(
        distribution=away_dist,
        rng=rng,
        regulation_innings=regulation_innings,
        max_innings=max_innings,
        home_distribution=home_dist,
    )


@dataclass(frozen=True)
class InGameSimulationResult:
    """Aggregated Monte Carlo results for an in-progress game forecast."""

    home_win_prob: float
    away_win_prob: float
    home_cover_run_line_prob: float
    away_cover_run_line_prob: float
    expected_home_final_runs: float
    expected_away_final_runs: float
    expected_total_runs: float
    simulations_run: int


def _simulate_remainder_of_game(
    distribution: dict[BaseOutState, dict[Outcome, float]],
    home_dist: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    current_inning: int,
    is_bottom_half: bool,
    current_state: BaseOutState,
    home_score: int,
    away_score: int,
    regulation_innings: int = 9,
    max_innings: int = 30,
) -> GameResult:
    """Simulate the remaining plays of an in-progress game from its current state."""
    home_runs = home_score
    away_runs = away_score
    inning = current_inning

    # 1. Complete the current half-inning
    if not is_bottom_half:
        # Top half in progress
        away_runs += sum(simulate_half_inning_steps(distribution, rng, start=current_state))
        # Now play bottom of current inning
        if not (inning >= regulation_innings and home_runs > away_runs):
            if inning >= regulation_innings:
                for runs in simulate_half_inning_steps(home_dist, rng):
                    home_runs += runs
                    if home_runs > away_runs:
                        break
            else:
                home_runs += simulate_half_inning(home_dist, rng)
    else:
        # Bottom half in progress
        if inning >= regulation_innings:
            for runs in simulate_half_inning_steps(home_dist, rng, start=current_state):
                home_runs += runs
                if home_runs > away_runs:
                    break
        else:
            home_runs += sum(simulate_half_inning_steps(home_dist, rng, start=current_state))

    # Check if game is already decided
    if inning >= regulation_innings and home_runs != away_runs:
        return GameResult(away_runs=away_runs, home_runs=home_runs, innings=inning)

    # 2. Continue to subsequent innings if tied or regulation not reached
    while True:
        inning += 1
        if inning > max_innings:
            raise MarkovError(f"game still tied after {max_innings} innings during in-game sim")

        away_runs += simulate_half_inning(distribution, rng)
        if inning >= regulation_innings and home_runs > away_runs:
            break

        if inning >= regulation_innings:
            for runs in simulate_half_inning_steps(home_dist, rng):
                home_runs += runs
                if home_runs > away_runs:
                    break
        else:
            home_runs += simulate_half_inning(home_dist, rng)

        if inning >= regulation_innings and home_runs != away_runs:
            break

    return GameResult(away_runs=away_runs, home_runs=home_runs, innings=inning)


def simulate_in_game_win_probability(
    distribution: dict[BaseOutState, dict[Outcome, float]],
    rng: random.Random,
    current_inning: int,
    is_bottom_half: bool,
    current_state: BaseOutState,
    home_score: int,
    away_score: int,
    home_edge_runs_per_100: float = 0.0,
    away_edge_runs_per_100: float = 0.0,
    n_simulations: int = 5000,
    regulation_innings: int = 9,
    max_innings: int = 30,
) -> InGameSimulationResult:
    """Run massive Monte Carlo simulation of an in-progress game to calculate live win probability.

    Returns empirical probability distribution of game winner, run lines, and projected total runs.
    """
    if n_simulations <= 0:
        raise MarkovError("n_simulations must be positive")

    home_dist = adjust_outcome_distribution_for_matchup(distribution, home_edge_runs_per_100)
    away_dist = adjust_outcome_distribution_for_matchup(distribution, away_edge_runs_per_100)

    home_wins = 0
    home_covers = 0  # Home wins by 2+ (covers -1.5 run line)
    total_home_runs = 0
    total_away_runs = 0

    for _ in range(n_simulations):
        res = _simulate_remainder_of_game(
            distribution=away_dist,
            home_dist=home_dist,
            rng=rng,
            current_inning=current_inning,
            is_bottom_half=is_bottom_half,
            current_state=current_state,
            home_score=home_score,
            away_score=away_score,
            regulation_innings=regulation_innings,
            max_innings=max_innings,
        )
        if res.home_runs > res.away_runs:
            home_wins += 1
            if res.home_runs - res.away_runs >= 2:
                home_covers += 1
        total_home_runs += res.home_runs
        total_away_runs += res.away_runs

    home_win_prob = home_wins / n_simulations
    away_win_prob = 1.0 - home_win_prob
    home_cover_prob = home_covers / n_simulations
    away_cover_prob = 1.0 - home_cover_prob

    return InGameSimulationResult(
        home_win_prob=home_win_prob,
        away_win_prob=away_win_prob,
        home_cover_run_line_prob=home_cover_prob,
        away_cover_run_line_prob=away_cover_prob,
        expected_home_final_runs=total_home_runs / n_simulations,
        expected_away_final_runs=total_away_runs / n_simulations,
        expected_total_runs=(total_home_runs + total_away_runs) / n_simulations,
        simulations_run=n_simulations,
    )
