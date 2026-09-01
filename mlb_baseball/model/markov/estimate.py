"""DB-reading estimators for the base/out Markov chain -- the DB-reading half
of the markov package. Everything here takes a psycopg.Connection and reads
Retrosheet or Statcast, then hands in-memory values to markov.core.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.model.markov.core import (
    MATCHUP_PRIOR_PA,
    BaseOutState,
    BatterArsenalProfile,
    GameResult,
    Outcome,
    PitchArsenal,
    TransitionCountRow,
    _immediate_expected_runs,
    _validate_bat_home,
    _validate_seasons,
    build_outcome_distribution,
    build_transition_matrix,
    run_expectancy,
    shrink_outcome_distribution,
)
from mlb_baseball.sql import read_sql

__all__ = [
    "estimate_transition_matrix",
    "estimate_run_expectancy",
    "estimate_outcome_distribution",
    "fetch_matchup_transition_counts",
    "estimate_matchup_distribution",
    "real_half_inning_runs",
    "real_game_scores",
    "fetch_pitcher_arsenal",
    "fetch_batter_arsenal",
]

_ARSENAL_FIRST_SEASON = 1871


def _validated_season(season: int | str) -> int:
    """Coerce ``season`` to ``int`` and bounds-check it.

    A numeric string ("2019") is accepted -- the arsenal SQL binds
    ``str(season)`` regardless, so that shape worked before this guard
    existed and rejecting it would be a needless behaviour change. A
    ``float`` or ``bool`` is rejected, not coerced: ``int(2019.9)`` would
    silently query 2019, and ``int(True)`` would query 1. The upper bound
    tracks the calendar the way every Statcast connector does
    (``date.today().year``), plus one so an off-season lookup of next
    year's not-yet-played schedule doesn't spuriously fail; a fixed year
    would start rejecting valid current-season data once the wall clock
    passed it.
    """
    if isinstance(season, bool) or not isinstance(season, int | str):
        raise ValueError(f"season must be an int or numeric string, got {season!r}")
    try:
        year = int(season)
    except ValueError:
        raise ValueError(f"season must be an integer year, got {season!r}") from None
    max_season = date.today().year + 1
    if not (_ARSENAL_FIRST_SEASON <= year <= max_season):
        raise ValueError(
            f"season must be between {_ARSENAL_FIRST_SEASON} and {max_season}, got {year}"
        )
    return year


_TRANSITION_COUNTS_SQL = read_sql("markov_transition_counts.sql")
_MATCHUP_COUNTS_SQL = read_sql("markov_transition_counts_matchup.sql")
_HALF_INNING_RUNS_SQL = read_sql("markov_half_inning_runs.sql")
_GAME_SCORES_SQL = read_sql("markov_game_scores.sql")
_PITCHER_ARSENAL_SQL = read_sql("pitcher_arsenal_select.sql")
_BATTER_ARSENAL_SQL = read_sql("batter_arsenal_select.sql")


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
    _validate_seasons(seasons)
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


def fetch_pitcher_arsenal(
    conn: psycopg.Connection, pitcher_id: str, season: int | str
) -> PitchArsenal | None:
    """Fetch pitcher arsenal statistics from raw.statcast_pitcher_arsenal_stat.

    ``season`` accepts an int or a numeric string ("2019"); see
    ``_validated_season`` for the accepted range.
    """
    year = _validated_season(season)
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitcher_arsenal_stat')")
        (table_exists,) = fetch_one(cur)
        if not table_exists:
            return None

        cur.execute(_PITCHER_ARSENAL_SQL, {"player_id": str(pitcher_id), "season": str(year)})
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
            season=year,
            pitch_usage=pitch_usage,
            run_values_per_100=run_values,
            woba_against=woba_against,
            whiff_pct=whiff_pct,
        )


def fetch_batter_arsenal(
    conn: psycopg.Connection, batter_id: str, season: int | str
) -> BatterArsenalProfile | None:
    """Fetch batter pitch-type profile from raw.statcast_batter_arsenal.

    ``season`` accepts an int or a numeric string ("2019"); see
    ``_validated_season`` for the accepted range.
    """
    year = _validated_season(season)
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_batter_arsenal')")
        (table_exists,) = fetch_one(cur)
        if not table_exists:
            return None

        cur.execute(_BATTER_ARSENAL_SQL, {"player_id": str(batter_id), "season": str(year)})
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
            season=year,
            pitches_seen=pitches_seen,
            run_values_per_100=run_values,
            woba=woba,
            whiff_pct=whiff_pct,
        )
