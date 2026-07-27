"""Lands MLB's own Stats API (statsapi.mlb.com) into raw.mlb_schedule,
raw.mlb_standing, raw.mlb_roster, raw.mlb_transaction, raw.mlb_playbyplay,
and raw.mlb_live_game, via the `statsapi` package
(github.com/toddrob99/MLB-StatsAPI — 830+ stars, actively maintained,
already a pinned dependency in pyproject.toml).

Full history where it's cheap, current-season-forward where the source is
per-game and expensive (see docs/DECISIONS.md ADR-014/015/017): storage is
cheap, and even where this duplicates Retrosheet's own historical products,
having a second independently-sourced copy is a genuine cross-validation
asset, not wasted effort. Verified directly (not assumed) against a real
shared game (2025-03-18, Dodgers @ Cubs, Tokyo Dome): same final score
(4-1), same batter/pitcher sequence and play outcomes in matching order
across both sources — see ADR-017.

- **Schedule** (raw.mlb_schedule): every season from 1901 (confirmed via
  direct testing — 1900 and earlier return 0 games) through the present,
  including live status values Retrosheet's completed-game-only products
  don't have at all.
- **Standings** (raw.mlb_standing): every season from 1969 on (divisions
  didn't exist before then — confirmed via direct testing, not a library
  bug to work around). Pre-1969 records already covered by raw.lahman_teams
  and raw.retrosheet_gamelog.
- **Rosters** (raw.mlb_roster): every season from 1901 on, all teams that
  existed that season (team list itself pulled per-season since expansion/
  relocation changes it — confirmed 26 teams in 1990 vs 30 today). Cheap
  (~30 calls/season) so done in full, same reasoning as schedule/standings.
- **Transactions** (raw.mlb_transaction): every season from 2000 on
  (confirmed via direct testing: seasons before ~2000 return 0 rows).
  A genuine gap-fill, not duplication: raw.retrosheet_transaction is frozen
  as of November 26, 2021 (see its own module docstring) — this is the only
  source in the pipeline with current transaction data.
- **Play-by-play** (raw.mlb_playbyplay): one row per plate appearance,
  matching Retrosheet's own grain — but only from 2026 on (FIRST_PLAYBYPLAY_
  YEAR), Retrosheet's most recent published season (verified directly:
  raw.retrosheet_gameinfo tops out at 2025, nothing for 2026 at all).
  Pulling this for 2025-and-earlier would be pure duplication of what
  Retrosheet already has, at real per-game API cost (this endpoint is
  one call per game, not one call per season like schedule/standings).
  Pitch-level physics (velocity/spin/location) deliberately excluded here
  even though MLB's own game feed has it since 2008 — that's a strictly
  worse copy of what Statcast (see statcast.py, pybaseball) already
  provides with far more detail (119 columns vs. ~20) and a cheaper fetch
  pattern (date-range batches vs. one call per game) — see ADR-017.
- **Live game state** (raw.mlb_live_game): append-only snapshots (score,
  inning, balls/strikes/outs, current batter/pitcher), one row per capture,
  for whatever games the API itself reports as currently `Live`
  (gameData.status.abstractGameState). Loaded via append_dataframe (never
  replaced/deleted) since every snapshot stays meaningful.

bootstrap() loads full history for schedule/standings/rosters/transactions
(each per-season, scope_column="_season"), committing after each season so
a failure partway through ~125 years doesn't lose already-loaded ones.
Play-by-play bootstrap only runs for FIRST_PLAYBYPLAY_YEAR+ and commits per
game (not per season) given its much higher per-season call volume and
correspondingly higher chance of a single game failing partway through.
A single bad season (or game, for play-by-play) doesn't abort the run:
caught, logged, and skipped, matching retrosheet.py's "missing year returns
empty without erroring" resilience.

update() reloads the current season's schedule/standings/roster/
transactions (season-scoped replace, idempotent), refreshes play-by-play
for today's started-or-finished games (game_pk-scoped replace — an
in-progress game's plays keep growing across update() calls), and calls
capture_live() to append current live-game snapshots. Getting genuinely
real-time data requires update() to actually be called repeatedly — see
scripts/mlb_api_update.sh and ADR-016.

Retry-with-backoff (net.call_with_retry) wraps every statsapi call — added
after, not before, a real failure: the first full historical bootstrap hit
`503 Server Error: first byte timeout` from statsapi.mlb.com on 5 of 126
seasons. The per-season/per-game try/except stays as a second layer: if a
call still fails after retries are exhausted, skip and log rather than lose
the rest of the bootstrap.

The `transactions` endpoint is called with force=True: statsapi's own
required-parameter validation has a real bug (it accumulates missing
params across every alternative parameter set instead of resetting between
them), so a startDate/endDate query — a documented valid combination per
the endpoint's own required_params — is incorrectly rejected without
force=True. Confirmed by reading the library's source, not guessed.
"""

