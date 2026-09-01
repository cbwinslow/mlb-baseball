"""Market-implied win probability as a comparison line against log5/Elo/
gbm's own predictions (ADR-053, ADR-267).

Two grains, both written by record():

1. Decided games — `core.market` joined through `core.game`. Retrospective:
   how the last pre-game snapshot predicted a game that has already been
   played. Idempotent via NOT EXISTS (the pre-game price in core.market
   does not change after conform).
2. Upcoming games — `gold.game_feature` rows with `home_win IS NULL`,
   matched to Kalshi/Polymarket through `raw.mlb_schedule` the same way
   starter probable-pitcher features are. Live: the latest snapshot
   strictly before first pitch. Each `mlb predict` run inserts a new
   snapshot (same shape as log5/elo/gbm); evaluation already picks one
   row per game at a named cutoff.

Polymarket and Kalshi stay distinct model_versions. Polymarket is filtered
to `sportsmarkettype = 'moneyline'` so spreads/F5 contracts cannot fan out
or replace a win probability (ADR-053 production finding). Only the home
side becomes home_win_prob.
"""

from __future__ import annotations

from ast import literal_eval
from datetime import date as date_cls
from datetime import datetime

import psycopg

from mlb_baseball.conform import (
    _KALSHI_TICKER_DATE_RE,
    _KALSHI_TICKER_TEAM_RE,
    _MONTH_ABBR,
    _POLYMARKET_SLUG_DATE_RE,
    _kalshi_snapshot_lookup,
    _latest_before,
    _polymarket_snapshot_lookup,
    _team_lookup,
)
from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check, check_join_coverage
from mlb_baseball.sql import read_sql

MODEL_VERSIONS = {"polymarket": "polymarket-v1", "kalshi": "kalshi-v1"}

_UPCOMING_INSERT = """
INSERT INTO gold.prediction (mlb_game_pk, game_instance_key, model_version, home_win_prob)
VALUES (%s, %s, %s, %s)
"""


def record(conn: psycopg.Connection) -> int:
    return _record_decided(conn) + _record_upcoming(conn)


def _record_decided(conn: psycopg.Connection) -> int:
    total = 0
    with conn.cursor() as cur:
        cur.execute(
            read_sql("market_polymarket_prediction_insert.sql"),
            {"model_version": MODEL_VERSIONS["polymarket"]},
        )
        total += cur.rowcount
        cur.execute(
            read_sql("market_kalshi_prediction_insert.sql"),
            {"model_version": MODEL_VERSIONS["kalshi"]},
        )
        total += cur.rowcount
    return total


def _record_upcoming(conn: psycopg.Connection) -> int:
    """Latest pre-game moneyline for still-unplayed gold.game_feature rows.

    Missing schedule/snapshot/event tables are a skip, not a crash — the
    same degrade-gracefully shape conform's market builder already uses.
    """
    games = _load_upcoming_games(conn)
    if not games:
        return 0
    by_alias = _team_lookup(conn)
    rows: list[tuple] = []
    rows.extend(_upcoming_polymarket_rows(conn, games, by_alias))
    rows.extend(_upcoming_kalshi_rows(conn, games, by_alias))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(_UPCOMING_INSERT, rows)
    return len(rows)


def _load_upcoming_games(conn: psycopg.Connection) -> list[dict]:
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(read_sql("market_upcoming_games.sql"))
                raw_rows = cur.fetchall()
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        return []

    games: list[dict] = []
    for mlb_game_pk, instance_key, game_date, home_id, away_id, start_text in raw_rows:
        if home_id is None or away_id is None or mlb_game_pk is None:
            continue
        start = _parse_datetime(start_text)
        if start is None:
            continue
        games.append(
            {
                "mlb_game_pk": mlb_game_pk,
                "game_instance_key": instance_key,
                "game_date": game_date,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "start_at": start,
            }
        )
    return games


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _unique_upcoming_lookups(
    games: list[dict],
) -> tuple[dict[tuple, dict], dict[tuple, dict]]:
    """Drop doubleheaders rather than guess which game a market is for —
    same 'leave it unmatched' rule as conform._game_lookup."""
    by_teams: dict[tuple, list[dict]] = {}
    by_date_team: dict[tuple, list[dict]] = {}
    for game in games:
        key = (game["game_date"], game["away_team_id"], game["home_team_id"])
        by_teams.setdefault(key, []).append(game)
        by_date_team.setdefault((game["game_date"], game["home_team_id"]), []).append(game)
        by_date_team.setdefault((game["game_date"], game["away_team_id"]), []).append(game)
    exact = {key: rows[0] for key, rows in by_teams.items() if len(rows) == 1}
    fuzzy = {key: rows[0] for key, rows in by_date_team.items() if len(rows) == 1}
    return exact, fuzzy


