"""Builds `core` (the conformed/dimensional layer) from already-ingested
`raw` tables — see docs/DECISIONS.md ADR-013 and ARCHITECTURE.md "Layered
schema". This is not a connector: it never touches the network, and its job
is joining data that's *already* landed, not fetching new data. Driven by
`mlb conform`, not `mlb ingest <source>`.

Full truncate-and-rebuild every run, not incremental — unlike raw's
per-season scoped replace, there's no meaningful "what changed" for a
cross-source join at this row count (player/team/game together are under
300K rows; rebuilding takes well under a second). This also sidesteps the
whole class of bug ADR-010 documents: nothing here can partially overwrite
another chunk's data, because there are no chunks — one INSERT...SELECT per
table, every time.

Depends on raw tables that must already have data (checked explicitly
before running, not assumed):
    raw.retrosheet_team    (from `mlb ingest retrosheet_reference`)
    raw.register_people    (from `mlb ingest register`)
    raw.retrosheet_gameinfo (from `mlb ingest retrosheet`)
"""

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.ingest import track_run

SOURCE = "core"

# (raw table, connector that populates it) — checked before conform runs so
# a missing prerequisite fails with an actionable message, not a silent
# empty core rebuild or a confusing mid-query error.
PREREQUISITES = [
    ("raw.retrosheet_team", "mlb ingest retrosheet_reference --mode bootstrap"),
    ("raw.register_people", "mlb ingest register --mode bootstrap"),
    ("raw.retrosheet_gameinfo", "mlb ingest retrosheet --mode bootstrap"),
]


def _check_prerequisites(conn: psycopg.Connection) -> None:
    missing = []
    with conn.cursor() as cur:
        for table, fix_command in PREREQUISITES:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                missing.append(f"{table} does not exist — run `{fix_command}` first")
                continue
            (count,) = cur.fetchone()
            if count == 0:
                missing.append(f"{table} is empty — run `{fix_command}` first")
    if missing:
        raise RuntimeError("core requires raw data that isn't loaded yet: " + "; ".join(missing))


def _build_teams(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE core.team CASCADE")
        cur.execute(
            """
            INSERT INTO core.team (retro_team_id, league, city, nickname, first_year, last_year)
            SELECT team_id, league, city, nickname, first_year::integer, last_year::integer
            FROM raw.retrosheet_team
            """
        )
        return cur.rowcount


def _build_players(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE core.player CASCADE")
        cur.execute(
            """
            INSERT INTO core.player (
                retro_id, mlbam_id, bbref_id, fangraphs_id, chadwick_uuid,
                last_name, first_name, birth_date, death_date
            )
            SELECT
                key_retro,
                key_mlbam,
                key_bbref,
                key_fangraphs,
                key_uuid,
                name_last,
                name_first,
                CASE WHEN birth_year IS NOT NULL AND birth_month IS NOT NULL
                          AND birth_day IS NOT NULL
                     THEN make_date(birth_year::integer, birth_month::integer, birth_day::integer)
                END,
                CASE WHEN death_year IS NOT NULL AND death_month IS NOT NULL
                          AND death_day IS NOT NULL
                     THEN make_date(death_year::integer, death_month::integer, death_day::integer)
                END
            FROM raw.register_people
            WHERE key_retro IS NOT NULL
            """
        )
        return cur.rowcount


def _build_games(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            r"""
            -- number/attendance/timeofgame only convert when the raw text is
            -- a plain non-negative number. Real raw.retrosheet_gameinfo rows
            -- confirmed to need this: "12000.0" (pandas coerces an int
            -- column with any missing values to float on read -- numeric
            -- cast handles that), "6500?" and "<1000" (Retrosheet's own
            -- uncertain-attendance annotations), and "-1.0" (Retrosheet's
            -- sentinel for unknown game duration, 188 rows). All become NULL
            -- rather than guessing a number -- a direct ::integer cast would
            -- error on all four instead.
            INSERT INTO core.game (
                retro_game_id, season, game_date, game_number,
                away_team_id, home_team_id, away_score, home_score,
                game_type, site, attendance, duration_minutes, day_night,
                winning_pitcher_id, losing_pitcher_id, save_pitcher_id
            )
            SELECT
                gi.gid,
                gi._season::integer,
                to_date(gi.date, 'YYYYMMDD'),
                CASE WHEN gi.number ~ '^[0-9]+(\.[0-9]+)?$' THEN gi.number::numeric::integer END,
                away_team.id,
                home_team.id,
                NULLIF(gi.vruns, '')::integer,
                NULLIF(gi.hruns, '')::integer,
                gi.gametype,
                gi.site,
                CASE WHEN gi.attendance ~ '^[0-9]+(\.[0-9]+)?$'
                     THEN gi.attendance::numeric::integer END,
                CASE WHEN gi.timeofgame ~ '^[0-9]+(\.[0-9]+)?$'
                     THEN gi.timeofgame::numeric::integer END,
                gi.daynight,
                wp.id,
                lp.id,
                sv.id
            FROM raw.retrosheet_gameinfo gi
            LEFT JOIN core.team away_team
                ON away_team.retro_team_id = gi.visteam
                AND gi._season::integer BETWEEN away_team.first_year AND away_team.last_year
            LEFT JOIN core.team home_team
                ON home_team.retro_team_id = gi.hometeam
                AND gi._season::integer BETWEEN home_team.first_year AND home_team.last_year
            LEFT JOIN core.player wp ON wp.retro_id = gi.wp
            LEFT JOIN core.player lp ON lp.retro_id = gi.lp
            LEFT JOIN core.player sv ON sv.retro_id = gi.save
            """
        )
        return cur.rowcount


def run() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        _check_prerequisites(conn)
        # game references team/player, so it must be cleared first — CASCADE
        # on team/player's TRUNCATE would otherwise also wipe game silently.
        with conn.cursor() as cur:
            cur.execute("TRUNCATE core.game")
        counts = {
            "core.team": _build_teams(conn),
            "core.player": _build_players(conn),
        }
        counts["core.game"] = _build_games(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows("core.player"),
        check_table_has_rows("core.team"),
        check_table_has_rows("core.game"),
    ]
