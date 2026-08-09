"""Lands MLB's own Stats API (statsapi.mlb.com) into raw.mlb_schedule,
raw.mlb_standing, raw.mlb_roster, raw.mlb_transaction, raw.mlb_playbyplay,
raw.mlb_live_game, raw.mlb_venue, raw.mlb_team_history, raw.mlb_person,
raw.mlb_draft, raw.mlb_boxscore_batting/pitching/fielding, raw.mlb_umpire,
raw.mlb_win_prob, and raw.mlb_probable, via the `statsapi` package
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
- **Venues** (raw.mlb_venue): every ballpark the API knows about (~1,667),
  full reload each run — reference data, not per-season.
- **Team history** (raw.mlb_team_history): one row per team per
  configuration-change (name/venue/franchise), not one row per season —
  confirmed directly (Yankees/team_id 147 returns 5 rows spanning 1903-2009,
  not 123). Team IDs sourced from raw.mlb_roster's own distinct team_id
  column (not just the current season's 30 teams) so long-defunct
  early-1900s franchises aren't missed.
- **Person bios** (raw.mlb_person): name/DOB/bats-throws/debut-date for
  every person_id ever seen in raw.mlb_roster (~20k) — the API has no bulk
  "every player ever" endpoint, so rosters (1901+, already loaded) stands in
  as the complete ID list. Full reload each run.
- **Draft** (raw.mlb_draft): every pick, 1965 (MLB's first amateur draft,
  confirmed: 1964 returns 0 rounds) through present.
- **Box scores** (raw.mlb_boxscore_batting/pitching/fielding): one row per
  player per game per stat category, FIRST_PLAYBYPLAY_YEAR+ only (same
  duplication-avoidance reasoning as play-by-play below — Retrosheet already
  covers box scores for its own published years).
- **Umpires** (raw.mlb_umpire): per-game plate/base assignments, pulled from
  the same game_boxscore response's `officials` array (not from the
  jobs_umpire_games/jobs_officialScorers endpoints — confirmed those are
  per-umpire career directories, not per-game assignment lookups, the wrong
  shape for this). Continues Retrosheet's own umpire data past its freeze.
- **Win probability, line score, and game context** (raw.mlb_win_prob,
  raw.mlb_linescore, raw.mlb_game_context): win_prob is one row per at-bat
  (joins to raw.mlb_playbyplay on game_pk + at_bat_index); linescore is one
  row per inning per side; game_context is one row per game (pregame win
  probability plus positional sacrifice-fly probability — distinct from
  win_prob's per-at-bat values). All three run FIRST_WIN_PROB_YEAR (1950)
  through present — a much wider range than play-by-play/box-score/umpire,
  which stay at FIRST_PLAYBYPLAY_YEAR (2026), because none of the three has
  a Retrosheet equivalent at all (win_prob/game_context are derived
  analytics, not raw play/box records; linescore is a convenience summary).
  The 1950 boundary itself was confirmed directly (not assumed to extend
  indefinitely): gamePk-based game_winProbability/game_playByPlay/
  game_boxscore all return real, populated data for a 1950 game, but
  404/empty for 1949 and every year checked back to 1901.
  `jobs_umpire_games` (per-umpire career game log, which would extend
  umpire coverage into this range using the person_ids we already have from
  raw.mlb_umpire) was evaluated but confirmed to return 401 Unauthorized
  regardless of parameters — an MLB-internal endpoint, not built.
- **Probable pitchers** (raw.mlb_probable): one append-only snapshot row
  per (game_pk, side) every time `update()` observes a *change* from the
  last known snapshot (a new announcement or a scratch) — not one row
  per poll. Fetched via `schedule`'s own `hydrate=probablePitcher` param
  (verified directly against real 2026 data, not assumed: the schedule
  endpoint's `teams.<side>.probablePitcher` object carries `id`/`fullName`,
  unlike `statsapi.schedule()`'s own convenience wrapper, which already
  hydrates probables into raw.mlb_schedule's `home_probable_pitcher`/
  `away_probable_pitcher` columns but only as a bare name string — no
  person_id, and season-scoped replace loses any scratch history). Closes
  ADR-034/046's biggest remaining gap: without a person_id to resolve
  against `core.player.mlbam_id`, `mlb_baseball/model/starter.py` had no
  way to look ahead to a game that hasn't been played yet. Confirmed
  directly that real announcements are almost always only 1-2 days out
  (15/15 real games covered for today and tomorrow in a direct check,
  dropping to near-zero three-plus days out) — `PROBABLE_WINDOW_DAYS`
  is wider than that observed pattern anyway, since the whole window is
  one `schedule` call regardless of span, not one call per day.

Deliberately not built: `person_stats` (redundant with game_boxscore, which
already returns every player's per-game line in one call instead of one call
per player), `jobs_umpire_games` (confirmed 401 Unauthorized — MLB-internal,
not accessible regardless of parameters), `stats_streaks`/`highLow`
(confirmed broken/inaccessible via the generic statsapi.get() interface —
same class as FanGraphs), per-award recipient history (Lahman already has
it), `homeRunDerby`/All-Star voting endpoints (low-value event ephemera,
`homeRunDerby` also needs a Derby-specific gamePk not discoverable from
raw.mlb_schedule), and the cosmetic/operational family — `game_color`
(confirmed dead, 404), `team_uniforms`/`game_uniforms` (checked directly:
merchandise metadata, not analytical data), `game_content` (checked
directly: editorial/media CMS content, not stats), `meta` (checked
directly: returns a bare list — the API's own parameter documentation, not
baseball data), `game_changes`/`people_changes` (an operational sync feed,
not a stable fact), and generic `jobs` (confirmed to return the same roster
as the dedicated jobs_umpires/jobs_officialScorers endpoints — a
parameterized alias, not new data). `jobs_officialScorers`/`jobs_datacasters`
ARE built (raw.mlb_official_scorer/raw.mlb_datacaster) — it's
`jobs_umpire_games` specifically that's inaccessible, not the whole
`jobs_*` family.

bootstrap() loads full history for schedule/standings/rosters/transactions
(each per-season, scope_column="_season"), committing after each season so
a failure partway through ~125 years doesn't lose already-loaded ones.
Venue/team-history/person/draft each load once as their own step. Game
detail (play-by-play + box score + umpires + win probability) only runs for
FIRST_PLAYBYPLAY_YEAR+ and commits per game (not per season) given its much
higher per-season call volume and correspondingly higher chance of a single
game failing partway through. A single bad season/game/step doesn't abort
the run: caught, logged, and skipped, matching retrosheet.py's "missing year
returns empty without erroring" resilience.

update() reloads the current season's schedule/standings/roster/
transactions/draft (season-scoped replace, idempotent), refreshes game
detail for today's started-or-finished games (game_pk-scoped replace — an
in-progress game's plays keep growing across update() calls), and calls
capture_live() to append current live-game snapshots. Venue/team-history/
person are NOT refreshed every update() — they're reference/roster-derived
data that changes rarely relative to a 5-minute cadence, not worth ~1,800
extra API calls every tick; they're refreshed on the next bootstrap re-run
instead (a documented, deliberate staleness tradeoff, not an oversight).
Getting genuinely real-time data requires update() to actually be called
repeatedly — see scripts/mlb_api_update.sh and ADR-016.

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

import concurrent.futures
import gzip
import hashlib
import json
import re
import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import psycopg
import requests
import statsapi

from mlb_baseball import manifest
from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import (
    Check,
    check_partition_coverage,
    check_recent_run,
    check_table_exists,
    check_table_has_rows,
)
from mlb_baseball.ingest import record_items, track_run
from mlb_baseball.load import (
    append_dataframe,
    load_dataframe,
    replace_dataframe_scopes,
    season_already_loaded,
)
from mlb_baseball.net import call_with_retry

SOURCE = "mlb_api"
# statsapi.get()'s underlying requests.get() call has no timeout unless
# passed one explicitly via request_kwargs -- found the hard way: a single
# unresponsive response from statsapi.mlb.com hung the whole bootstrap
# indefinitely, since call_with_retry's retry-on-exception logic never
# even engages until something actually raises. _get() below is a thin
# wrapper used everywhere in place of statsapi.get so every call site gets
# this for free; a hang now surfaces as requests.exceptions.Timeout, which
# call_with_retry already retries correctly.
REQUEST_TIMEOUT_SECONDS = 30
# Historical analytics responses are compact and normally return in well
# under a second.  Giving one wedged response the generic 30-second timeout
# stalls an entire bounded batch, so this hot path fails fast and retries
# independently.  The broader connector retains its more conservative limit.
# The live benchmark's slowest successful response was under four seconds.
# Five seconds leaves ordinary tail latency room while keeping one wedged
# socket from stalling an otherwise complete 200-game batch for ten seconds.
ANALYTICS_REQUEST_TIMEOUT_SECONDS = 5
ANALYTICS_RETRY_ATTEMPTS = 3
ANALYTICS_BACKOFF_SECONDS = 1.0


def _get(endpoint: str, params: dict | None = None, force: bool = False):
    return statsapi.get(
        endpoint, params or {}, force=force, request_kwargs={"timeout": REQUEST_TIMEOUT_SECONDS}
    )


FIRST_SCHEDULE_YEAR = 1901
FIRST_STANDINGS_YEAR = 1969
FIRST_ROSTER_YEAR = FIRST_SCHEDULE_YEAR
FIRST_TRANSACTION_YEAR = 2000
# Retrosheet's most recently published season (verified: raw.retrosheet_gameinfo
# tops out at 2025) — MLB API's play-by-play/box-score/umpire data starts
# exactly where that stops, not earlier, to avoid a per-game-cost duplicate
# of already-authoritative data.
FIRST_PLAYBYPLAY_YEAR = 2026
# Win probability has no Retrosheet equivalent at all (a derived win-
# expectancy model, not a raw play/box record) — pulled back much further
# than play-by-play/box-score/umpire, which stay at FIRST_PLAYBYPLAY_YEAR
# since Retrosheet already covers those. The real boundary was confirmed
# directly, not assumed: gamePk-based game_winProbability/game_playByPlay
# return real, populated data for a 1950 game, but 404/empty for 1949 and
# every year checked back to 1901 (1940, 1945-1949 all empty; 1950, 1955,
# 1957, 1960 all populated) — MLB's game feed data simply doesn't exist
# before the 1950 season.
FIRST_WIN_PROB_YEAR = 1950
# The win-probability endpoint otherwise returns every pitch event, runner,
# and context object for every plate appearance. We only land these seven
# fields, so request them explicitly. A real 1967 game fell from 313,579 to
# 13,667 bytes (96% smaller) with the identical 70 output rows.
WIN_PROB_FIELDS = (
    "atBatIndex,about,inning,halfInning,homeTeamWinProbability,"
    "awayTeamWinProbability,homeTeamWinProbabilityAdded"
)
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
# MLB's first amateur draft (confirmed via direct testing — 1964 returns 0
# rounds, 1965 returns 72 rounds/824 picks).
FIRST_DRAFT_YEAR = 1965
# Days ahead of today to pull probable-pitcher announcements for. Confirmed
# via direct testing against real 2026 data that real announcements are
# almost always only 1-2 days out (15/15 real games covered for today and
# tomorrow, dropping to near-zero three-plus days out) — this window is
# generous relative to that, not a guess, and costs nothing extra either
# way since `schedule` takes the whole range in one call regardless of span.
PROBABLE_WINDOW_DAYS = 5
# The venue/people endpoints accept a batched, comma-separated ID list
# (confirmed via direct testing) — chunking keeps the one-time full-catalog
# pull to a couple hundred calls instead of one per venue/person.
VENUE_BATCH_SIZE = 100
PERSON_BATCH_SIZE = 200
# A 48-game live API benchmark measured 24 workers at 106.0 games/sec,
# ahead of 16 (55.8) while 32 fell back to 95.1.  Keep the bound explicit so
# an operator cannot turn a recovery job into an accidental unbounded request
# fan-out.
# A batch is deliberately modest: it bounds memory, makes failures cheap to
# retry, and turns hundreds of per-game commits into one COPY transaction.
ANALYTICS_WORKERS = 24
ANALYTICS_BATCH_SIZE = 200
ANALYTICS_PARSER_VERSION = "mlb-api-analytics-v3"
_ANALYTICS_LOCAL = threading.local()
REFERENCE_WORKERS = 8


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
    rows: list[dict] = []
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
    teams = call_with_retry(_get, "teams", {"sportId": 1, "season": season}, force=True)
    return [t["id"] for t in teams.get("teams", [])]


def _roster_df(season: int) -> pd.DataFrame:
    rows = []
    for team_id in _season_team_ids(season):
        data = call_with_retry(_get, "team_roster", {"teamId": team_id, "season": season})
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
        _get,
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


VENUE_COLUMNS = [
    "venue_id",
    "name",
    "active",
    "address1",
    "city",
    "state",
    "postal_code",
    "country",
    "latitude",
    "longitude",
    "timezone_id",
    "capacity",
    "turf_type",
    "roof_type",
    "left_line",
    "center",
    "right_line",
]


def _all_venue_ids() -> list[int]:
    data = call_with_retry(_get, "venue", {"venueIds": ""}, force=True)
    return [v["id"] for v in data.get("venues", [])]


def _venue_df() -> pd.DataFrame:
    ids = _all_venue_ids()
    rows = []
    for i in range(0, len(ids), VENUE_BATCH_SIZE):
        batch = ids[i : i + VENUE_BATCH_SIZE]
        data = call_with_retry(
            _get,
            "venue",
            {
                "venueIds": ",".join(str(v) for v in batch),
                "hydrate": "location,fieldInfo,timezone",
            },
            force=True,
        )
        for v in data.get("venues", []):
            location = v.get("location", {})
            field_info = v.get("fieldInfo", {})
            coords = location.get("defaultCoordinates", {})
            rows.append(
                {
                    "venue_id": v.get("id"),
                    "name": v.get("name"),
                    "active": v.get("active"),
                    "address1": location.get("address1"),
                    "city": location.get("city"),
                    "state": location.get("state"),
                    "postal_code": location.get("postalCode"),
                    "country": location.get("country"),
                    "latitude": coords.get("latitude"),
                    "longitude": coords.get("longitude"),
                    "timezone_id": v.get("timeZone", {}).get("id"),
                    "capacity": field_info.get("capacity"),
                    "turf_type": field_info.get("turfType"),
                    "roof_type": field_info.get("roofType"),
                    "left_line": field_info.get("leftLine"),
                    "center": field_info.get("center"),
                    "right_line": field_info.get("rightLine"),
                }
            )
    return pd.DataFrame(rows, columns=VENUE_COLUMNS)


def _load_venue(conn: psycopg.Connection) -> int:
    # Not season-scoped — a full reference-table reload each run, same
    # pattern as retrosheet_reference.py (parks/team IDs are also "whole
    # file, no natural per-year chunk").
    df = _venue_df()
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_venue", df)


TEAM_HISTORY_COLUMNS = [
    "team_id",
    "season",
    "name",
    "team_code",
    "abbreviation",
    "location_name",
    "franchise_name",
    "club_name",
    "first_year_of_play",
    "venue_id",
    "venue_name",
    "league_name",
    "active",
]


def _team_history_df(team_id: int) -> pd.DataFrame:
    # One row per configuration change (name/venue/franchise), not one row
    # per season — confirmed via direct testing on the Yankees (team_id 147):
    # 5 rows (1903 Highlanders/Hilltop Park, 1913 Polo Grounds, 1923 Yankee
    # Stadium I, 1974 Shea Stadium during renovation, 2009 new Yankee
    # Stadium), not 123. Each row's "season" is when that configuration took
    # effect, running until the next row's season (or present, for the last).
    data = call_with_retry(_get, "teams_history", {"teamIds": team_id}, force=True)
    rows = []
    for t in data.get("teams", []):
        venue = t.get("venue", {})
        league = t.get("league", {})
        rows.append(
            {
                "team_id": t.get("id"),
                "season": t.get("season"),
                "name": t.get("name"),
                "team_code": t.get("teamCode"),
                "abbreviation": t.get("abbreviation"),
                "location_name": t.get("locationName"),
                "franchise_name": t.get("franchiseName"),
                "club_name": t.get("clubName"),
                "first_year_of_play": t.get("firstYearOfPlay"),
                "venue_id": venue.get("id"),
                "venue_name": venue.get("name"),
                "league_name": league.get("name"),
                "active": t.get("active"),
            }
        )
    return pd.DataFrame(rows, columns=TEAM_HISTORY_COLUMNS)


def _distinct_roster_team_ids(conn: psycopg.Connection) -> list[int]:
    # Sourced from raw.mlb_roster (already spans 1901-present, all teams
    # each season) rather than just the current season's 30 teams — MLB
    # team_ids persist across renames/relocations (confirmed: team_id 147
    # covers the Highlanders through the current Yankees, one row per era
    # in teams_history), but a handful of long-defunct 1901-1902-era teams
    # wouldn't be in *any* current season's team list at all. Rosters, not
    # schedule, because it's the smallest table with the same coverage.
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT team_id FROM raw.mlb_roster WHERE team_id IS NOT NULL")
        return [int(row[0]) for row in cur.fetchall()]


def _load_team_history(conn: psycopg.Connection) -> int:
    total = 0
    for team_id in _distinct_roster_team_ids(conn):
        df = _team_history_df(team_id)
        if df.empty:
            continue
        total += load_dataframe(
            conn, "raw.mlb_team_history", df, scope_column="team_id", scope_value=str(team_id)
        )
    return total


PERSON_COLUMNS = [
    "person_id",
    "full_name",
    "birth_date",
    "birth_city",
    "birth_country",
    "height",
    "weight",
    "active",
    "primary_position_code",
    "primary_position_name",
    "bat_side",
    "pitch_hand",
    "mlb_debut_date",
]


def _distinct_roster_person_ids(conn: psycopg.Connection) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT person_id FROM raw.mlb_roster WHERE person_id IS NOT NULL")
        return [int(row[0]) for row in cur.fetchall()]


def _person_df(person_ids: list[int]) -> pd.DataFrame:
    rows = []
    for i in range(0, len(person_ids), PERSON_BATCH_SIZE):
        batch = person_ids[i : i + PERSON_BATCH_SIZE]
        data = call_with_retry(
            _get, "people", {"personIds": ",".join(str(p) for p in batch)}, force=True
        )
        for p in data.get("people", []):
            position = p.get("primaryPosition", {})
            rows.append(
                {
                    "person_id": p.get("id"),
                    "full_name": p.get("fullName"),
                    "birth_date": p.get("birthDate"),
                    "birth_city": p.get("birthCity"),
                    "birth_country": p.get("birthCountry"),
                    "height": p.get("height"),
                    "weight": p.get("weight"),
                    "active": p.get("active"),
                    "primary_position_code": position.get("code"),
                    "primary_position_name": position.get("name"),
                    "bat_side": p.get("batSide", {}).get("code"),
                    "pitch_hand": p.get("pitchHand", {}).get("code"),
                    "mlb_debut_date": p.get("mlbDebutDate"),
                }
            )
    return pd.DataFrame(rows, columns=PERSON_COLUMNS)


def _load_person(conn: psycopg.Connection) -> int:
    # Sourced from raw.mlb_roster's own person_id column rather than a
    # separate "list every player ever" call — the MLB Stats API has no such
    # bulk endpoint, and rosters (1901+, already loaded) is a complete proxy
    # for "everyone who's ever appeared on an MLB roster". Full reload each
    # run (not scoped) since this is reference/bio data, not per-season data.
    person_ids = _distinct_roster_person_ids(conn)
    df = _person_df(person_ids)
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_person", df)


DRAFT_COLUMNS = [
    "draft_year",
    "pick_round",
    "pick_number",
    "round_pick_number",
    "pick_value",
    "signing_bonus",
    "person_id",
    "person_name",
    "team_id",
    "team_name",
    "home_city",
    "home_state",
    "home_country",
    "school_name",
    "school_class",
    "school_city",
    "school_state",
    "school_country",
    "scouting_report",
    "blurb",
]


def _draft_df(year: int) -> pd.DataFrame:
    data = call_with_retry(_get, "draft", {"year": year}, force=True)
    rows = []
    for round_ in data.get("drafts", {}).get("rounds", []):
        for pick in round_.get("picks", []):
            person = pick.get("person", {})
            team = pick.get("team", {})
            home = pick.get("home", {})
            school = pick.get("school", {})
            rows.append(
                {
                    "draft_year": year,
                    "pick_round": pick.get("pickRound"),
                    "pick_number": pick.get("pickNumber"),
                    "round_pick_number": pick.get("roundPickNumber"),
                    "pick_value": pick.get("pickValue"),
                    "signing_bonus": pick.get("signingBonus"),
                    "person_id": person.get("id"),
                    "person_name": person.get("fullName"),
                    "team_id": team.get("id"),
                    "team_name": team.get("name"),
                    "home_city": home.get("city"),
                    "home_state": home.get("state"),
                    "home_country": home.get("country"),
                    "school_name": school.get("name"),
                    "school_class": school.get("schoolClass"),
                    "school_city": school.get("city"),
                    "school_state": school.get("state"),
                    "school_country": school.get("country"),
                    "scouting_report": pick.get("scoutingReport"),
                    "blurb": pick.get("blurb"),
                }
            )
    return pd.DataFrame(rows, columns=DRAFT_COLUMNS)


def _load_draft(conn: psycopg.Connection, year: int) -> int:
    df = _draft_df(year)
    if df.empty:
        return 0
    return load_dataframe(
        conn, "raw.mlb_draft", df, scope_column="draft_year", scope_value=str(year)
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
    "captured_at",
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
    data = call_with_retry(_get, "game_playByPlay", {"gamePk": game_pk})
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


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _camel_to_snake(name: str) -> str:
    """MLB's own boxscore/win-probability JSON keys are camelCase
    (atBatsPerHomeRun, homeTeamWinProbability); hand-listing every one of
    the ~85 batting/pitching/fielding stat fields would be pure transcription
    risk, so convert programmatically instead of squashing them through
    load.py's case-fold-only sanitizer (which would flatten atBats -> atbats,
    losing the source's own word boundary)."""
    return _CAMEL_RE.sub("_", name).lower()


