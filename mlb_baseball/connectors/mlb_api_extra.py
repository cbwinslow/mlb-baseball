"""Lands MLB Stats API reference/personnel/organizational data that isn't
tied to the per-game detail loop in mlb_api.py — into raw.mlb_sport,
raw.mlb_league, raw.mlb_division, raw.mlb_season, raw.mlb_player_pool,
raw.mlb_free_agent, raw.mlb_coach, raw.mlb_alumni, raw.mlb_personnel,
raw.mlb_affiliate, raw.mlb_attendance, and raw.mlb_game_pace, via the same
`statsapi` package as mlb_api.py.

Split into its own connector rather than folded into mlb_api.py: this data
refreshes far less often than schedule/roster/live-game data (season-level
reference/personnel snapshots, not per-game), so it doesn't belong on the
same 5-minute cron cadence — see docs/DECISIONS.md ADR-020.

- **Sports/leagues/divisions** (raw.mlb_sport/mlb_league/mlb_division):
  whole-catalog reference snapshots, full reload each run. `sports` returns
  every sport the API tracks (MLB, minor leagues, international) — kept
  as-is (source-faithful), not filtered to MLB only, since it's tiny and
  the sport code/name make it obvious which rows are MLB.
- **Seasons** (raw.mlb_season): season metadata (start/end dates, All-Star
  date, etc.) for every season the API knows about, one bulk call.
- **Player pool** (raw.mlb_player_pool): the "canonical season player
  universe" per `sports_players` — every player considered part of MLB's
  player pool that season, one call per season. Broader than
  raw.mlb_roster (which is scoped to actual 40-man/active rosters).
- **Free agents** (raw.mlb_free_agent): one call per season; genuinely 0
  rows before free agency's modern form existed (confirmed: 1990/2000
  empty, 2010+ populated) — not a bug, a real historical absence.
- **Coaches/alumni/personnel** (raw.mlb_coach/mlb_alumni/mlb_personnel):
  per current team. `team_alumni` requires a `group` param with no
  documented enum in the library's own metadata — confirmed via direct
  testing that "hitting" and "pitching" are both valid and return
  different rosters, so both are pulled per team per season.
- **Affiliates** (raw.mlb_affiliate): current MLB-to-minor-league
  organizational mapping per team — the mapping itself is real MLB
  organizational data even though the affiliate teams aren't MLB; full
  season-by-season minor league data for those affiliates is out of scope.
- **Attendance** (raw.mlb_attendance): one call per team returns FULL
  franchise history (confirmed: team 147 returns 1903-2026 in a single
  call) — a real historical gap closed cheaply (~30 calls total, not
  ~30 x 124 years).
- **Game pace** (raw.mlb_game_pace): one call per season, sport-wide
  aggregate pace-of-play stats (pitches/game, time/game, etc.).

`people_freeAgents` is called with force=True: like `transactions` in
mlb_api.py, the library's own required-parameter metadata says no params
are required, but a bare call returns a real 400 — confirmed directly that
adding `season` fixes it, another real (undocumented) library/API mismatch.

bootstrap() loads full history for player-pool/free-agents/game-pace (each
per-season), and a full reload for the small whole-catalog reference
tables (sports/leagues/divisions/seasons) and the per-team tables (coaches/
alumni/personnel/affiliates/attendance). Not on a repeating cron schedule —
none of this changes intra-day — so health_check() uses check_last_run.
"""

from datetime import date

import pandas as pd
import psycopg
import statsapi

from mlb_baseball.connectors.mlb_api import _season_team_ids
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe, season_already_loaded
from mlb_baseball.net import call_with_retry

SOURCE = "mlb_api_extra"
FIRST_YEAR = 1901
ALUMNI_GROUPS = ["hitting", "pitching"]


def _load_sports(conn: psycopg.Connection) -> int:
    data = call_with_retry(statsapi.get, "sports", {}, force=True)
    df = pd.DataFrame(data.get("sports", []))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_sport", df)


def _load_leagues(conn: psycopg.Connection) -> int:
    data = call_with_retry(statsapi.get, "league", {"sportId": 1}, force=True)
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
    data = call_with_retry(statsapi.get, "divisions", {"sportId": 1}, force=True)
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
    data = call_with_retry(statsapi.get, "seasons", {"sportId": 1, "all": True}, force=True)
    df = pd.DataFrame(data.get("seasons", []))
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.mlb_season", df)