import json
from datetime import date

import pandas as pd
import psycopg
import statsapi

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_recent_run, check_table_exists, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import append_dataframe, load_dataframe, season_already_loaded
from mlb_baseball.net import call_with_retry

SOURCE = "mlb_api"
FIRST_SCHEDULE_YEAR = 1901
FIRST_STANDINGS_YEAR = 1969
FIRST_ROSTER_YEAR = FIRST_SCHEDULE_YEAR
FIRST_TRANSACTION_YEAR = 2000
# Retrosheet's most recently published season (verified: raw.retrosheet_gameinfo
# tops out at 2025) — MLB API's play-by-play starts exactly where that stops,
# not earlier, to avoid a per-game-cost duplicate of already-authoritative data.
FIRST_PLAYBYPLAY_YEAR = 2026
# Game statuses meaning "hasn't actually started" — anything else is worth a
# play-by-play fetch (an exclude-list, not an include-list, since the exact
# in-progress status string wasn't directly observable while building this —
# no game was live during testing — safer to fetch and get an empty/partial
# result than to silently skip a real status string variant).
NOT_YET_PLAYED_STATUSES = {"Scheduled", "Pre-Game", "Warmup", "Postponed", "Cancelled"}
# scripts/mlb_api_update.sh runs `mlb ingest mlb_api --mode update` every 5
# minutes via cron (see docs/DECISIONS.md ADR-016) — 3x that cadence gives
# room for one slow/retried run without doctor falsely flagging staleness.
FRESHNESS_THRESHOLD_MINUTES = 15


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


ROSTER_COLUMNS = [
    "team_id",
    "person_id",
    "person_name",
    "jersey_number",
    "position_code",
    "position_name",
    "position_type",
    "status_code",
    "status_description",
]


def _season_team_ids(season: int) -> list[int]:
    teams = call_with_retry(statsapi.get, "teams", {"sportId": 1, "season": season}, force=True)
    return [t["id"] for t in teams.get("teams", [])]


def _roster_df(season: int) -> pd.DataFrame:
    rows = []
    for team_id in _season_team_ids(season):
        data = call_with_retry(statsapi.get, "team_roster", {"teamId": team_id, "season": season})
        for entry in data.get("roster", []):
            person = entry.get("person", {})
            position = entry.get("position", {})
            status = entry.get("status", {})
            rows.append(
                {
                    "team_id": team_id,
                    "person_id": person.get("id"),
                    "person_name": person.get("fullName"),
                    "jersey_number": entry.get("jerseyNumber"),
                    "position_code": position.get("code"),
                    "position_name": position.get("name"),
                    "position_type": position.get("type"),
                    "status_code": status.get("code"),
                    "status_description": status.get("description"),
                }
            )
    df = pd.DataFrame(rows, columns=ROSTER_COLUMNS)
    df["_season"] = str(season)
    return df