def _boxscore_identity(player: dict, game_pk: int, team_id: int) -> dict:
    person = player.get("person", {})
    position = player.get("position", {})
    status = player.get("status", {})
    return {
        "game_pk": game_pk,
        "team_id": team_id,
        "person_id": person.get("id"),
        "person_name": person.get("fullName"),
        "position_code": position.get("code"),
        "position_name": position.get("name"),
        "status_code": status.get("code"),
        "jersey_number": player.get("jerseyNumber"),
        "batting_order": player.get("battingOrder"),
    }


def _boxscore_rows(data: dict, game_pk: int) -> tuple[list[dict], list[dict], list[dict]]:
    batting_rows: list[dict] = []
    pitching_rows: list[dict] = []
    fielding_rows: list[dict] = []
    for side in ("away", "home"):
        team = data.get("teams", {}).get(side, {})
        team_id = team.get("team", {}).get("id")
        for player in team.get("players", {}).values():
            identity = _boxscore_identity(player, game_pk, team_id)
            stats = player.get("stats", {})
            for category, rows in (
                ("batting", batting_rows),
                ("pitching", pitching_rows),
                ("fielding", fielding_rows),
            ):
                values = stats.get(category) or {}
                if values:
                    rows.append({**identity, **{_camel_to_snake(k): v for k, v in values.items()}})
    return batting_rows, pitching_rows, fielding_rows