def _load_player_pool(conn: psycopg.Connection, season: int) -> int:
    data = call_with_retry(statsapi.get, "sports_players", {"sportId": 1, "season": season})
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
    data = call_with_retry(statsapi.get, "people_freeAgents", {"season": season}, force=True)
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
    total = 0
    for team_id in _season_team_ids(season):
        data = call_with_retry(statsapi.get, "team_coaches", {"teamId": team_id, "season": season})
        rows = []
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
            continue
        df["_season"] = str(season)
        total += load_dataframe(
            conn,
            "raw.mlb_coach",
            df,
            scope_column="_season",
            scope_value=str(season),
        )
    return total


def _load_alumni(conn: psycopg.Connection, season: int) -> int:
    total = 0
    for team_id in _season_team_ids(season):
        for group in ALUMNI_GROUPS:
            data = call_with_retry(
                statsapi.get,
                "team_alumni",
                {"teamId": team_id, "season": season, "group": group},
            )
            rows = [
                {
                    "team_id": team_id,
                    "alumni_group": group,
                    "person_id": p.get("id"),
                    "person_name": p.get("fullName"),
                }
                for p in data.get("people", [])
            ]
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            df["_season"] = str(season)
            total += load_dataframe(
                conn, "raw.mlb_alumni", df, scope_column="_season", scope_value=str(season)
            )
    return total


def _load_personnel(conn: psycopg.Connection) -> int:
    total = 0
    current_year = date.today().year
    for team_id in _season_team_ids(current_year):
        data = call_with_retry(statsapi.get, "team_personnel", {"teamId": team_id})
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
        statsapi.get, "teams_affiliates", {"teamIds": ",".join(str(t) for t in team_ids)}
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
        data = call_with_retry(statsapi.get, "attendance", {"teamId": team_id})
        rows = []
        for record in data.get("records", []):
            rows.append({"team_id": team_id, **record})
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        total += load_dataframe(
            conn, "raw.mlb_attendance", df, scope_column="team_id", scope_value=str(team_id)
        )
    return total


def _load_game_pace(conn: psycopg.Connection, season: int) -> int:
    data = call_with_retry(statsapi.get, "gamePace", {"season": season, "sportId": 1})
    sports = data.get("sports", [])
    if not sports:
        return 0
    df = pd.DataFrame(sports)
    df["_season"] = str(season)
    return load_dataframe(
        conn, "raw.mlb_game_pace", df, scope_column="_season", scope_value=str(season)
    )


def bootstrap() -> dict[str, int]:
    counts: dict[str, int] = {
        "raw.mlb_player_pool": 0,
        "raw.mlb_free_agent": 0,
        "raw.mlb_coach": 0,
        "raw.mlb_alumni": 0,
        "raw.mlb_game_pace": 0,
    }
    current_year = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for season in range(FIRST_YEAR, current_year + 1):
            if season < current_year and season_already_loaded(conn, "raw.mlb_player_pool", season):
                print(f"mlb_api_extra: {season} already loaded, skipping")
                continue
            try:
                counts["raw.mlb_player_pool"] += _load_player_pool(conn, season)
                counts["raw.mlb_free_agent"] += _load_free_agents(conn, season)
                counts["raw.mlb_coach"] += _load_coaches(conn, season)
                counts["raw.mlb_alumni"] += _load_alumni(conn, season)
                counts["raw.mlb_game_pace"] += _load_game_pace(conn, season)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"mlb_api_extra: season {season} failed ({exc}); skipping, continuing")
        # Whole-catalog reference tables and per-team-current tables load
        # once, after the season loop — none are season-scoped.
        for label, fn in [
            ("raw.mlb_sport", _load_sports),
            ("raw.mlb_league", _load_leagues),
            ("raw.mlb_division", _load_divisions),
            ("raw.mlb_season", _load_seasons),
            ("raw.mlb_personnel", _load_personnel),
            ("raw.mlb_affiliate", _load_affiliates),
            ("raw.mlb_attendance", _load_attendance),
        ]:
            try:
                counts[label] = fn(conn)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"mlb_api_extra: {label} failed ({exc}); skipping")
                counts[label] = 0
        result["rows"] = sum(counts.values())
    return counts


def update() -> dict[str, int]:
    season = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        counts = {
            "raw.mlb_player_pool": _load_player_pool(conn, season),
            "raw.mlb_free_agent": _load_free_agents(conn, season),
            "raw.mlb_coach": _load_coaches(conn, season),
            "raw.mlb_alumni": _load_alumni(conn, season),
            "raw.mlb_game_pace": _load_game_pace(conn, season),
            "raw.mlb_personnel": _load_personnel(conn),
            "raw.mlb_affiliate": _load_affiliates(conn),
            "raw.mlb_attendance": _load_attendance(conn),
        }
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
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
        check_last_run(SOURCE),
    ]