def _load_roster(conn: psycopg.Connection, season: int) -> int:
    df = _roster_df(season)
    if df.empty:
        return 0
    return load_dataframe(
        conn, "raw.mlb_roster", df, scope_column="_season", scope_value=str(season)
    )


TRANSACTION_COLUMNS = [
    "transaction_id",
    "person_id",
    "person_name",
    "from_team_id",
    "from_team_name",
    "to_team_id",
    "to_team_name",
    "date",
    "effective_date",
    "resolution_date",
    "type_code",
    "type_desc",
    "description",
]


def _transactions_df(season: int) -> pd.DataFrame:
    data = call_with_retry(
        statsapi.get,
        "transactions",
        {"startDate": f"01/01/{season}", "endDate": f"12/31/{season}"},
        force=True,  # see module docstring — statsapi's own param validation has a bug
    )
    rows = []
    for tx in data.get("transactions", []):
        person = tx.get("person", {})
        from_team = tx.get("fromTeam", {})
        to_team = tx.get("toTeam", {})
        rows.append(
            {
                "transaction_id": tx.get("id"),
                "person_id": person.get("id"),
                "person_name": person.get("fullName"),
                "from_team_id": from_team.get("id"),
                "from_team_name": from_team.get("name"),
                "to_team_id": to_team.get("id"),
                "to_team_name": to_team.get("name"),
                "date": tx.get("date"),
                "effective_date": tx.get("effectiveDate"),
                "resolution_date": tx.get("resolutionDate"),
                "type_code": tx.get("typeCode"),
                "type_desc": tx.get("typeDesc"),
                "description": tx.get("description"),
            }
        )
    df = pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)
    df["_season"] = str(season)
    return df


def _load_transactions(conn: psycopg.Connection, season: int) -> int:
    df = _transactions_df(season)
    if df.empty:
        return 0
    return load_dataframe(
        conn, "raw.mlb_transaction", df, scope_column="_season", scope_value=str(season)
    )


PLAYBYPLAY_COLUMNS = [
    "game_pk",
    "at_bat_index",
    "inning",
    "half_inning",
    "batter_id",
    "batter_name",
    "bat_side",
    "pitcher_id",
    "pitcher_name",
    "pitch_hand",
    "event",
    "event_type",
    "description",
    "rbi",
    "away_score",
    "home_score",
    "balls",
    "strikes",
    "outs",
]


def _playbyplay_df(game_pk: int) -> pd.DataFrame:
    data = call_with_retry(statsapi.get, "game_playByPlay", {"gamePk": game_pk})
    rows = []
    for play in data.get("allPlays", []):
        matchup = play.get("matchup", {})
        result = play.get("result", {})
        about = play.get("about", {})
        count = play.get("count", {})
        rows.append(
            {
                "game_pk": game_pk,
                "at_bat_index": play.get("atBatIndex"),
                "inning": about.get("inning"),
                "half_inning": about.get("halfInning"),
                "batter_id": matchup.get("batter", {}).get("id"),
                "batter_name": matchup.get("batter", {}).get("fullName"),
                "bat_side": matchup.get("batSide", {}).get("code"),
                "pitcher_id": matchup.get("pitcher", {}).get("id"),
                "pitcher_name": matchup.get("pitcher", {}).get("fullName"),
                "pitch_hand": matchup.get("pitchHand", {}).get("code"),
                "event": result.get("event"),
                "event_type": result.get("eventType"),
                "description": result.get("description"),
                "rbi": result.get("rbi"),
                "away_score": result.get("awayScore"),
                "home_score": result.get("homeScore"),
                "balls": count.get("balls"),
                "strikes": count.get("strikes"),
                "outs": count.get("outs"),
            }
        )
    return pd.DataFrame(rows, columns=PLAYBYPLAY_COLUMNS)


def _load_playbyplay_for_game(conn: psycopg.Connection, game_pk: int, season: int) -> int:
    df = _playbyplay_df(game_pk)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_playbyplay", df, scope_column="game_pk", scope_value=str(game_pk)
    )