def _officials_rows(data: dict, game_pk: int) -> list[dict]:
    rows = []
    for entry in data.get("officials", []):
        official = entry.get("official", {})
        rows.append(
            {
                "game_pk": game_pk,
                "person_id": official.get("id"),
                "person_name": official.get("fullName"),
                "official_type": entry.get("officialType"),
            }
        )
    return rows


def _load_boxscore_for_game(conn: psycopg.Connection, game_pk: int) -> dict[str, int]:
    data = call_with_retry(_get, "game_boxscore", {"gamePk": game_pk})
    batting_rows, pitching_rows, fielding_rows = _boxscore_rows(data, game_pk)
    counts = {}
    for table, rows in (
        ("raw.mlb_boxscore_batting", batting_rows),
        ("raw.mlb_boxscore_pitching", pitching_rows),
        ("raw.mlb_boxscore_fielding", fielding_rows),
        ("raw.mlb_umpire", _officials_rows(data, game_pk)),
    ):
        df = pd.DataFrame(rows)
        counts[table] = (
            load_dataframe(conn, table, df, scope_column="game_pk", scope_value=str(game_pk))
            if not df.empty
            else 0
        )
    return counts


def _win_prob_rows(data: list[dict], game_pk: int) -> list[dict]:
    rows = []
    for play in data:
        about = play.get("about", {})
        rows.append(
            {
                "game_pk": game_pk,
                "at_bat_index": play.get("atBatIndex"),
                "inning": about.get("inning"),
                "half_inning": about.get("halfInning"),
                "home_win_probability": play.get("homeTeamWinProbability"),
                "away_win_probability": play.get("awayTeamWinProbability"),
                "home_win_probability_added": play.get("homeTeamWinProbabilityAdded"),
            }
        )
    return rows


def _load_win_prob_for_game(conn: psycopg.Connection, game_pk: int, season: int) -> int:
    data = call_with_retry(
        _get,
        "game_winProbability",
        {"gamePk": game_pk, "fields": WIN_PROB_FIELDS},
    )
    df = pd.DataFrame(_win_prob_rows(data, game_pk))
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_win_prob", df, scope_column="game_pk", scope_value=str(game_pk)
    )


def _linescore_rows(data: dict, game_pk: int) -> list[dict]:
    rows = []
    for inning in data.get("innings", []):
        for side in ("home", "away"):
            side_data = inning.get(side, {})
            rows.append(
                {
                    "game_pk": game_pk,
                    "inning": inning.get("num"),
                    "side": side,
                    "runs": side_data.get("runs"),
                    "hits": side_data.get("hits"),
                    "errors": side_data.get("errors"),
                    "left_on_base": side_data.get("leftOnBase"),
                }
            )
    return rows


def _load_linescore_for_game(conn: psycopg.Connection, game_pk: int, season: int) -> int:
    data = call_with_retry(_get, "game_linescore", {"gamePk": game_pk})
    df = pd.DataFrame(_linescore_rows(data, game_pk))
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_linescore", df, scope_column="game_pk", scope_value=str(game_pk)
    )


_LINESCORE_COLUMNS = [
    "game_pk",
    "inning",
    "side",
    "runs",
    "hits",
    "errors",
    "left_on_base",
    "_season",
]


def _linescore_schedule_url(season: int) -> str:
    return (
        "https://statsapi.mlb.com/api/v1/schedule?"
        f"sportId=1&season={season}&hydrate=linescore"
    )


def _season_linescore_df(data: dict, season: int) -> pd.DataFrame:
    """Return every available game linescore for a season in one API call.

    The old loader made a separate ``game_linescore`` request for every game.
    MLB's schedule endpoint can hydrate all of them at once: a real 1967
    request returned linescores for all 1,630 games in 1.3 seconds. This
    preserves the same source data while removing thousands of network
    round-trips from a historical backfill.
    """
    rows = []
    for game_date in data.get("dates", []):
        for game in game_date.get("games", []):
            linescore = game.get("linescore")
            game_pk = game.get("gamePk")
            if linescore and game_pk is not None:
                rows.extend(_linescore_rows(linescore, int(game_pk)))
    return pd.DataFrame(
        [{**row, "_season": str(season)} for row in rows], columns=_LINESCORE_COLUMNS
    )


def _load_linescores_for_season(
    conn: psycopg.Connection,
    season: int,
    *,
    run_id: int | None = None,
    data: dict | None = None,
    artifact: tuple[str, str] | None = None,
    record_ledger: bool = True,
) -> int:
    """Land one hydrated schedule as a replayable, idempotent source item.

    A season-wide schedule response is dramatically quicker than one
    ``game_linescore`` request per game.  It remains a real source item,
    though: archive it, replace exactly its season scope with COPY, and only
    then write its ledger marker.  That gives line scores the same recovery
    guarantees as win probability and context metrics.
    """
    if data is None:
        data = call_with_retry(
            _get,
            "schedule",
            {"sportId": 1, "season": season, "hydrate": "linescore"},
            force=True,
        )
    df = _season_linescore_df(data, season)
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    if artifact is None:
        content = gzip.compress(encoded, mtime=0)
        artifact_id = hashlib.sha256(content).hexdigest()[:16]
        path, entry = manifest.persist_artifact(
            SOURCE,
            f"analytics/{season}/linescore-schedule-{artifact_id}.json.gz",
            content,
            url=_linescore_schedule_url(season),
            metadata={
                "parser_version": ANALYTICS_PARSER_VERSION,
                "schema_fingerprint": manifest.schema_fingerprint(_LINESCORE_COLUMNS),
                "records": len(df),
            },
        )
        artifact_path = str(path.relative_to(path.parents[2]))
        artifact_sha256 = str(entry["sha256"])
    else:
        artifact_path, artifact_sha256 = artifact
    count = replace_dataframe_scopes(
        conn,
        "raw.mlb_linescore",
        df,
        scope_column="_season",
        scope_values=[str(season)],
    )
    if record_ledger:
        record_items(
            conn,
            [
                {
                    "source": SOURCE,
                    "dataset": "linescore_schedule",
                    "item_key": str(season),
                    "status": "loaded",
                    "source_url": _linescore_schedule_url(season),
                    "artifact_path": artifact_path,
                    "artifact_sha256": artifact_sha256,
                    "bytes": len(encoded),
                    "http_status": 200,
                    "rows": count,
                    "parser_version": ANALYTICS_PARSER_VERSION,
                    "schema_fingerprint": manifest.schema_fingerprint(_LINESCORE_COLUMNS),
                    "run_id": run_id,
                }
            ],
        )
    return count


def _linescores_already_landed(conn: psycopg.Connection, season: int) -> bool:
    """Return true only when the durable schedule item still matches raw rows."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rows, artifact_path, artifact_sha256
                FROM meta.ingestion_item
                WHERE source = %s AND dataset = 'linescore_schedule'
                  AND item_key = %s AND status = 'loaded'
                """,
                (SOURCE, str(season)),
            )
            item = cur.fetchone()
            if item is None:
                return False
            cur.execute("SELECT count(*) FROM raw.mlb_linescore WHERE _season = %s", (str(season),))
            return (
                int(fetch_one(cur)[0]) == int(item[0] or 0)
                and _analytics_artifact_is_valid(item[1], item[2])
            )
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return False


def _load_context_metrics_for_game(conn: psycopg.Connection, game_pk: int, season: int) -> int:
    # One row per game, not per-play: pregame win probability (distinct from
    # raw.mlb_win_prob's per-at-bat values) plus positional sacrifice-fly
    # probability — confirmed via a real call this is game-level context,
    # not a per-play series (its own "game" sub-object is the only nested
    # structure; the rest are flat scalars).
    data = call_with_retry(_get, "game_contextMetrics", {"gamePk": game_pk})
    row = {
        "game_pk": game_pk,
        "away_win_probability": data.get("awayWinProbability"),
        "home_win_probability": data.get("homeWinProbability"),
        "left_field_sac_fly_probability": data.get("leftFieldSacFlyProbability"),
        "center_field_sac_fly_probability": data.get("centerFieldSacFlyProbability"),
        "right_field_sac_fly_probability": data.get("rightFieldSacFlyProbability"),
    }
    df = pd.DataFrame([row])
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_game_context", df, scope_column="game_pk", scope_value=str(game_pk)
    )


def _load_game_detail_for_game(
    conn: psycopg.Connection, game_pk: int, season: int
) -> dict[str, int]:
    """Play-by-play, box score (batting/pitching/fielding + umpires), and the
    analytics trio (win probability/line score/game context) all key off the
    same game_pk — loaded together per game so a bootstrap/update loop only
    has to fetch each season's/day's game list once, even though each is
    still its own separate API call."""
    counts = {"raw.mlb_playbyplay": _load_playbyplay_for_game(conn, game_pk, season)}
    counts.update(_load_boxscore_for_game(conn, game_pk))
    counts.update(_load_analytics_for_game(conn, game_pk, season))
    return counts


_GAME_DETAIL_TABLES = [
    "raw.mlb_playbyplay",
    "raw.mlb_boxscore_batting",
    "raw.mlb_boxscore_pitching",
    "raw.mlb_boxscore_fielding",
    "raw.mlb_linescore",
    "raw.mlb_game_context",
    "raw.mlb_umpire",
    "raw.mlb_win_prob",
]


def _load_game_detail_for_season(conn: psycopg.Connection, season: int) -> dict[str, int]:
    totals: dict[str, int] = dict.fromkeys(_GAME_DETAIL_TABLES, 0)
    try:
        games = call_with_retry(statsapi.schedule, season=season, sportId=1)
    except Exception as exc:
        print(f"mlb_api: game detail for season {season} failed ({exc}); skipping whole season")
        return totals
    for game_pk in _started_game_ids(games):
        try:
            for table, count in _load_game_detail_for_game(conn, game_pk, season).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: game detail for game {game_pk} failed ({exc}); skipping")
    return totals


_ANALYTICS_TABLES = ["raw.mlb_win_prob", "raw.mlb_linescore", "raw.mlb_game_context"]


