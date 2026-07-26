"""Lands MLB's own Stats API (statsapi.mlb.com) into raw.mlb_schedule,
raw.mlb_standing, and raw.mlb_live_game, via the `statsapi` package
(github.com/toddrob99/MLB-StatsAPI — 830+ stars, actively maintained,
already a pinned dependency in pyproject.toml).

Full history, not just the current season (see docs/DECISIONS.md ADR-014
for the superseded current-season-only design and ADR-015 for why it
changed): storage is cheap, and even where this duplicates Retrosheet's
own historical schedule/gamelog products, having a second independently-
sourced copy is a genuine cross-validation asset, not wasted effort.

- **Schedule** (raw.mlb_schedule): every season from 1901 (confirmed via
  direct testing — 1900 and earlier return 0 games; MLB's "modern era"
  sportId=1 coverage starts there) through the present, including live
  status values (Scheduled/Postponed/Cancelled/Completed Early/Live) that
  don't exist in Retrosheet's completed-game-only products at all.
- **Standings** (raw.mlb_standing): every season from 1969 on. Confirmed via
  direct testing that statsapi's standings_data() raises KeyError('division')
  for any season before 1969 — real divisions didn't exist before then (MLB
  split into East/West divisions starting in 1969), so the API/library has
  no representation for a non-divisional standings table. Not a gap in this
  project's overall data: pre-1969 team win-loss records are already fully
  covered by raw.lahman_teams and raw.retrosheet_gamelog.
- **Live game state** (raw.mlb_live_game): append-only snapshots (score,
  inning, balls/strikes/outs, current batter/pitcher), one row per capture,
  for whatever games the API itself reports as currently `Live`
  (gameData.status.abstractGameState) — this is the piece that actually
  supports real-time odds: everything else in this pipeline only has
  completed-game data. Loaded via append_dataframe (never replaced/deleted)
  since every snapshot stays meaningful, unlike schedule/standings' "this
  chunk replaces that chunk" shape.

bootstrap() loads full history for schedule/standings, one season at a time
(scope_column="_season", same pattern as retrosheet.py), committing after
each season so a failure partway through ~125 years doesn't lose already-
loaded ones. Unlike retrosheet.py, a single bad season here doesn't abort
the run: caught, logged, and skipped, matching retrosheet.py's "missing
year returns empty without erroring" resilience — the volume here (100+
sequential API calls) makes hitting at least one transient issue over a
full bootstrap more likely than any single connector call elsewhere in
this project.

update() reloads just the current season's schedule/standings (same
season-scoped replace, so re-running is idempotent) and calls
capture_live() to append any currently-live games' state. Getting genuinely
real-time data requires update() to actually be called repeatedly (cron,
systemd timer, etc.) — that scheduling mechanism is still an open decision
(see docs/ARCHITECTURE.md "Explicitly not designed yet"), not something
this connector invents on its own.

Retry-with-backoff (net.call_with_retry) wraps every statsapi.schedule()/
standings_data() call — added after, not before, a real failure: the first
full historical bootstrap hit `503 Server Error: first byte timeout` from
statsapi.mlb.com on 5 of 126 seasons (2019, 2021-2024), silently skipped by
the per-season try/except below before retry existed. Exactly the pattern
ADR-007 said to wait for before adding retry logic, and exactly what
happened on the very first real run. The per-season try/except stays as a
second layer: if a season still fails after retries are exhausted, skip and
log rather than lose the rest of the bootstrap.
"""

import json
from datetime import date

import pandas as pd
import psycopg
import statsapi

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_exists, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import append_dataframe, load_dataframe
from mlb_baseball.net import call_with_retry

SOURCE = "mlb_api"
FIRST_SCHEDULE_YEAR = 1901
FIRST_STANDINGS_YEAR = 1969


def _schedule_df(season: int) -> pd.DataFrame:
    games = call_with_retry(statsapi.schedule, season=season, sportId=1)
    for game in games:
        # statsapi's own schedule() emits "losing_Team" (capital T) instead of
        # "losing_team" specifically for tied Spring Training/Exhibition games
        # (confirmed: 22/2946 games in a real 2026 pull, all game_type S/E,
        # winning_team == "Tie", never both keys present on the same game).
        # load.py's column-name sanitizing lowercases both to the same
        # Postgres column, which would otherwise be a DuplicateColumn error
        # on CREATE TABLE — coalesce here instead of letting that happen.
        if "losing_Team" in game:
            game["losing_team"] = game.pop("losing_Team")
        # national_broadcasts is a list — raw columns are text, so serialize
        # rather than let pandas fall back to Python's str() repr of the list.
        game["national_broadcasts"] = json.dumps(game.get("national_broadcasts") or [])
    df = pd.DataFrame(games)
    df["_season"] = str(season)
    return df


