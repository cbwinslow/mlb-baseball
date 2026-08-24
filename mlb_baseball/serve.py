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
    conn: psycopg.Connection | None = None,
) -> list[dict[str, Any]]:
    """Fetch active +EV contract recommendations on Kalshi & Polymarket."""

    def _query(c: psycopg.Connection) -> list[dict[str, Any]]:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM serve.prediction_market_alpha "
                "WHERE ABS(home_edge_alpha) >= %s "
                "ORDER BY ABS(home_edge_alpha) DESC",
                (min_edge,),
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