def _already_loaded_analytics_games(conn: psycopg.Connection, season: int) -> set[int]:
    """Game IDs present in every analytics relation for ``season``.

    A completed game is skippable only when its win-probability, linescore,
    and context rows all remain available.  A single-table marker would hide
    a partial load or later data loss, preventing the next resumable
    bootstrap from repairing it.

    Regression: a real full-history bootstrap (1950-2026, ~24,600
    candidate games) had no skip check at all here -- every re-run,
    including a plain retry after an interruption, redid the *entire*
    per-game sweep from scratch, re-fetching ~21,500 already-successful
    games and re-confirming the same ~800+ genuinely-empty ones every
    single time. This does not close that second gap (a confirmed-empty
    game still has no row to skip against, so it's still re-checked next
    run -- a real, smaller remaining cost, not fixed here) but removes
    the dominant one: skipping already-loaded games cuts a repeat run's
    real work by roughly 90%, confirmed against this project's own
    production numbers (21,500 of ~24,600) at the time this was written.

    Returns an empty set, not an error, if raw.mlb_game_context doesn't
    exist yet -- a fresh database genuinely has nothing to skip."""
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                SELECT game_pk FROM raw.mlb_win_prob WHERE _season = %s
                INTERSECT
                SELECT game_pk FROM raw.mlb_linescore WHERE _season = %s
                INTERSECT
                SELECT game_pk FROM raw.mlb_game_context WHERE _season = %s
                """,
                (str(season), str(season), str(season)),
            )
        except psycopg.errors.UndefinedTable:
            conn.rollback()
            return set()
        return {int(row[0]) for row in cur.fetchall()}


def _load_analytics_for_game(
    conn: psycopg.Connection, game_pk: int, season: int, *, include_linescore: bool = True
) -> dict[str, int]:
    counts = {
        "raw.mlb_win_prob": _load_win_prob_for_game(conn, game_pk, season),
        "raw.mlb_game_context": _load_context_metrics_for_game(conn, game_pk, season),
    }
    if include_linescore:
        counts["raw.mlb_linescore"] = _load_linescore_for_game(conn, game_pk, season)
    return counts


def _analytics_url(endpoint: str, game_pk: int) -> str:
    """Canonical source URL recorded beside each replayable API item."""
    endpoint_path = {
        "game_winProbability": "winProbability",
        "game_contextMetrics": "contextMetrics",
    }[endpoint]
    return f"https://statsapi.mlb.com/api/v1/game/{game_pk}/{endpoint_path}"


def _fetch_analytics_document(endpoint: str, game_pk: int, params: dict) -> object:
    """Fetch one analytics document with a connection reused by its worker.

    The general connector keeps ``statsapi`` as its friendly endpoint adapter.
    This hot path uses the documented HTTP URL directly because the package's
    one-shot requests prevent connection reuse across tens of thousands of
    game documents.  Sessions are thread-local: no unsafe cross-thread state,
    and no connection setup for every request.
    """
    def reset_session(session: requests.Session) -> None:
        """Do not retry a failed request over a potentially stale socket.

        The historical backfill keeps one session per worker for normal
        keep-alive reuse.  In long runs a CDN connection can instead become
        unhealthy: a fresh request succeeds immediately while that worker
        repeatedly waits for its old socket.  Retrying with a fresh session
        preserves connection reuse in the common case and bounds that rare
        failure mode without adding another global client or unbounded retry.
        """
        session.close()
        if getattr(_ANALYTICS_LOCAL, "session", None) is session:
            delattr(_ANALYTICS_LOCAL, "session")

    def request():
        session = getattr(_ANALYTICS_LOCAL, "session", None)
        if session is None:
            session = requests.Session()
            _ANALYTICS_LOCAL.session = session
        try:
            response = session.get(
                _analytics_url(endpoint, game_pk),
                params=params,
                timeout=ANALYTICS_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException:
            reset_session(session)
            raise
        if response.status_code >= 400:
            # A confirmed 404 is an expected terminal result for some old
            # games and is handled by the caller.  Other failures should not
            # leave the retry loop attached to a bad keep-alive connection.
            if response.status_code != 404:
                reset_session(session)
            response.raise_for_status()
        try:
            return response.json()
        except requests.exceptions.RequestException:
            reset_session(session)
            raise

    return call_with_retry(
        request,
        max_attempts=ANALYTICS_RETRY_ATTEMPTS,
        backoff_seconds=ANALYTICS_BACKOFF_SECONDS,
    )


def _analytics_item_key(season: int, game_pk: int) -> str:
    return f"{season}:{game_pk}"


def _terminal_analytics_games(conn: psycopg.Connection, season: int) -> set[int]:
    """Return games whose two per-game API responses are already durable.

    Raw tables alone cannot prove a zero-row response was intentionally
    received.  The ledger does: a 404 is terminal, and a 200 with no rows is
    terminal once its JSON artifact and database replace are committed.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dataset, split_part(item_key, ':', 2)::integer, status, rows,
                       artifact_path, artifact_sha256
                FROM meta.ingestion_item
                WHERE source = %s
                  AND dataset IN ('win_probability', 'context_metrics')
                  AND item_key LIKE %s
                  AND status IN ('loaded', 'unavailable')
                """,
                (SOURCE, f"{season}:%"),
            )
            items = {
                (str(dataset), int(game_pk)): (
                    str(status),
                    int(rows or 0),
                    str(artifact_path) if artifact_path else None,
                    str(artifact_sha256) if artifact_sha256 else None,
                )
                for dataset, game_pk, status, rows, artifact_path, artifact_sha256 in cur.fetchall()
            }
            cur.execute(
                "SELECT game_pk::integer, count(*) FROM raw.mlb_win_prob "
                "WHERE _season = %s GROUP BY game_pk",
                (str(season),),
            )
            win_rows = {int(game_pk): int(count) for game_pk, count in cur.fetchall()}
            cur.execute(
                "SELECT game_pk::integer, count(*) FROM raw.mlb_game_context "
                "WHERE _season = %s GROUP BY game_pk",
                (str(season),),
            )
            context_rows = {int(game_pk): int(count) for game_pk, count in cur.fetchall()}
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return set()

    terminal = set()
    artifact_valid: dict[tuple[str | None, str | None], bool] = {}

    def has_valid_artifact(path: str | None, checksum: str | None) -> bool:
        key = (path, checksum)
        if key not in artifact_valid:
            artifact_valid[key] = _analytics_artifact_is_valid(path, checksum)
        return artifact_valid[key]

    for game_pk in {game for _, game in items}:
        win = items.get(("win_probability", game_pk))
        context = items.get(("context_metrics", game_pk))
        if win is None or context is None:
            continue
        win_ok = (
            (win[0] == "unavailable" or win_rows.get(game_pk, 0) == win[1])
            and has_valid_artifact(win[2], win[3])
        )
        context_ok = (
            (context[0] == "unavailable" or context_rows.get(game_pk, 0) == context[1])
            and has_valid_artifact(context[2], context[3])
        )
        if win_ok and context_ok:
            terminal.add(game_pk)
    return terminal


def _analytics_season_complete(conn: psycopg.Connection, season: int) -> bool:
    """Require source-item proof for every finished scheduled game.

    This intentionally does not use ``season_already_loaded``.  That helper
    answers only "does this table have any rows for the season?", which is
    not enough for a three-endpoint, per-game historical backfill.  A legacy
    raw-only load is therefore replayed once into the durable ledger rather
    than being silently treated as complete forever.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT game_id::integer
                FROM raw.mlb_schedule
                WHERE _season = %s AND status = 'Final'
                """,
                (str(season),),
            )
            expected = {int(row[0]) for row in cur.fetchall()}
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return False
    return (
        bool(expected)
        and expected.issubset(_terminal_analytics_games(conn, season))
        and _linescores_already_landed(conn, season)
    )


def _fetch_analytics_game(game_pk: int) -> dict[str, Any]:
    """Fetch both independent analytics documents for one game.

    ``statsapi`` remains the endpoint adapter.  Parallelism happens above this
    function, so workers never share a database connection or manifest file.
    A confirmed 404 becomes an explicit terminal result; transient failures
    still use the repository-wide bounded retry policy and surface visibly.
    """
    documents: dict[str, dict[str, Any]] = {}
    for dataset, endpoint, params in (
        ("win_probability", "game_winProbability", {"gamePk": game_pk, "fields": WIN_PROB_FIELDS}),
        ("context_metrics", "game_contextMetrics", {"gamePk": game_pk}),
    ):
        try:
            payload = _fetch_analytics_document(endpoint, game_pk, params)
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status != 404:
                raise
            documents[dataset] = {
                "status": "unavailable",
                "http_status": 404,
                "payload": None,
                "url": _analytics_url(endpoint, game_pk),
            }
        else:
            documents[dataset] = {
                "status": "loaded",
                "http_status": 200,
                "payload": payload,
                "url": _analytics_url(endpoint, game_pk),
            }
    return {"game_pk": game_pk, "documents": documents}


def _artifact_for_analytics_batch(
    season: int, batch_number: int, results: list[dict[str, Any]]
) -> tuple[str, str]:
    """Persist source-faithful JSON payloads before their typed COPY load."""
    records = []
    for result in results:
        game_pk = int(result["game_pk"])
        for dataset, document in dict(result["documents"]).items():
            records.append(
                {
                    "dataset": dataset,
                    "game_pk": game_pk,
                    "http_status": document["http_status"],
                    "url": document["url"],
                    "payload": document["payload"],
                }
            )
    ndjson = "\n".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records
    )
    content = gzip.compress(f"{ndjson}\n".encode(), mtime=0)
    artifact_id = hashlib.sha256(content).hexdigest()[:16]
    filename = f"analytics/{season}/batch-{batch_number:05d}-{artifact_id}.ndjson.gz"
    path, entry = manifest.persist_artifact(
        SOURCE,
        filename,
        content,
        url="https://statsapi.mlb.com/api/v1/game/{gamePk}/[winProbability|contextMetrics]",
        metadata={
            "parser_version": ANALYTICS_PARSER_VERSION,
            "schema_fingerprint": manifest.schema_fingerprint(
                ["dataset", "game_pk", "http_status", "url", "payload"]
            ),
            "records": len(records),
        },
    )
    return str(path.relative_to(path.parents[2])), str(entry["sha256"])


def _load_analytics_batch(
    conn: psycopg.Connection,
    season: int,
    batch_number: int,
    results: list[dict[str, Any]],
    *,
    run_id: int | None,
    artifact: tuple[str, str] | None = None,
    record_ledger: bool = True,
) -> dict[str, int]:
    """Archive, replace, and ledger a fetched batch as one durable unit."""
    if artifact is None:
        artifact_path, artifact_sha256 = _artifact_for_analytics_batch(
            season, batch_number, results
        )
    else:
        artifact_path, artifact_sha256 = artifact
    win_rows: list[dict] = []
    context_rows: list[dict] = []
    loaded_scopes: dict[str, list[str]] = {"win_probability": [], "context_metrics": []}
    items: list[dict] = []
    for result in results:
        game_pk = int(result["game_pk"])
        for dataset, document in dict(result["documents"]).items():
            payload = document["payload"]
            status = str(document["status"])
            rows: list[dict]
            if dataset == "win_probability":
                rows = _win_prob_rows(payload or [], game_pk)
                win_rows.extend({**row, "_season": str(season)} for row in rows)
            else:
                data = payload or {}
                rows = (
                    [
                        {
                            "game_pk": game_pk,
                            "away_win_probability": data.get("awayWinProbability"),
                            "home_win_probability": data.get("homeWinProbability"),
                            "left_field_sac_fly_probability": data.get(
                                "leftFieldSacFlyProbability"
                            ),
                            "center_field_sac_fly_probability": data.get(
                                "centerFieldSacFlyProbability"
                            ),
                            "right_field_sac_fly_probability": data.get(
                                "rightFieldSacFlyProbability"
                            ),
                            "_season": str(season),
                        }
                    ]
                    if status == "loaded"
                    else []
                )
                context_rows.extend(rows)
            if status == "loaded":
                loaded_scopes[dataset].append(str(game_pk))
            encoded = (
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                if payload is not None
                else b""
            )
            items.append(
                {
                    "source": SOURCE,
                    "dataset": dataset,
                    "item_key": _analytics_item_key(season, game_pk),
                    "status": status,
                    "source_url": document["url"],
                    "artifact_path": artifact_path,
                    "artifact_sha256": artifact_sha256,
                    "bytes": len(encoded),
                    "http_status": document["http_status"],
                    "rows": len(rows),
                    "parser_version": ANALYTICS_PARSER_VERSION,
                    "schema_fingerprint": manifest.schema_fingerprint(
                        list(rows[0]) if rows else ["game_pk"]
                    ),
                    "run_id": run_id,
                }
            )
    win_df = pd.DataFrame(
        win_rows,
        columns=[
            "game_pk",
            "at_bat_index",
            "inning",
            "half_inning",
            "home_win_probability",
            "away_win_probability",
            "home_win_probability_added",
            "_season",
        ],
    )
    context_df = pd.DataFrame(
        context_rows,
        columns=[
            "game_pk",
            "away_win_probability",
            "home_win_probability",
            "left_field_sac_fly_probability",
            "center_field_sac_fly_probability",
            "right_field_sac_fly_probability",
            "_season",
        ],
    )
    win_count = replace_dataframe_scopes(
        conn,
        "raw.mlb_win_prob",
        win_df,
        scope_column="game_pk",
        scope_values=loaded_scopes["win_probability"],
    )
    context_count = replace_dataframe_scopes(
        conn,
        "raw.mlb_game_context",
        context_df,
        scope_column="game_pk",
        scope_values=loaded_scopes["context_metrics"],
    )
    if record_ledger:
        record_items(conn, items)
    conn.commit()
    return {"raw.mlb_win_prob": win_count, "raw.mlb_game_context": context_count}


def _load_analytics_for_season(
    conn: psycopg.Connection,
    season: int,
    *,
    run_id: int | None = None,
    workers: int = ANALYTICS_WORKERS,
) -> dict[str, int]:
    """Win probability, line score, and game-level context metrics, for
    seasons before FIRST_PLAYBYPLAY_YEAR — unlike play-by-play/box-scores/
    umpires (which Retrosheet already covers for these years, so re-pulling
    them would be pure duplication at real per-game API cost), none of
    these three has a Retrosheet equivalent. Confirmed the real boundary
    directly rather than assuming continuity back further: gamePk-based
    play-by-play/win-probability/box-score all return real, populated data
    for a 1950 game, but 404/empty for 1949 and earlier (tested 1901, 1920,
    1940, 1945, 1946, 1947, 1948, 1949 — all empty; 1950, 1955, 1957,
    1960 — all populated). `jobs_umpire_games` was also evaluated for this
    range (umpire assignments, per-umpire career game log) but confirmed to
    return a 401 Unauthorized regardless of parameters — an MLB-internal
    endpoint we don't have access to, not a shape mismatch like
    `jobs_officialScorers`; not built."""
    totals: dict[str, int] = dict.fromkeys(_ANALYTICS_TABLES, 0)
    try:
        games = call_with_retry(statsapi.schedule, season=season, sportId=1)
    except Exception as exc:
        print(f"mlb_api: analytics for season {season} failed ({exc}); skipping whole season")
        return totals
    if _linescores_already_landed(conn, season):
        print(f"mlb_api: linescores for season {season} already landed, skipping hydration")
    else:
        try:
            totals["raw.mlb_linescore"] = _load_linescores_for_season(
                conn, season, run_id=run_id
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: linescores for season {season} failed ({exc}); falling back per game")
    terminal = _terminal_analytics_games(conn, season)
    # The schedule endpoint can expose the same game more than once in a
    # reschedule/doubleheader-shaped response.  An API item is keyed by game,
    # not by schedule appearance: de-duplicate before both the network pool
    # and the bulk replace so an otherwise durable game cannot be fetched
    # twice in one retry.
    pending = sorted(set(_started_game_ids(games)) - terminal)
    if terminal:
        print(f"mlb_api: analytics for season {season}: skipped {len(terminal)} durable items")
    for offset in range(0, len(pending), ANALYTICS_BATCH_SIZE):
        game_batch = pending[offset : offset + ANALYTICS_BATCH_SIZE]
        batch_number = offset // ANALYTICS_BATCH_SIZE + 1
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(_fetch_analytics_game, game_batch))
            for table, count in _load_analytics_batch(
                conn, season, batch_number, results, run_id=run_id
            ).items():
                totals[table] = totals.get(table, 0) + count
        except Exception as exc:
            conn.rollback()
            print(
                f"mlb_api: analytics batch {batch_number} for season {season} failed ({exc}); "
                "leaving it for a safe retry"
            )
    return totals


def backfill_analytics(
    *,
    start_year: int = FIRST_WIN_PROB_YEAR,
    end_year: int | None = None,
    workers: int = ANALYTICS_WORKERS,
) -> dict[str, int]:
    """Run only the costly analytics stage, safely resumable by game.

    This is the operator-facing replacement for waiting through unrelated
    reference endpoints before the largest historical gap can make progress.
    It never deletes a whole season: completed source items are skipped, and
    each successful batch replaces only its own game keys.
    """
    final_year = end_year or date.today().year
    if start_year < FIRST_WIN_PROB_YEAR or end_year is not None and final_year < start_year:
        raise ValueError(
            f"analytics years must be within {FIRST_WIN_PROB_YEAR}-{date.today().year}"
        )
    if not 1 <= workers <= 24:
        raise ValueError("analytics workers must be between 1 and 24")
    totals: dict[str, int] = dict.fromkeys(_ANALYTICS_TABLES, 0)
    with get_connection() as conn, track_run(conn, SOURCE, "backfill") as result:
        for season in range(start_year, final_year + 1):
            for table, count in _load_analytics_for_season(
                conn, season, run_id=result["run_id"], workers=workers
            ).items():
                totals[table] = totals.get(table, 0) + count
        result["rows"] = sum(totals.values())
    return totals


def _read_analytics_artifact(relative_path: str, expected_sha256: str) -> bytes:
    """Read one ledger-referenced artifact and reject a wrong or unsafe file."""
    root = (manifest.DOWNLOADS_ROOT / SOURCE).resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise RuntimeError(
            f"analytics artifact is missing or outside downloads root: {relative_path}"
        )
    content = path.read_bytes()
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"analytics artifact checksum mismatch for {relative_path}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    return content


def _analytics_artifact_is_valid(
    relative_path: str | None, expected_sha256: str | None
) -> bool:
    """Whether a ledger reference still resolves to its immutable bytes."""
    if not relative_path or not expected_sha256:
        return False
    try:
        _read_analytics_artifact(relative_path, expected_sha256)
    except (OSError, RuntimeError):
        return False
    return True


def _analytics_results_from_ndjson(content: bytes) -> list[dict[str, Any]]:
    games: dict[int, dict[str, Any]] = {}
    for line in gzip.decompress(content).decode().splitlines():
        record = json.loads(line)
        game_pk = int(record["game_pk"])
        http_status = int(record["http_status"])
        dataset = str(record["dataset"])
        games.setdefault(game_pk, {"game_pk": game_pk, "documents": {}})["documents"][dataset] = {
            "status": "unavailable" if http_status == 404 else "loaded",
            "http_status": http_status,
            "payload": record.get("payload"),
            "url": record["url"],
        }
    incomplete = [game_pk for game_pk, result in games.items() if len(result["documents"]) != 2]
    if incomplete:
        raise RuntimeError(
            f"analytics artifact is missing endpoint documents for games: {incomplete[:5]}"
        )
    return [games[game_pk] for game_pk in sorted(games)]


def replay_analytics(
    *, start_year: int = FIRST_WIN_PROB_YEAR, end_year: int | None = None
) -> dict[str, int]:
    """Rebuild analytics raw tables from verified local artifacts, without HTTP.

    The ledger is the replay manifest: it identifies exactly which immutable
    artifact each successful source item came from.  We deliberately reject
    missing or checksum-mismatched files rather than silently making a
    partial rebuild look successful.
    """
    final_year = end_year or date.today().year
    if start_year < FIRST_WIN_PROB_YEAR or final_year < start_year:
        raise ValueError(
            f"analytics years must be within {FIRST_WIN_PROB_YEAR}-{date.today().year}"
        )
    totals: dict[str, int] = dict.fromkeys(_ANALYTICS_TABLES, 0)
    with get_connection() as conn, track_run(conn, SOURCE, "backfill") as result:
        for season in range(start_year, final_year + 1):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT artifact_path, artifact_sha256
                    FROM meta.ingestion_item
                    WHERE source = %s AND dataset = 'linescore_schedule'
                      AND item_key = %s AND status = 'loaded'
                    """,
                    (SOURCE, str(season)),
                )
                linescore_artifacts = cur.fetchall()
                cur.execute(
                    """
                    SELECT DISTINCT artifact_path, artifact_sha256
                    FROM meta.ingestion_item
                    WHERE source = %s
                      AND dataset IN ('win_probability', 'context_metrics')
                      AND item_key LIKE %s
                      AND status IN ('loaded', 'unavailable')
                    ORDER BY artifact_path
                    """,
                    (SOURCE, f"{season}:%"),
                )
                batch_artifacts = cur.fetchall()
            if len(linescore_artifacts) != 1:
                raise RuntimeError(
                    f"season {season}: expected one durable linescore artifact, found "
                    f"{len(linescore_artifacts)}"
                )
            linescore_path, linescore_sha256 = linescore_artifacts[0]
            linescore_data = json.loads(
                gzip.decompress(_read_analytics_artifact(linescore_path, linescore_sha256))
            )
            totals["raw.mlb_linescore"] += _load_linescores_for_season(
                conn,
                season,
                run_id=result["run_id"],
                data=linescore_data,
                artifact=(str(linescore_path), str(linescore_sha256)),
                record_ledger=False,
            )
            for batch_number, (artifact_path, artifact_sha256) in enumerate(
                batch_artifacts, start=1
            ):
                results = _analytics_results_from_ndjson(
                    _read_analytics_artifact(str(artifact_path), str(artifact_sha256))
                )
                for table, count in _load_analytics_batch(
                    conn,
                    season,
                    batch_number,
                    results,
                    run_id=result["run_id"],
                    artifact=(str(artifact_path), str(artifact_sha256)),
                    record_ledger=False,
                ).items():
                    totals[table] = totals.get(table, 0) + count
            conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def _load_game_detail_for_today(conn: psycopg.Connection) -> dict[str, int]:
    today = date.today().strftime("%m/%d/%Y")
    games = call_with_retry(statsapi.schedule, date=today, sportId=1)
    season = date.today().year
    totals: dict[str, int] = dict.fromkeys(_GAME_DETAIL_TABLES, 0)
    for game_pk in _started_game_ids(games):
        try:
            for table, count in _load_game_detail_for_game(conn, game_pk, season).items():
                totals[table] = totals.get(table, 0) + count
        except Exception as exc:
            print(f"mlb_api: game detail for game {game_pk} failed ({exc}); skipping")
    return totals