def _standings_df(season: int) -> pd.DataFrame:
    divisions = call_with_retry(statsapi.standings_data, season=season)
    rows = []
    for division_id, division in divisions.items():
        for team in division["teams"]:
            rows.append({"division_id": division_id, "div_name": division["div_name"], **team})
    df = pd.DataFrame(rows)
    df["_season"] = str(season)
    return df


def _load_schedule(conn: psycopg.Connection, season: int) -> int:
    df = _schedule_df(season)
    if df.empty:
        return 0
    return load_dataframe(
        conn, "raw.mlb_schedule", df, scope_column="_season", scope_value=str(season)
    )


def _load_standings(conn: psycopg.Connection, season: int) -> int:
    df = _standings_df(season)
    if df.empty:
        return 0
    return load_dataframe(
        conn, "raw.mlb_standing", df, scope_column="_season", scope_value=str(season)
    )


def bootstrap() -> dict[str, int]:
    counts: dict[str, int] = {"raw.mlb_schedule": 0, "raw.mlb_standing": 0}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for season in range(FIRST_SCHEDULE_YEAR, date.today().year + 1):
            try:
                counts["raw.mlb_schedule"] += _load_schedule(conn, season)
                if season >= FIRST_STANDINGS_YEAR:
                    counts["raw.mlb_standing"] += _load_standings(conn, season)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"mlb_api: season {season} failed ({exc}); skipping, continuing bootstrap")
        result["rows"] = sum(counts.values())
    return counts


LIVE_GAME_COLUMNS = [
    "game_pk",
    "game_date",
    "away_name",
    "home_name",
    "detailed_state",
    "current_inning",
    "inning_state",
    "away_runs",
    "away_hits",
    "away_errors",
    "home_runs",
    "home_hits",
    "home_errors",
    "balls",
    "strikes",
    "outs",
    "batter_id",
    "batter_name",
    "pitcher_id",
    "pitcher_name",
]


def _live_snapshot(game_pk: int) -> dict | None:
    data = call_with_retry(statsapi.get, "game", {"gamePk": game_pk})
    status = data["gameData"]["status"]
    if status.get("abstractGameState") != "Live":
        return None
    linescore = data["liveData"]["linescore"]
    teams = linescore.get("teams", {})
    offense = linescore.get("offense", {})
    defense = linescore.get("defense", {})
    return {
        "game_pk": game_pk,
        "game_date": data["gameData"]["datetime"].get("officialDate"),
        "away_name": data["gameData"]["teams"]["away"]["name"],
        "home_name": data["gameData"]["teams"]["home"]["name"],
        "detailed_state": status.get("detailedState"),
        "current_inning": linescore.get("currentInning"),
        "inning_state": linescore.get("inningState"),
        "away_runs": teams.get("away", {}).get("runs"),
        "away_hits": teams.get("away", {}).get("hits"),
        "away_errors": teams.get("away", {}).get("errors"),
        "home_runs": teams.get("home", {}).get("runs"),
        "home_hits": teams.get("home", {}).get("hits"),
        "home_errors": teams.get("home", {}).get("errors"),
        "balls": linescore.get("balls"),
        "strikes": linescore.get("strikes"),
        "outs": linescore.get("outs"),
        "batter_id": offense.get("batter", {}).get("id"),
        "batter_name": offense.get("batter", {}).get("fullName"),
        "pitcher_id": defense.get("pitcher", {}).get("id"),
        "pitcher_name": defense.get("pitcher", {}).get("fullName"),
    }


def capture_live(conn: psycopg.Connection) -> int:
    # Always ensures raw.mlb_live_game exists, even with 0 rows to insert
    # today (pd.DataFrame(rows, columns=LIVE_GAME_COLUMNS) keeps the fixed
    # column set regardless of whether `rows` is empty) — otherwise the
    # table's very existence would depend on the coincidence of update()
    # happening to run while a game is live, and check_table_exists would
    # report a false "never bootstrapped?" on every ordinary no-game-live
    # day. Found via a real doctor run: exactly this happened after the
    # first production update() call landed on a day with no live games.
    today = date.today().strftime("%m/%d/%Y")
    games = call_with_retry(statsapi.schedule, date=today, sportId=1)
    snapshots = [_live_snapshot(game["game_id"]) for game in games]
    rows = [s for s in snapshots if s is not None]
    df = pd.DataFrame(rows, columns=LIVE_GAME_COLUMNS)
    return append_dataframe(conn, "raw.mlb_live_game", df)


def update() -> dict[str, int]:
    season = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        standings_count = _load_standings(conn, season) if season >= FIRST_STANDINGS_YEAR else 0
        counts = {
            "raw.mlb_schedule": _load_schedule(conn, season),
            "raw.mlb_standing": standings_count,
        }
        counts["raw.mlb_live_game"] = capture_live(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.mlb_schedule"),
        check_table_has_rows("raw.mlb_standing"),
        check_table_exists("raw.mlb_live_game"),
        check_last_run(SOURCE),
    ]