def _started_game_ids(games: list[dict]) -> list[int]:
    return [g["game_id"] for g in games if g.get("status") not in NOT_YET_PLAYED_STATUSES]


def _load_playbyplay_for_season(conn: psycopg.Connection, season: int) -> int:
    games = call_with_retry(statsapi.schedule, season=season, sportId=1)
    total = 0
    for game_pk in _started_game_ids(games):
        try:
            total += _load_playbyplay_for_game(conn, game_pk, season)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: play-by-play for game {game_pk} failed ({exc}); skipping")
    return total


def _load_playbyplay_for_today(conn: psycopg.Connection) -> int:
    today = date.today().strftime("%m/%d/%Y")
    games = call_with_retry(statsapi.schedule, date=today, sportId=1)
    season = date.today().year
    total = 0
    for game_pk in _started_game_ids(games):
        try:
            total += _load_playbyplay_for_game(conn, game_pk, season)
        except Exception as exc:
            print(f"mlb_api: play-by-play for game {game_pk} failed ({exc}); skipping")
    return total


def bootstrap() -> dict[str, int]:
    counts: dict[str, int] = {
        "raw.mlb_schedule": 0,
        "raw.mlb_standing": 0,
        "raw.mlb_roster": 0,
        "raw.mlb_transaction": 0,
        "raw.mlb_playbyplay": 0,
    }
    current_year = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for season in range(FIRST_SCHEDULE_YEAR, current_year + 1):
            # A past season's schedule/standings/roster/transactions are
            # published and complete — they never change, so re-fetching on
            # every bootstrap re-run is pure waste (each season costs real
            # API calls and wall-clock time). raw.mlb_schedule is checked as
            # the single completeness proxy for the whole season, matching
            # the granularity this loop already fails at (one try/except per
            # season, not per table) — only the current season, still in
            # progress, always gets re-fetched.
            if season < current_year and season_already_loaded(conn, "raw.mlb_schedule", season):
                print(f"mlb_api: {season} schedule/standings/roster/transactions loaded, skipping")
            else:
                try:
                    counts["raw.mlb_schedule"] += _load_schedule(conn, season)
                    if season >= FIRST_STANDINGS_YEAR:
                        counts["raw.mlb_standing"] += _load_standings(conn, season)
                    if season >= FIRST_ROSTER_YEAR:
                        counts["raw.mlb_roster"] += _load_roster(conn, season)
                    if season >= FIRST_TRANSACTION_YEAR:
                        counts["raw.mlb_transaction"] += _load_transactions(conn, season)
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    print(
                        f"mlb_api: season {season} failed ({exc}); skipping, continuing bootstrap"
                    )
            if season >= FIRST_PLAYBYPLAY_YEAR:
                if season < current_year and season_already_loaded(
                    conn, "raw.mlb_playbyplay", season
                ):
                    print(f"mlb_api: {season} play-by-play already loaded, skipping")
                    continue
                # Own per-game commits inside — far higher call volume than
                # the rest of this loop, so it needs finer-grained resilience
                # than the single per-season try/except above.
                counts["raw.mlb_playbyplay"] += _load_playbyplay_for_season(conn, season)
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
        counts = {
            "raw.mlb_schedule": _load_schedule(conn, season),
            "raw.mlb_standing": _load_standings(conn, season)
            if season >= FIRST_STANDINGS_YEAR
            else 0,
            "raw.mlb_roster": _load_roster(conn, season),
            "raw.mlb_transaction": _load_transactions(conn, season),
            "raw.mlb_playbyplay": _load_playbyplay_for_today(conn),
        }
        counts["raw.mlb_live_game"] = capture_live(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.mlb_schedule"),
        check_table_has_rows("raw.mlb_standing"),
        check_table_has_rows("raw.mlb_roster"),
        check_table_has_rows("raw.mlb_transaction"),
        check_table_exists("raw.mlb_playbyplay"),
        check_table_exists("raw.mlb_live_game"),
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES),
    ]
