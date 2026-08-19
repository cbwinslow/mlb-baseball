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

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import psycopg

from mlb_baseball.sql import read_sql

_TRANSITION_COUNTS_SQL = read_sql("markov_transition_counts.sql")


@dataclass(frozen=True)
class BaseOutState:
    outs: int
    on1: bool = False
    on2: bool = False
    on3: bool = False


# The shared absorbing state every 3-outs transition collapses into --
# base occupancy is meaningless once the half-inning is over.
TERMINAL = BaseOutState(outs=3)

TRANSIENT_STATES: tuple[BaseOutState, ...] = tuple(
    BaseOutState(o, b1, b2, b3)
    for o in (0, 1, 2)
    for b1 in (False, True)
    for b2 in (False, True)
    for b3 in (False, True)
)


class MarkovError(ValueError):
    """A base/out transition dataset failed a physical or probability invariant."""


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
    if row.n < 0:
        raise MarkovError(f"negative row count: {row}")
    if row.runs_scored < 0:
        raise MarkovError(f"negative runs_scored: {row}")
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


def _validate_probabilities_sum_to_one(
    post_probs: dict[BaseOutState, float], tolerance: float = 1e-9
) -> None:
    total = sum(post_probs.values())
    if abs(total - 1.0) > tolerance:
        raise MarkovError(f"post-state probabilities sum to {total}, not 1.0")


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


def _fetch_transition_counts(
    conn: psycopg.Connection, seasons: Sequence[int]
) -> list[TransitionCountRow]:
    with conn.cursor() as cur:
        cur.execute(_TRANSITION_COUNTS_SQL, {"seasons": [str(s) for s in seasons]})
        return [TransitionCountRow(*row) for row in cur.fetchall()]


def estimate_transition_matrix(
    conn: psycopg.Connection, seasons: Sequence[int]
) -> dict[BaseOutState, dict[BaseOutState, float]]:
    """Estimate the base/out transition matrix from real Retrosheet
    play-by-play for the given regular-season years."""
    rows = _fetch_transition_counts(conn, seasons)
    return build_transition_matrix(rows)


def _immediate_expected_runs(rows: Iterable[TransitionCountRow]) -> dict[BaseOutState, float]:
    """Expected runs scored on the very next play from each pre-state,
    marginalized over every observed outcome (count-weighted average of
    row.runs_scored across every row sharing that pre-state) -- this is
    exactly sum_post P(pre->post) * E[runs | pre->post] by construction,
    the "immediate reward" term the run-expectancy linear system needs."""
    totals: dict[BaseOutState, int] = {}
    weighted_runs: dict[BaseOutState, int] = {}
    for row in rows:
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
    re = np.linalg.solve(np.eye(n) - q, r)
    return {state: float(re[i]) for state, i in index.items()}


def estimate_run_expectancy(
    conn: psycopg.Connection, seasons: Sequence[int]
) -> dict[BaseOutState, float]:
    """Estimate the RE24-style run-expectancy table from real Retrosheet
    play-by-play for the given regular-season years."""
    rows = _fetch_transition_counts(conn, seasons)
    matrix = build_transition_matrix(rows)
    immediate_runs = _immediate_expected_runs(rows)
    return run_expectancy(matrix, immediate_runs)