def _upcoming_polymarket_rows(
    conn: psycopg.Connection,
    games: list[dict],
    by_alias: dict[str, int],
) -> list[tuple]:
    exact, _fuzzy = _unique_upcoming_lookups(games)
    try:
        with conn.transaction():
            snapshots = _polymarket_snapshot_lookup(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.slug, e.teams, m.id, o.outcome
                    FROM raw.polymarket_event e
                    JOIN raw.polymarket_market m ON m.event_id = e.id
                    JOIN raw.polymarket_outcome o ON o.market_id = m.id
                    WHERE e.sport IS NOT NULL
                        AND m.sportsmarkettype = 'moneyline'
                    """
                )
                market_rows = cur.fetchall()
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        return []

    out: list[tuple] = []
    seen_games: set[str] = set()
    for slug, teams_text, market_id, outcome in market_rows:
        date_match = _POLYMARKET_SLUG_DATE_RE.search(slug or "")
        if not date_match:
            continue
        try:
            teams = literal_eval(teams_text) if teams_text else []
        except (ValueError, SyntaxError):
            continue
        if len(teams) != 2:
            continue
        away = next((t for t in teams if t.get("ordering") == "away"), None)
        home = next((t for t in teams if t.get("ordering") == "home"), None)
        if away is None or home is None:
            continue
        away_id = by_alias.get(away.get("name"))
        home_id = by_alias.get(home.get("name"))
        if away_id is None or home_id is None:
            continue
        if outcome != home.get("name"):
            continue
        game_date = date_cls.fromisoformat(date_match.group(1))
        game = exact.get((game_date, away_id, home_id))
        if game is None:
            continue
        pk = game["mlb_game_pk"]
        if pk in seen_games:
            continue
        price = _latest_before(snapshots.get((market_id, outcome), []), game["start_at"])
        if price is None:
            continue
        seen_games.add(pk)
        out.append((pk, game["game_instance_key"], MODEL_VERSIONS["polymarket"], price))
    return out


def _upcoming_kalshi_rows(
    conn: psycopg.Connection,
    games: list[dict],
    by_alias: dict[str, int],
) -> list[tuple]:
    _exact, fuzzy = _unique_upcoming_lookups(games)
    try:
        with conn.transaction():
            snapshots = _kalshi_snapshot_lookup(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ticker, event_ticker
                    FROM raw.kalshi_market
                    WHERE event_ticker LIKE 'KXMLBGAME%'
                    """
                )
                market_rows = cur.fetchall()
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        return []

    out: list[tuple] = []
    seen_games: set[str] = set()
    for ticker, event_ticker in market_rows:
        date_match = _KALSHI_TICKER_DATE_RE.match(event_ticker or "")
        team_match = _KALSHI_TICKER_TEAM_RE.search(ticker or "")
        if not date_match or not team_match:
            continue
        yy, mon_abbr, dd = date_match.groups()
        month = _MONTH_ABBR.get(mon_abbr)
        if month is None:
            continue
        game_date = date_cls.fromisoformat(f"{2000 + int(yy):04d}-{month:02d}-{int(dd):02d}")
        team_id = by_alias.get(team_match.group(1))
        if team_id is None:
            continue
        game = fuzzy.get((game_date, team_id))
        if game is None or team_id != game["home_team_id"]:
            continue
        pk = game["mlb_game_pk"]
        if pk in seen_games:
            continue
        price = _latest_before(snapshots.get(ticker, []), game["start_at"])
        if price is None:
            continue
        seen_games.add(pk)
        out.append((pk, game["game_instance_key"], MODEL_VERSIONS["kalshi"], price))
    return out