def _load_draft_years(conn: psycopg.Connection, current_year: int) -> int:
    total = 0
    for year in range(FIRST_DRAFT_YEAR, current_year + 1):
        if year < current_year and season_already_loaded(conn, "raw.mlb_draft", year):
            print(f"mlb_api: {year} draft already loaded, skipping")
            continue
        try:
            total += _load_draft(conn, year)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: draft {year} failed ({exc}); skipping")
    return total


# --- Reference/personnel/organizational/official-stats data (ADR-020) ---
#
# Kept in this same file/connector (not split out) per explicit direction to
# consolidate rather than multiply connector modules — but NOT folded into
# update() (see update()'s own docstring below): this is season-level
# reference/personnel data, not per-game/per-5-minute data, and refreshing
# ~30 teams' worth of coaches/alumni/personnel/attendance/stat-leaders every
# 5 minutes on the cron cycle would be pure waste with no freshness benefit.
# Only bootstrap() touches these — an operator re-runs bootstrap()
# periodically (or via the once-per-run reference block below) to pick up
# real-world changes (a new coach hired, a new season's attendance, etc.).
ALUMNI_GROUPS = ["hitting", "pitching"]


def _load_sports(conn: psycopg.Connection) -> int:
    data = call_with_retry(_get, "sports", {}, force=True)
    df = pd.DataFrame(data.get("sports", []))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_sport", df)


