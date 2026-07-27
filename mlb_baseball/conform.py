"""Builds `core` (the conformed/dimensional layer) from already-ingested
`raw` tables — see docs/DECISIONS.md ADR-013/ADR-017/ADR-018 and
ARCHITECTURE.md "Layered schema". This is not a connector: it never touches
the network, and its job is joining data that's *already* landed, not
fetching new data. Driven by `mlb conform`, not `mlb ingest <source>`.

Full truncate-and-rebuild every run, not incremental — unlike raw's
per-season scoped replace, there's no meaningful "what changed" for a
cross-source join at this row count. This also sidesteps the whole class of
bug ADR-010 documents: nothing here can partially overwrite another chunk's
data, because there are no chunks — one INSERT...SELECT per table, every
time.

Depends on raw tables that must already have data (checked explicitly
before running, not assumed):
    raw.retrosheet_team    (from `mlb ingest retrosheet_reference`)
    raw.register_people    (from `mlb ingest register`)
    raw.retrosheet_gameinfo (from `mlb ingest retrosheet`)

core.player/team/game are always built from the sources above. core.play
and core.pitch pull from raw.retrosheet_event, raw.mlb_playbyplay, and
raw.statcast_pitch, but those aren't hard prerequisites — each is genuinely
optional (a fresh clone may not have run retrosheet_event yet, since it
needs the Chadwick CLI tools; mlb_playbyplay only exists once mlb_api's
current season has started; statcast_pitch only exists once statcast has
been bootstrapped) — each is skipped with a clear message, not a failure,
if its source table doesn't exist yet (see `_build_plays`/`_build_pitches`).

core.game.game_pk (MLB's own numeric game ID, distinct from retro_game_id)
is backfilled from raw.mlb_schedule via a (game_date, away team, home team)
match — the bridge that lets game_pk-keyed data (mlb_playbyplay,
statcast_pitch) join back to core.game. Confirmed directly against real
production data at an ~85% match rate, consistent across eras — the
remainder stays NULL rather than a guessed value (see migration
0006_core_play_pitch.sql).
"""

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_table_exists, check_table_has_rows
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
        retro_count = cur.rowcount

    # core.game above is entirely Retrosheet-sourced — real gap, found by
    # a real production run: Retrosheet's most recent published season is
    # 2025 (confirmed: raw.retrosheet_gameinfo has nothing for 2026), so
    # without this, core.game has zero rows for the current season, and the
    # MLB-API-sourced half of core.play (joined via game_pk) silently drops
    # every row for that season instead of erroring — a real correctness
    # bug, not just a coverage gap. This backfills seasons Retrosheet
    # doesn't have yet from raw.mlb_schedule instead. retro_game_id is
    # synthesized ('MLB' + game_pk, Retrosheet's own IDs never take that
    # form) since these games have no Retrosheet ID at all. Pitcher FKs stay
    # NULL: raw.mlb_schedule's winning/losing/save pitcher fields are free
    # text names, not IDs, and matching those reliably to core.player isn't
    # attempted here — nullable is the honest answer, not a guessed match.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                r"""
                INSERT INTO core.game (
                    retro_game_id, game_pk, season, game_date, game_number,
                    away_team_id, home_team_id, away_score, home_score,
                    game_type, site
                )
                SELECT
                    'MLB' || ms.game_id,
                    ms.game_id,
                    ms._season::integer,
                    ms.game_date::date,
                    NULLIF(ms.game_num, '')::numeric::integer,
                    away.id,
                    home.id,
                    CASE WHEN ms.away_score ~ '^[0-9]+(\.[0-9]+)?$'
                         THEN ms.away_score::numeric::integer END,
                    CASE WHEN ms.home_score ~ '^[0-9]+(\.[0-9]+)?$'
                         THEN ms.home_score::numeric::integer END,
                    ms.game_type,
                    ms.venue_name
                FROM (
                    -- 1,199 game_ids (confirmed) appear twice in
                    -- raw.mlb_schedule under two different dates, e.g.
                    -- game 824912 listed under both 2026-06-16 and
                    -- 2026-06-17 — a suspended-and-resumed game sharing one
                    -- gamePk across both dates, a real MLB Stats API
                    -- characteristic, not an ingestion bug. DISTINCT ON
                    -- keeps the later date (the actual completion) per
                    -- game_id, deterministically.
                    SELECT DISTINCT ON (game_id) *
                    FROM raw.mlb_schedule
                    ORDER BY game_id, game_date DESC
                ) ms
                LEFT JOIN core.team away
                    ON away.city || ' ' || away.nickname = ms.away_name
                    AND ms._season::integer BETWEEN away.first_year AND away.last_year
                LEFT JOIN core.team home
                    ON home.city || ' ' || home.nickname = ms.home_name
                    AND ms._season::integer BETWEEN home.first_year AND home.last_year
                WHERE ms.status NOT IN
                    ('Scheduled', 'Postponed', 'Cancelled', 'Pre-Game', 'Warmup')
                    AND NOT EXISTS (
                        SELECT 1 FROM raw.retrosheet_gameinfo gi WHERE gi._season = ms._season
                    )
                """
            )
            return retro_count + cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_schedule not present yet — core.game has no current-season rows")
        return retro_count


def _backfill_game_pk(conn: psycopg.Connection) -> int:
    # Uses conn.transaction() (a SAVEPOINT, since run() already has an open
    # transaction) rather than conn.rollback() on failure — plain rollback()
    # would undo the *whole* transaction, including the teams/players/games
    # _build_games already inserted earlier in this same run(). A SAVEPOINT
    # scopes the rollback to just this optional step. Found by a real test
    # failure: core.game.game_pk backfill being skipped (raw.mlb_schedule
    # not loaded yet) was silently wiping out core.game entirely.
    try:
        with conn.transaction(), conn.cursor() as cur:
            # FROM-list uses implicit (comma) joins, not explicit JOIN...ON,
            # because Postgres's UPDATE...FROM doesn't allow the UPDATE
            # target (g) to be referenced inside a JOIN...ON clause within
            # the FROM list — only in WHERE. Found the hard way: the
            # explicit-JOIN version raised UndefinedTable ("invalid
            # reference to FROM-clause entry for table g"), which this
            # function's own except clause silently absorbed as "table
            # doesn't exist yet" — a real bug masking a real bug, caught by
            # actually reading the exception's message during debugging
            # rather than trusting the except clause's assumption.
            cur.execute(
                """
                UPDATE core.game g
                SET game_pk = ms.game_id
                FROM raw.mlb_schedule ms, core.team away, core.team home
                WHERE ms.game_date::date = g.game_date
                    AND ms.away_name = away.city || ' ' || away.nickname
                    AND ms.home_name = home.city || ' ' || home.nickname
                    AND away.id = g.away_team_id
                    AND home.id = g.home_team_id
                """
            )
            return cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_schedule not present yet — skipping core.game.game_pk backfill")
        return 0


def _build_plays(conn: psycopg.Connection) -> int:
    # Not self-truncating: run() truncates core.play before core.game (FK
    # ordering — core.play references core.game), same reason _build_games
    # doesn't self-truncate core.game either.
    #
    # Each source's INSERT gets its own conn.transaction() (a SAVEPOINT,
    # since run() already has an open transaction) rather than
    # conn.rollback() on failure — see _backfill_game_pk for why plain
    # rollback() is wrong here (it would undo the whole run(), not just this
    # optional step).
    total = 0
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.play (
                    game_id, season, source, play_index, inning, half_inning,
                    batter_id, pitcher_id, event_code, event_desc,
                    away_score, home_score
                )
                SELECT
                    g.id,
                    ev._season::integer,
                    'retrosheet',
                    NULLIF(ev.event_id, '')::integer,
                    NULLIF(ev.inn_ct, '')::integer,
                    CASE ev.bat_home_id WHEN '0' THEN 'top' WHEN '1' THEN 'bottom' END,
                    bat.id,
                    pit.id,
                    ev.event_cd,
                    ev.event_tx,
                    NULLIF(ev.away_score_ct, '')::integer,
                    NULLIF(ev.home_score_ct, '')::integer
                FROM (
                    -- 1,872 games (confirmed, all Negro-League-era) are
                    -- published byte-identical in both the general
                    -- play-by-play archive and the dedicated Negro League
                    -- archive (different _scope values, same game_id +
                    -- event_id) — real duplication in Retrosheet's own
                    -- source data, not an ingestion bug. DISTINCT ON keeps
                    -- one copy per (game_id, event_id) deterministically;
                    -- content is identical either way, confirmed directly
                    -- against a real sample before writing this.
                    SELECT DISTINCT ON (game_id, event_id) *
                    FROM raw.retrosheet_event
                    ORDER BY game_id, event_id, _scope
                ) ev
                JOIN core.game g ON g.retro_game_id = ev.game_id
                LEFT JOIN core.player bat ON bat.retro_id = ev.bat_id
                LEFT JOIN core.player pit ON pit.retro_id = ev.pit_id
                """
            )
            total += cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.retrosheet_event not present yet — skipping its core.play rows")

    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.play (
                    game_id, season, source, play_index, inning, half_inning,
                    batter_id, pitcher_id, event_code, event_desc,
                    away_score, home_score, balls, strikes, outs
                )
                SELECT
                    g.id,
                    pbp._season::integer,
                    'mlb_api',
                    NULLIF(pbp.at_bat_index, '')::integer,
                    NULLIF(pbp.inning, '')::integer,
                    pbp.half_inning,
                    bat.id,
                    pit.id,
                    pbp.event_type,
                    pbp.event,
                    NULLIF(pbp.away_score, '')::integer,
                    NULLIF(pbp.home_score, '')::integer,
                    NULLIF(pbp.balls, '')::integer,
                    NULLIF(pbp.strikes, '')::integer,
                    NULLIF(pbp.outs, '')::integer
                FROM raw.mlb_playbyplay pbp
                JOIN core.game g ON g.game_pk = pbp.game_pk
                LEFT JOIN core.player bat ON bat.mlbam_id = pbp.batter_id
                LEFT JOIN core.player pit ON pit.mlbam_id = pbp.pitcher_id
                """
            )
            total += cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_playbyplay not present yet — skipping its core.play rows")
    return total


def _build_pitches(conn: psycopg.Connection) -> int:
    # Not self-truncating — see _build_plays. Uses conn.transaction() (a
    # SAVEPOINT) rather than conn.rollback() on failure — see
    # _backfill_game_pk for why plain rollback() is wrong here.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.pitch (
                    game_id, season, at_bat_number, pitch_number, inning,
                    batter_id, pitcher_id, pitch_type, pitch_name,
                    release_speed, release_spin_rate, launch_speed,
                    launch_angle, hit_distance, description, event
                )
                SELECT
                    g.id,
                    sp.game_year::integer,
                    NULLIF(sp.at_bat_number, '')::integer,
                    NULLIF(sp.pitch_number, '')::integer,
                    NULLIF(sp.inning, '')::integer,
                    bat.id,
                    pit.id,
                    sp.pitch_type,
                    sp.pitch_name,
                    NULLIF(sp.release_speed, '')::numeric,
                    NULLIF(sp.release_spin_rate, '')::numeric,
                    NULLIF(sp.launch_speed, '')::numeric,
                    NULLIF(sp.launch_angle, '')::numeric,
                    NULLIF(sp.hit_distance_sc, '')::numeric,
                    sp.description,
                    sp.events
                FROM raw.statcast_pitch sp
                JOIN core.game g ON g.game_pk = sp.game_pk
                LEFT JOIN core.player bat ON bat.mlbam_id = sp.batter
                LEFT JOIN core.player pit ON pit.mlbam_id = sp.pitcher
                """
            )
            return cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.statcast_pitch not present yet — core.pitch left empty")
        return 0


def run() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        _check_prerequisites(conn)
        # game references team/player, so it must be cleared first — CASCADE
        # on team/player's TRUNCATE would otherwise also wipe game silently.
        # play/pitch reference game in turn — Postgres requires truncating a
        # table together with everything that references it in the same
        # statement (a separate TRUNCATE core.game afterward raises
        # FeatureNotSupported even if play/pitch are already empty), so all
        # three go in one TRUNCATE, not three sequential ones.
        with conn.cursor() as cur:
            cur.execute("TRUNCATE core.play, core.pitch, core.game")
        counts = {
            "core.team": _build_teams(conn),
            "core.player": _build_players(conn),
        }
        counts["core.game"] = _build_games(conn)
        _backfill_game_pk(conn)
        counts["core.play"] = _build_plays(conn)
        counts["core.pitch"] = _build_pitches(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows("core.player"),
        check_table_has_rows("core.team"),
        check_table_has_rows("core.game"),
        check_table_exists("core.play"),
        check_table_exists("core.pitch"),
    ]