def _polymarket_coverage_check() -> Check:
    model_version = MODEL_VERSIONS["polymarket"]
    return check_join_coverage(
        "decided games with a resolved polymarket moneyline price get a recorded prediction",
        f"""
        SELECT count(*) FROM gold.prediction p
        JOIN gold.game_feature f ON f.game_instance_key = p.game_instance_key
        JOIN core.game g ON g.id = f.game_id
        WHERE p.model_version = '{model_version}'
        """,
        """
        SELECT count(*)
        FROM core.market m
        JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
        JOIN raw.polymarket_market pm ON pm.id = split_part(m.market_ref, ':', 1)
        WHERE m.source = 'polymarket'
            AND pm.sportsmarkettype = 'moneyline'
            AND m.implied_probability IS NOT NULL
            AND g.game_pk IS NOT NULL
        """,
        tolerance=0,
    )


def _kalshi_coverage_check() -> Check:
    model_version = MODEL_VERSIONS["kalshi"]
    return check_join_coverage(
        "decided games with a resolved kalshi price get a recorded prediction",
        f"""
        SELECT count(*) FROM gold.prediction p
        JOIN gold.game_feature f ON f.game_instance_key = p.game_instance_key
        JOIN core.game g ON g.id = f.game_id
        WHERE p.model_version = '{model_version}'
        """,
        """
        SELECT count(*)
        FROM core.market m
        JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
        WHERE m.source = 'kalshi'
            AND m.implied_probability IS NOT NULL
            AND g.game_pk IS NOT NULL
        """,
        tolerance=0,
    )


def _upcoming_source_coverage_check(source: str, model_version: str) -> Check:
    """Fail only when snapshots exist and upcoming games exist but none of
    those games have a live market prediction. Missing raw tables are a
    skip — connectors may not have been bootstrapped in this database."""
    label = f"upcoming games with {source} snapshots get a live {model_version} prediction"
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT count(*) FROM gold.game_feature
                    WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL
                    """
                )
                (upcoming,) = fetch_one(cur)
                cur.execute("SELECT count(*) FROM raw.mlb_schedule")
                (schedule_rows,) = fetch_one(cur)
                if source == "polymarket":
                    cur.execute("SELECT count(*) FROM raw.polymarket_snapshot")
                else:
                    cur.execute("SELECT count(*) FROM raw.kalshi_snapshot")
                (snapshots,) = fetch_one(cur)
                cur.execute(
                    """
                    SELECT count(DISTINCT f.mlb_game_pk)
                    FROM gold.game_feature f
                    JOIN gold.prediction p
                        ON p.mlb_game_pk = f.mlb_game_pk
                        AND p.model_version = %s
                    WHERE f.home_win IS NULL
                    """,
                    (model_version,),
                )
                (predicted,) = fetch_one(cur)
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(label, True, "raw market/schedule tables absent — skipped")
    if upcoming == 0 or schedule_rows == 0 or snapshots == 0:
        return Check(
            label,
            True,
            f"{predicted} live predictions "
            f"(upcoming={upcoming}, schedule={schedule_rows}, snapshots={snapshots})",
        )
    if predicted == 0:
        return Check(
            label,
            False,
            f"0 {model_version} predictions for {upcoming} upcoming games "
            f"despite {snapshots} {source} snapshots",
        )
    return Check(label, True, f"{predicted} of {upcoming} upcoming games have {model_version}")


def health_check() -> list[Check]:
    return [
        _polymarket_coverage_check(),
        _kalshi_coverage_check(),
        _upcoming_source_coverage_check("polymarket", MODEL_VERSIONS["polymarket"]),
        _upcoming_source_coverage_check("kalshi", MODEL_VERSIONS["kalshi"]),
    ]