def _load_leagues(conn: psycopg.Connection) -> int:
    data = call_with_retry(_get, "league", {"sportId": 1}, force=True)
    rows = []
    for league in data.get("leagues", []):
        row = {k: v for k, v in league.items() if not isinstance(v, (dict, list))}
        season_info = league.get("seasonDateInfo", {})
        rows.append({**row, **{f"season_{k}": v for k, v in season_info.items()}})
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_league", df)


def _load_divisions(conn: psycopg.Connection) -> int:
    data = call_with_retry(_get, "divisions", {"sportId": 1}, force=True)
    rows = []
    for division in data.get("divisions", []):
        row = {k: v for k, v in division.items() if not isinstance(v, (dict, list))}
        row["league_id"] = division.get("league", {}).get("id")
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_division", df)


def _load_seasons(conn: psycopg.Connection) -> int:
    data = call_with_retry(_get, "seasons", {"sportId": 1, "all": True}, force=True)
    df = pd.DataFrame(data.get("seasons", []))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_season", df)


def _load_player_pool(conn: psycopg.Connection, season: int) -> int:
    data = call_with_retry(_get, "sports_players", {"sportId": 1, "season": season})
    rows = []
    for person in data.get("people", []):
        team = person.get("currentTeam", {})
        rows.append(
            {
                "person_id": person.get("id"),
                "full_name": person.get("fullName"),
                "birth_date": person.get("birthDate"),
                "current_team_id": team.get("id"),
                "current_team_name": team.get("name"),
                "active": person.get("active"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_player_pool", df, scope_column="_season", scope_value=str(season)
    )


def _load_free_agents(conn: psycopg.Connection, season: int) -> int:
    data = call_with_retry(_get, "people_freeAgents", {"season": season}, force=True)
    rows = []
    for fa in data.get("freeAgents", []):
        player = fa.get("player", {})
        original_team = fa.get("originalTeam", {})
        new_team = fa.get("newTeam", {})
        rows.append(
            {
                "person_id": player.get("id"),
                "person_name": player.get("fullName"),
                "original_team_id": original_team.get("id"),
                "original_team_name": original_team.get("name"),
                "new_team_id": new_team.get("id"),
                "new_team_name": new_team.get("name"),
                "notes": fa.get("notes"),
                "date_declared": fa.get("dateDeclared"),
                "date_signed": fa.get("dateSigned"),
                "rank": fa.get("rank"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_free_agent", df, scope_column="_season", scope_value=str(season)
    )


def _load_coaches(conn: psycopg.Connection, season: int) -> int:
    tasks = [
        (team_id, "team_coaches", {"teamId": team_id, "season": season})
        for team_id in _season_team_ids(season)
    ]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=REFERENCE_WORKERS) as pool:
        for team_id, data in pool.map(_fetch_reference_task, tasks):
            for entry in data.get("roster", []):
                person = entry.get("person", {})
                rows.append(
                    {
                        "team_id": team_id,
                        "person_id": person.get("id"),
                        "person_name": person.get("fullName"),
                        "jersey_number": entry.get("jerseyNumber"),
                        "job": entry.get("job"),
                        "job_id": entry.get("jobId"),
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_coach", df, scope_column="_season", scope_value=str(season)
    )


def _fetch_reference_task(task: tuple[int, str, dict]) -> tuple[int, dict]:
    team_id, endpoint, params = task
    return team_id, call_with_retry(_get, endpoint, params)


def _load_alumni(conn: psycopg.Connection, season: int) -> int:
    tasks = [
        (team_id, "team_alumni", {"teamId": team_id, "season": season, "group": group})
        for team_id in _season_team_ids(season)
        for group in ALUMNI_GROUPS
    ]
    rows: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=REFERENCE_WORKERS) as pool:
        for (team_id, _, params), (_, data) in zip(
            tasks, pool.map(_fetch_reference_task, tasks), strict=True
        ):
            group = params["group"]
            rows.extend(
                {
                    "team_id": team_id,
                    "alumni_group": group,
                    "person_id": person.get("id"),
                    "person_name": person.get("fullName"),
                }
                for person in data.get("people", [])
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_alumni", df, scope_column="_season", scope_value=str(season)
    )


def _load_personnel(conn: psycopg.Connection) -> int:
    total = 0
    current_year = date.today().year
    for team_id in _season_team_ids(current_year):
        data = call_with_retry(_get, "team_personnel", {"teamId": team_id})
        rows = []
        for entry in data.get("roster", []):
            person = entry.get("person", {})
            rows.append(
                {
                    "team_id": team_id,
                    "person_id": person.get("id"),
                    "person_name": person.get("fullName"),
                    "job": entry.get("job"),
                    "job_id": entry.get("jobId"),
                }
            )
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        total += load_dataframe(
            conn, "raw.mlb_personnel", df, scope_column="team_id", scope_value=str(team_id)
        )
    return total


def _load_affiliates(conn: psycopg.Connection) -> int:
    current_year = date.today().year
    team_ids = _season_team_ids(current_year)
    data = call_with_retry(
        _get, "teams_affiliates", {"teamIds": ",".join(str(t) for t in team_ids)}
    )
    rows = []
    for team in data.get("teams", []):
        rows.append(
            {
                "affiliate_team_id": team.get("id"),
                "affiliate_name": team.get("name"),
                "parent_org_id": team.get("parentOrgId"),
                "parent_org_name": team.get("parentOrgName"),
                "league_name": team.get("league", {}).get("name"),
                "level": team.get("sport", {}).get("name"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_affiliate", df)


def _load_attendance(conn: psycopg.Connection) -> int:
    total = 0
    current_year = date.today().year
    for team_id in _season_team_ids(current_year):
        data = call_with_retry(_get, "attendance", {"teamId": team_id})
        rows = [{"team_id": team_id, **record} for record in data.get("records", [])]
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        total += load_dataframe(
            conn, "raw.mlb_attendance", df, scope_column="team_id", scope_value=str(team_id)
        )
    return total


def _load_game_pace(conn: psycopg.Connection, season: int) -> int:
    data = call_with_retry(_get, "gamePace", {"season": season, "sportId": 1})
    sports = data.get("sports", [])
    if not sports:
        return 0
    df = pd.DataFrame(sports)
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_game_pace", df, scope_column="_season", scope_value=str(season)
    )


# MLB's own official per-player/per-team season stat totals — a second,
# independently-computed copy of what our own core.play/core.pitch
# aggregates would produce, useful as a cross-validation check once those
# exist. STAT_GROUPS covers the two stat families the `stats`/`teams_stats`
# endpoints split on; `playerPool=all` + a large `limit` avoids the default
# top-50-only truncation (confirmed directly: without these, a 742-player
# season came back as only 50 rows).
STAT_GROUPS = ["hitting", "pitching"]

# leaderCategories/leaderGameTypes have no documented enum in the library's
# own metadata (confirmed: statsapi's endpoint catalog lists the param name
# but not valid values) — this is a curated, representative set of standard
# categories, not an exhaustive one, since there's no authoritative list to
# enumerate against. Documented here rather than silently limited.
LEADER_CATEGORIES = [
    "homeRuns",
    "battingAverage",
    "runsBattedIn",
    "onBasePlusSlugging",
    "stolenBases",
    "era",
    "wins",
    "strikeouts",
    "saves",
    "walksAndHitsPerInningPitched",
]


def _load_stats(conn: psycopg.Connection, season: int) -> int:
    rows = []
    for group in STAT_GROUPS:
        data = call_with_retry(
            _get,
            "stats",
            {
                "stats": "season",
                "group": group,
                "season": season,
                "sportId": 1,
                "limit": 2000,
                "playerPool": "all",
            },
        )
        for stat_block in data.get("stats", []):
            for split in stat_block.get("splits", []):
                stat = split.get("stat", {})
                rows.append(
                    {
                        "person_id": split.get("player", {}).get("id"),
                        "person_name": split.get("player", {}).get("fullName"),
                        "team_id": split.get("team", {}).get("id"),
                        "group": group,
                        **{_camel_to_snake(k): v for k, v in stat.items()},
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_player_stat", df, scope_column="_season", scope_value=str(season)
    )


def _load_team_stats(conn: psycopg.Connection, season: int) -> int:
    rows = []
    for group in STAT_GROUPS:
        data = call_with_retry(
            _get,
            "teams_stats",
            {"stats": "season", "group": group, "season": season, "sportIds": 1},
        )
        for stat_block in data.get("stats", []):
            for split in stat_block.get("splits", []):
                stat = split.get("stat", {})
                rows.append(
                    {
                        "team_id": split.get("team", {}).get("id"),
                        "team_name": split.get("team", {}).get("name"),
                        "group": group,
                        **{_camel_to_snake(k): v for k, v in stat.items()},
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_team_stat", df, scope_column="_season", scope_value=str(season)
    )


def _load_stats_leaders(conn: psycopg.Connection, season: int) -> int:
    rows = []
    for category in LEADER_CATEGORIES:
        data = call_with_retry(
            _get,
            "stats_leaders",
            {"leaderCategories": category, "season": season, "sportId": 1},
        )
        for block in data.get("leagueLeaders", []):
            for leader in block.get("leaders", []):
                rows.append(
                    {
                        "leader_category": category,
                        "rank": leader.get("rank"),
                        "value": leader.get("value"),
                        "person_id": leader.get("person", {}).get("id"),
                        "person_name": leader.get("person", {}).get("fullName"),
                        "team_id": leader.get("team", {}).get("id"),
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_stat_leader", df, scope_column="_season", scope_value=str(season)
    )


def _load_team_leaders(conn: psycopg.Connection, season: int) -> int:
    tasks = [
        (
            team_id,
            "team_leaders",
            {
                "teamId": team_id,
                "leaderCategories": category,
                "season": season,
                "leaderGameTypes": "R",
            },
        )
        for team_id in _season_team_ids(season)
        for category in LEADER_CATEGORIES
    ]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=REFERENCE_WORKERS) as pool:
        for (team_id, _, params), (_, data) in zip(
            tasks, pool.map(_fetch_reference_task, tasks), strict=True
        ):
            category = params["leaderCategories"]
            for block in data.get("teamLeaders", []):
                for leader in block.get("leaders", []):
                    rows.append(
                        {
                            "team_id": team_id,
                            "leader_category": category,
                            "rank": leader.get("rank"),
                            "value": leader.get("value"),
                            "person_id": leader.get("person", {}).get("id"),
                            "person_name": leader.get("person", {}).get("fullName"),
                        }
                    )
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_team_leader", df, scope_column="_season", scope_value=str(season)
    )


def _load_awards_catalog(conn: psycopg.Connection) -> int:
    # Catalog of award TYPES only (~680), not per-award-per-year recipient
    # history — a documented, deliberate boundary: Lahman's own
    # awards_players table already carries historical winners, and a full
    # recipients backfill here would be ~680 award IDs x up to 126 years
    # each with no batching mechanism, a combinatorial cost out of
    # proportion to the incremental value over Lahman's existing coverage.
    data = call_with_retry(_get, "awards", {}, force=True)
    df = pd.DataFrame(data.get("awards", []))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_award", df)


def _load_conferences(conn: psycopg.Connection) -> int:
    data = call_with_retry(_get, "conferences", {"sportId": 1}, force=True)
    df = pd.DataFrame(data.get("conferences", []))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_conference", df)


def _job_roster_rows(data: dict) -> list[dict]:
    rows = []
    for entry in data.get("roster", []):
        person = entry.get("person", {})
        rows.append(
            {
                "person_id": person.get("id"),
                "person_name": person.get("fullName"),
                "jersey_number": entry.get("jerseyNumber"),
                "job": entry.get("job"),
                "job_id": entry.get("jobId"),
            }
        )
    return rows


def _load_official_scorers(conn: psycopg.Connection) -> int:
    # A current personnel directory, not historical-per-season data —
    # confirmed directly: season=1990/2000/2024 all return the identical
    # 235-person roster, so this isn't scoped by season the way team_coaches
    # is. One current-snapshot pull, full reload each run.
    current_year = date.today().year
    data = call_with_retry(_get, "jobs_officialScorers", {"sportId": 1, "season": current_year})
    df = pd.DataFrame(_job_roster_rows(data))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_official_scorer", df)


def _load_umpires_directory(conn: psycopg.Connection) -> int:
    # Same "current directory, not per-season history" behavior as
    # jobs_officialScorers above — confirmed directly.
    current_year = date.today().year
    data = call_with_retry(_get, "jobs_umpires", {"sportId": 1, "season": current_year})
    df = pd.DataFrame(_job_roster_rows(data))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_umpire_directory", df)


def _load_datacasters(conn: psycopg.Connection) -> int:
    # "Stringers" — MLB's official in-game data-entry personnel (who records
    # Gameday play-by-play as it happens). Same current-directory shape as
    # jobs_officialScorers/jobs_umpires, not per-season history.
    current_year = date.today().year
    data = call_with_retry(_get, "jobs_datacasters", {"sportId": 1, "season": current_year})
    df = pd.DataFrame(_job_roster_rows(data))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_datacaster", df)


def bootstrap() -> dict[str, int]:
    counts: dict[str, int] = {
        "raw.mlb_schedule": 0,
        "raw.mlb_standing": 0,
        "raw.mlb_roster": 0,
        "raw.mlb_transaction": 0,
        "raw.mlb_playbyplay": 0,
        "raw.mlb_boxscore_batting": 0,
        "raw.mlb_boxscore_pitching": 0,
        "raw.mlb_boxscore_fielding": 0,
        "raw.mlb_umpire": 0,
        "raw.mlb_win_prob": 0,
        "raw.mlb_linescore": 0,
        "raw.mlb_game_context": 0,
        "raw.mlb_player_pool": 0,
        "raw.mlb_free_agent": 0,
        "raw.mlb_coach": 0,
        "raw.mlb_alumni": 0,
        "raw.mlb_game_pace": 0,
        "raw.mlb_player_stat": 0,
        "raw.mlb_team_stat": 0,
        "raw.mlb_stat_leader": 0,
        "raw.mlb_team_leader": 0,
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
            # Reference/personnel/official-stats data — own try/except so a
            # failure here (e.g. one team's coaches call) doesn't roll back
            # the schedule/standings/roster/transaction data already
            # committed above for this same season.
            if season < current_year and season_already_loaded(conn, "raw.mlb_player_pool", season):
                print(f"mlb_api: {season} reference/personnel/stat data loaded, skipping")
            else:
                try:
                    counts["raw.mlb_player_pool"] += _load_player_pool(conn, season)
                    counts["raw.mlb_free_agent"] += _load_free_agents(conn, season)
                    counts["raw.mlb_coach"] += _load_coaches(conn, season)
                    counts["raw.mlb_alumni"] += _load_alumni(conn, season)
                    counts["raw.mlb_game_pace"] += _load_game_pace(conn, season)
                    counts["raw.mlb_player_stat"] += _load_stats(conn, season)
                    counts["raw.mlb_team_stat"] += _load_team_stats(conn, season)
                    counts["raw.mlb_stat_leader"] += _load_stats_leaders(conn, season)
                    counts["raw.mlb_team_leader"] += _load_team_leaders(conn, season)
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    print(
                        f"mlb_api: {season} reference/personnel/stat data failed ({exc}); "
                        "skipping, continuing bootstrap"
                    )
            if season >= FIRST_PLAYBYPLAY_YEAR:
                if season < current_year and season_already_loaded(
                    conn, "raw.mlb_playbyplay", season
                ):
                    print(f"mlb_api: {season} game detail already loaded, skipping")
                    continue
                # Own per-game commits inside — far higher call volume than
                # the rest of this loop, so it needs finer-grained resilience
                # than the single per-season try/except above.
                for table, count in _load_game_detail_for_season(conn, season).items():
                    counts[table] = counts.get(table, 0) + count
            elif season >= FIRST_WIN_PROB_YEAR:
                # Analytics-only range (1950 through FIRST_PLAYBYPLAY_YEAR-1)
                # — play-by-play/box-score/umpire stay out of this range
                # since Retrosheet already covers them there; win
                # probability/line score/game context have no Retrosheet
                # equivalent, so they're the pieces worth the per-game API
                # cost this far back.
                #
                # Real gap found in a later review, not hypothetical: each
                # game loads all three of raw.mlb_win_prob/_linescore/
                # _game_context independently (see _load_analytics_for_game
                # below), but this skip check only ever looked at
                # raw.mlb_win_prob. A season where win_prob succeeded but
                # linescore/game_context failed for some games (a real
                # possibility — three separate per-game API calls, only
                # wrapped in one shared try/except at the season level, see
                # _load_analytics_for_season) would look "loaded" forever
                # after, silently skipped on every future bootstrap re-run
                # with no way to self-heal. All three must have data before
                # a season is considered done.
                if _analytics_season_complete(conn, season):
                    print(f"mlb_api: {season} analytics already loaded, skipping")
                    continue
                for table, count in _load_analytics_for_season(
                    conn, season, run_id=result["run_id"]
                ).items():
                    counts[table] = counts.get(table, 0) + count
        # Draft, venue, team history, and person bios each load once, after
        # the season loop — none of them are season-scoped in a way that
        # fits inside it (draft is per-year but a fixed 1965+ range, not tied
        # to schedule/standings; the other three are whole-catalog reloads).
        counts["raw.mlb_draft"] = _load_draft_years(conn, current_year)
        try:
            counts["raw.mlb_venue"] = _load_venue(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: venue load failed ({exc}); skipping")
            counts["raw.mlb_venue"] = 0
        try:
            counts["raw.mlb_team_history"] = _load_team_history(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: team history load failed ({exc}); skipping")
            counts["raw.mlb_team_history"] = 0
        try:
            counts["raw.mlb_person"] = _load_person(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"mlb_api: person load failed ({exc}); skipping")
            counts["raw.mlb_person"] = 0
        # Whole-catalog reference tables and per-team-current tables — also
        # load once, after the season loop, same reasoning as venue/team
        # history/person above.
        for label, fn in [
            ("raw.mlb_sport", _load_sports),
            ("raw.mlb_league", _load_leagues),
            ("raw.mlb_division", _load_divisions),
            ("raw.mlb_season", _load_seasons),
            ("raw.mlb_personnel", _load_personnel),
            ("raw.mlb_affiliate", _load_affiliates),
            ("raw.mlb_attendance", _load_attendance),
            ("raw.mlb_award", _load_awards_catalog),
            ("raw.mlb_conference", _load_conferences),
            ("raw.mlb_official_scorer", _load_official_scorers),
            ("raw.mlb_umpire_directory", _load_umpires_directory),
            ("raw.mlb_datacaster", _load_datacasters),
        ]:
            try:
                counts[label] = fn(conn)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"mlb_api: {label} failed ({exc}); skipping")
                counts[label] = 0
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
    "captured_at",
]


def _live_snapshot(game_pk: int) -> dict | None:
    data = call_with_retry(_get, "game", {"gamePk": game_pk})
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
    captured_at = datetime.now(UTC).isoformat()
    rows = [
        {**snapshot, "captured_at": captured_at} for snapshot in snapshots if snapshot is not None
    ]
    df = pd.DataFrame(rows, columns=LIVE_GAME_COLUMNS)
    return append_dataframe(
        conn,
        "raw.mlb_live_game",
        df,
        identity_columns=("game_pk", "captured_at"),
    )


PROBABLE_COLUMNS = ["game_pk", "side", "pitcher_id", "pitcher_name", "captured_at"]


def _probable_rows(data: dict) -> list[dict]:
    """One row per (game_pk, side) that actually has a probable pitcher
    announced yet — a game several days out with no rotation decision made
    has no `probablePitcher` key at all on one or both sides (confirmed
    directly against real data, not assumed), so this only ever emits rows
    for sides that genuinely have an announcement, never a placeholder.
    Not filtered by game type here — the raw layer stays a faithful mirror
    of whatever the API returns (see docs/ARCHITECTURE.md); scoping to
    regular-season games happens downstream, in
    mlb_baseball/model/starter.py, via its join through gold.game_feature
    (already regular-season-only)."""
    rows = []
    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            game_pk = game.get("gamePk")
            teams = game.get("teams", {})
            for side in ("home", "away"):
                pp = teams.get(side, {}).get("probablePitcher")
                if not pp:
                    continue
                rows.append(
                    {
                        "game_pk": game_pk,
                        "side": side,
                        "pitcher_id": pp.get("id"),
                        "pitcher_name": pp.get("fullName"),
                    }
                )
    return rows


def _latest_probables(conn: psycopg.Connection) -> dict[tuple[str, str], str]:
    """The most recently captured pitcher_id for every (game_pk, side)
    raw.mlb_probable has ever seen — used to detect a real change (a new
    announcement or a scratch) before appending another snapshot. Returns
    {} on a fresh database where the table doesn't exist yet, same
    "not bootstrapped yet, not an error" treatment as season_already_loaded."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_probable')")
        (exists,) = fetch_one(cur)
        if not exists:
            return {}
        cur.execute(
            "SELECT DISTINCT ON (game_pk, side) game_pk, side, pitcher_id "
            "FROM raw.mlb_probable ORDER BY game_pk, side, _loaded_at DESC"
        )
        return {(game_pk, side): pitcher_id for game_pk, side, pitcher_id in cur.fetchall()}


def _new_probable_rows(rows: list[dict], known: dict[tuple[str, str], str]) -> list[dict]:
    """Only rows that are new or actually changed since the last known
    snapshot for that (game_pk, side). update() runs every 5 minutes and
    re-fetches the identical days-ahead window every single time, so
    appending unconditionally would write a duplicate, unchanged row for
    essentially every (game, side) currently in the window on every call
    (a full season's worth of in-window game-sides x 288 calls/day, almost
    entirely repeats of the same announcement) — the append-only history
    stays valuable for tracking real scratches specifically because it only
    grows when something actually changes, not on every poll."""
    return [r for r in rows if known.get((str(r["game_pk"]), r["side"])) != str(r["pitcher_id"])]


def _load_probable(conn: psycopg.Connection) -> int:
    # `schedule`'s own hydrate=probablePitcher param (verified directly
    # against real 2026 data before writing this, not assumed) puts
    # {"id": ..., "fullName": ...} at teams.<side>.probablePitcher — a
    # real person_id, unlike statsapi.schedule()'s own convenience wrapper
    # (already used for raw.mlb_schedule), which hydrates probables as a
    # bare name string with no id and no history (season-scoped replace
    # silently loses a scratch the moment the season reloads).
    today = date.today()
    end = today + timedelta(days=PROBABLE_WINDOW_DAYS)
    data = call_with_retry(
        _get,
        "schedule",
        {
            "sportId": 1,
            "startDate": today.strftime("%m/%d/%Y"),
            "endDate": end.strftime("%m/%d/%Y"),
            "hydrate": "probablePitcher",
        },
    )
    rows = _new_probable_rows(_probable_rows(data), _latest_probables(conn))
    captured_at = datetime.now(UTC).isoformat()
    df = pd.DataFrame(
        [{**row, "captured_at": captured_at} for row in rows], columns=PROBABLE_COLUMNS
    )
    if df.empty:
        return 0
    return append_dataframe(
        conn,
        "raw.mlb_probable",
        df,
        identity_columns=("game_pk", "side", "captured_at"),
    )


def update() -> dict[str, int]:
    # Deliberately does NOT touch the reference/personnel/official-stats
    # data added in ADR-020 (sports/leagues/divisions/seasons/player-pool/
    # free-agents/coaches/alumni/personnel/affiliates/attendance/game-pace/
    # player+team stats/leaders/awards) — this is called every 5 minutes by
    # cron (scripts/mlb_api_update.sh), and re-running ~30 teams' worth of
    # coaches/alumni/personnel/attendance/stat-leader calls every 5 minutes
    # would be pure API/DB load with no real freshness benefit (none of that
    # data changes minute-to-minute the way schedule/roster/live-game
    # state does). That data refreshes via bootstrap() instead — an operator
    # re-runs it periodically to pick up real-world changes.
    season = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        counts = {
            "raw.mlb_schedule": _load_schedule(conn, season),
            "raw.mlb_standing": _load_standings(conn, season)
            if season >= FIRST_STANDINGS_YEAR
            else 0,
            "raw.mlb_roster": _load_roster(conn, season),
            "raw.mlb_transaction": _load_transactions(conn, season),
            "raw.mlb_draft": _load_draft(conn, season) if season >= FIRST_DRAFT_YEAR else 0,
        }
        counts.update(_load_game_detail_for_today(conn))
        counts["raw.mlb_live_game"] = capture_live(conn)
        counts["raw.mlb_probable"] = _load_probable(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def _analytics_durable_coverage_check() -> Check:
    """Verify every final scheduled game has durable, still-present analytics.

    Raw row counts alone cannot distinguish a legitimate source 404 from a
    dropped response.  This joins the schedule, item ledger, and typed raw
    row counts in one set-based check, including the season-wide linescore
    artifact.  Unlike the lighter table-coverage checks below, it requires
    complete terminal coverage (100%), not a heuristic threshold.
    """
    return check_partition_coverage(
        "mlb_api analytics durable coverage",
        f"""
        WITH expected_games AS (
            SELECT DISTINCT _season, game_id AS game_pk
            FROM raw.mlb_schedule
            WHERE _season ~ '^[0-9]+$'
              AND _season::integer >= {FIRST_WIN_PROB_YEAR}
              AND _season::integer < {date.today().year}
              AND status = 'Final'
        ), expected AS (
            SELECT _season, count(*) AS expected_count FROM expected_games GROUP BY _season
        ), win_rows AS (
            SELECT _season, game_pk, count(*) AS row_count
            FROM raw.mlb_win_prob GROUP BY _season, game_pk
        ), context_rows AS (
            SELECT _season, game_pk, count(*) AS row_count
            FROM raw.mlb_game_context GROUP BY _season, game_pk
        ), terminal_games AS (
            SELECT split_part(item_key, ':', 1) AS _season,
                   split_part(item_key, ':', 2) AS game_pk
            FROM meta.ingestion_item item
            LEFT JOIN win_rows win
              ON win._season = split_part(item.item_key, ':', 1)
             AND win.game_pk = split_part(item.item_key, ':', 2)
            LEFT JOIN context_rows context
              ON context._season = split_part(item.item_key, ':', 1)
             AND context.game_pk = split_part(item.item_key, ':', 2)
            WHERE item.source = '{SOURCE}'
              AND item.dataset IN ('win_probability', 'context_metrics')
              AND item.status IN ('loaded', 'unavailable')
            GROUP BY item.item_key
            HAVING count(*) FILTER (WHERE item.dataset = 'win_probability') = 1
               AND count(*) FILTER (WHERE item.dataset = 'context_metrics') = 1
               AND bool_and(
                    CASE item.dataset
                        WHEN 'win_probability' THEN item.status = 'unavailable'
                            OR COALESCE(win.row_count, 0) = COALESCE(item.rows, 0)
                        ELSE item.status = 'unavailable'
                            OR COALESCE(context.row_count, 0) = COALESCE(item.rows, 0)
                    END
               )
        ), linescore_rows AS (
            SELECT _season, count(*) AS row_count FROM raw.mlb_linescore GROUP BY _season
        ), valid_linescores AS (
            SELECT item.item_key AS _season
            FROM meta.ingestion_item item
            LEFT JOIN linescore_rows line ON line._season = item.item_key
            WHERE item.source = '{SOURCE}' AND item.dataset = 'linescore_schedule'
              AND item.status = 'loaded'
              AND COALESCE(line.row_count, 0) = COALESCE(item.rows, 0)
        )
        SELECT expected._season,
               count(DISTINCT terminal_games.game_pk)
                   FILTER (WHERE valid_linescores._season IS NOT NULL),
               expected.expected_count
        FROM expected_games
        JOIN expected USING (_season)
        LEFT JOIN terminal_games
          ON terminal_games._season = expected_games._season
         AND terminal_games.game_pk = expected_games.game_pk
        LEFT JOIN valid_linescores
          ON valid_linescores._season = expected._season
        GROUP BY expected._season, expected.expected_count
        """,
        min_ratio=1.0,
    )


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.mlb_schedule"),
        check_table_has_rows("raw.mlb_standing"),
        check_table_has_rows("raw.mlb_roster"),
        check_table_has_rows("raw.mlb_transaction"),
        check_table_has_rows("raw.mlb_venue"),
        check_table_has_rows("raw.mlb_team_history"),
        check_table_has_rows("raw.mlb_person"),
        check_table_has_rows("raw.mlb_draft"),
        check_table_exists("raw.mlb_playbyplay"),
        check_table_exists("raw.mlb_boxscore_batting"),
        check_table_exists("raw.mlb_boxscore_pitching"),
        check_table_exists("raw.mlb_boxscore_fielding"),
        check_table_exists("raw.mlb_umpire"),
        check_table_exists("raw.mlb_win_prob"),
        check_table_exists("raw.mlb_linescore"),
        check_table_exists("raw.mlb_game_context"),
        check_table_exists("raw.mlb_live_game"),
        _analytics_durable_coverage_check(),
        # check_table_exists, not check_table_has_rows: between seasons (or
        # simply on a day nothing's changed since the last snapshot — see
        # _new_probable_rows) 0 rows is a normal, healthy state, not a sign
        # nothing was ever ingested.
        check_table_exists("raw.mlb_probable"),
        check_table_has_rows("raw.mlb_sport"),
        check_table_has_rows("raw.mlb_league"),
        check_table_has_rows("raw.mlb_division"),
        check_table_has_rows("raw.mlb_season"),
        check_table_has_rows("raw.mlb_player_pool"),
        check_table_has_rows("raw.mlb_free_agent"),
        check_table_has_rows("raw.mlb_coach"),
        check_table_has_rows("raw.mlb_alumni"),
        check_table_has_rows("raw.mlb_personnel"),
        check_table_has_rows("raw.mlb_affiliate"),
        check_table_has_rows("raw.mlb_attendance"),
        check_table_has_rows("raw.mlb_game_pace"),
        check_table_has_rows("raw.mlb_player_stat"),
        check_table_has_rows("raw.mlb_team_stat"),
        check_table_has_rows("raw.mlb_stat_leader"),
        check_table_has_rows("raw.mlb_team_leader"),
        check_table_has_rows("raw.mlb_award"),
        check_table_has_rows("raw.mlb_conference"),
        check_table_has_rows("raw.mlb_official_scorer"),
        check_table_has_rows("raw.mlb_umpire_directory"),
        check_table_has_rows("raw.mlb_datacaster"),
        # Per-season completeness, not just "does the table have any rows
        # at all" — found worth building after a real review turned up
        # four consecutive seasons (2022-2025) silently sitting at zero
        # raw.mlb_win_prob coverage despite thousands of completed games
        # each. Excludes the current season (still in progress by
        # definition, not a real gap) and anything before FIRST_WIN_PROB_YEAR
        # (no data expected there at all, a documented boundary, not a gap).
        #
        # All three analytics tables checked, not just win_prob — a real
        # gap found in a later review: each game loads win_prob/linescore/
        # game_context via three independent per-game API calls (see
        # _load_analytics_for_game), so a season where win_prob succeeded
        # but the other two failed for some games would have looked
        # "complete" here forever, with the doctor check for it passing
        # while linescore/game_context silently stayed incomplete. All
        # three get the identical query shape deliberately (a generated
        # list, not three hand-copied blocks) so they can't drift out of
        # sync with each other again the way this gap happened in the
        # first place.
        *[
            check_partition_coverage(
                f"{table.removeprefix('raw.')} season coverage",
                f"""
                WITH expected AS (
                    SELECT _season, count(DISTINCT game_id) FILTER (WHERE status = 'Final')
                    AS expected_count
                    FROM raw.mlb_schedule
                    WHERE _season ~ '^[0-9]+$'
                      AND _season::integer >= {FIRST_WIN_PROB_YEAR}
                      AND _season::integer < {date.today().year}
                    GROUP BY _season
                ), actual AS (
                    SELECT _season, count(DISTINCT game_pk) AS actual_count
                    FROM {table}
                    WHERE _season ~ '^[0-9]+$'
                      AND _season::integer >= {FIRST_WIN_PROB_YEAR}
                      AND _season::integer < {date.today().year}
                    GROUP BY _season
                )
                SELECT expected._season, COALESCE(actual.actual_count, 0), expected.expected_count
                FROM expected LEFT JOIN actual USING (_season)
                """,
            )
            for table in ("raw.mlb_win_prob", "raw.mlb_linescore", "raw.mlb_game_context")
        ],
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES),
    ]
