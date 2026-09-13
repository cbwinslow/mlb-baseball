"""Serving Layer Access & Data Serialization (SRV-01, ADR-102).

Provides high-performance query interfaces into the `serve.*` views for web applications,
Astro static site generation, and external JSON APIs.
"""

from __future__ import annotations

import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check


def fetch_daily_betting_grid(
    game_date: datetime.date | str | None = None,
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    """Fetch the daily betting & prediction grid for a specific date (or all upcoming)."""

    def _query(c: psycopg.Connection) -> list[dict[str, Any]]:
        with c.cursor(row_factory=dict_row) as cur:
            if game_date is not None:
                cur.execute(
                    "SELECT * FROM serve.daily_betting_grid "
                    "WHERE game_date = %s ORDER BY game_date, mlb_game_pk",
                    (str(game_date),),
                )
            else:
                cur.execute(
                    "SELECT * FROM serve.daily_betting_grid "
                    "ORDER BY game_date DESC, mlb_game_pk LIMIT 100"
                )
            return list(cur.fetchall())

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)


def fetch_pitcher_card(
    player_id: int | None = None,
    mlbam_id: str | None = None,
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    """Fetch pitcher analytical profile card by internal player ID or MLBAM ID."""

    def _query(c: psycopg.Connection) -> list[dict[str, Any]]:
        with c.cursor(row_factory=dict_row) as cur:
            if player_id is not None:
                cur.execute(
                    "SELECT * FROM serve.pitcher_card "
                    "WHERE player_id = %s ORDER BY as_of_date DESC LIMIT 1",
                    (player_id,),
                )
            elif mlbam_id is not None:
                cur.execute(
                    "SELECT * FROM serve.pitcher_card "
                    "WHERE mlbam_id = %s ORDER BY as_of_date DESC LIMIT 1",
                    (mlbam_id,),
                )
            else:
                cur.execute("SELECT * FROM serve.pitcher_card ORDER BY as_of_date DESC LIMIT 50")
            return list(cur.fetchall())

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)


def fetch_prediction_market_alpha(
    min_edge: float = 0.025,
    game_date: datetime.date | str | None = None,
    limit: int = 50,
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    """Fetch active +EV contract recommendations on Kalshi & Polymarket."""

    def _query(c: psycopg.Connection) -> list[dict[str, Any]]:
        with c.cursor(row_factory=dict_row) as cur:
            if game_date is not None:
                cur.execute(
                    "SELECT * FROM serve.prediction_market_alpha "
                    "WHERE ABS(home_edge_alpha) >= %s AND game_date = %s "
                    "ORDER BY ABS(home_edge_alpha) DESC LIMIT %s",
                    (min_edge, str(game_date), limit),
                )
            else:
                # Default to recent active dates to optimize query execution
                cur.execute(
                    "SELECT * FROM serve.prediction_market_alpha "
                    "WHERE ABS(home_edge_alpha) >= %s "
                    "AND game_date >= CURRENT_DATE - INTERVAL '14 days' "
                    "ORDER BY ABS(home_edge_alpha) DESC LIMIT %s",
                    (min_edge, limit),
                )
            return list(cur.fetchall())

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)


def fetch_pitcher_prop_market(
    game_date: datetime.date | str | None = None,
    mlb_game_pk: str | None = None,
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    """Fetch projected pitcher strikeout props for games on a date or specific game_pk."""

    def _query(c: psycopg.Connection) -> list[dict[str, Any]]:
        with c.cursor(row_factory=dict_row) as cur:
            if mlb_game_pk is not None:
                cur.execute(
                    "SELECT * FROM serve.pitcher_prop_market WHERE mlb_game_pk = %s",
                    (str(mlb_game_pk),),
                )
            elif game_date is not None:
                cur.execute(
                    "SELECT * FROM serve.pitcher_prop_market "
                    "WHERE game_date = %s ORDER BY mlb_game_pk",
                    (str(game_date),),
                )
            else:
                cur.execute(
                    "SELECT * FROM serve.pitcher_prop_market ORDER BY game_date DESC LIMIT 50"
                )
            return list(cur.fetchall())

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)


def fetch_live_game_tracker(
    game_date: datetime.date | str | None = None,
    mlb_game_pk: str | None = None,
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    """Fetch live in-play game state and scores for games on a date or specific game_pk."""

    def _query(c: psycopg.Connection) -> list[dict[str, Any]]:
        with c.cursor(row_factory=dict_row) as cur:
            if mlb_game_pk is not None:
                cur.execute(
                    "SELECT * FROM serve.live_game_tracker WHERE mlb_game_pk = %s",
                    (str(mlb_game_pk),),
                )
            elif game_date is not None:
                cur.execute(
                    "SELECT * FROM serve.live_game_tracker "
                    "WHERE game_date = %s ORDER BY mlb_game_pk",
                    (str(game_date),),
                )
            else:
                cur.execute(
                    "SELECT * FROM serve.live_game_tracker ORDER BY game_date DESC LIMIT 50"
                )
            return list(cur.fetchall())

    if conn is not None:
        return _query(conn)
    with get_connection() as c:
        return _query(c)


def health_check() -> list[Check]:
    """Operational health check for the analytical serving layer (SRV-01, LIVE-01)."""
    checks: list[Check] = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.views WHERE table_schema = 'serve'"
                )
                views = {row[0] for row in cur.fetchall()}
                expected = {
                    "daily_betting_grid",
                    "pitcher_card",
                    "matchup_preview",
                    "prediction_market_alpha",
                    "pitcher_prop_market",
                    "live_game_tracker",
                }
                missing = expected - views
                if missing:
                    checks.append(
                        Check("serve views", False, f"missing views: {', '.join(sorted(missing))}")
                    )
                else:
                    checks.append(Check("serve views", True, "all 6 serving marts present"))

                # serve.ros_team_standings must be regular-season only
                # (ADR-282 / ADR-283). Check *decisions* (wins + losses), not
                # games_played: pre-1990 tie games were replayed in full and
                # both counted as games played (1989 PIT / SLN reached 164
                # games_played, 162 decisions), so games_played has a fuzzy
                # ceiling, but decisions do not -- since 1969 a team has at
                # most 162 + one Game 163 = 163 decisions, pre-1969 a
                # best-of-three pennant playoff reaches 165 (1962 SF 103-62).
                # A leaked postseason series is all decisions, so it still
                # trips this. Era-scoped to match report.health_check().
                if "ros_team_standings" in views:
                    cur.execute(
                        "SELECT count(*) FROM serve.ros_team_standings "
                        "WHERE wins + losses > CASE WHEN season < 1969 THEN 165 ELSE 163 END"
                    )
                    (over,) = cur.fetchone() or (0,)
                    detail = (
                        "ok"
                        if over == 0
                        else f"{over} team-seasons over the era envelope (postseason leaked in)"
                    )
                    checks.append(
                        Check("serve.ros_team_standings is regular-season only", over == 0, detail)
                    )
    except Exception as exc:
        checks.append(Check("serve views", False, str(exc)))
    return checks
