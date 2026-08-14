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

core.market/core.player_war/core.play's win-probability columns (migration
0008, ADR-028) close a real gap found reviewing this file: every source
ADR-020 onward added (win probability, WAR, Polymarket, Kalshi) sat in raw
with no bridge to core at all. _build_market's Polymarket/Kalshi matching
is done in Python, not SQL, because both sources' team/date info is nested
inside columns raw.polymarket_event/raw.kalshi_market store as Python-repr
text (load_dataframe has no JSON-aware serialization — see ADR-026/027) —
ast.literal_eval in Python is far more robust here than fragile string
matching against repr'd dicts in SQL. core.market.implied_probability
(ADR-052, issue #1) resolves to the latest raw.polymarket_snapshot/
raw.kalshi_snapshot row captured strictly before that specific game's real
start time (raw.mlb_schedule.game_datetime, via core.game.game_pk) — never
the current/settled price _polymarket_market_rows/_kalshi_market_rows used
to read directly, which for a decided game already reflects the outcome
and would leak straight into a Phase 2 model. NULL, not a guess, for any
market with no qualifying pre-game snapshot.

core.venue/core.standing (migration 0010) close the same class of gap for
raw.retrosheet_park, raw.mlb_venue, and raw.mlb_standing — all fully
ingested, none previously bridged to core. core.venue is keyed on
Retrosheet's own parkid (an exact match already stored, unused, in
raw.retrosheet_gameinfo.site/core.game.site — no fuzzy matching needed,
unlike team/game_pk resolution); MLB's richer venue catalog (lat/long,
capacity, turf/roof type, dimensions) is a best-effort enrichment by exact
name match, left NULL otherwise. core.game also gains Retrosheet's own
per-game weather columns (temp/wind/sky/precip/field condition) — landed
in raw.retrosheet_gameinfo the whole time, never used until this change.
core.standing resolves team_id via core.team.mlb_team_id, so
_build_standings must run after _backfill_mlb_team_id, not before.
"""

import re
from ast import literal_eval
from bisect import bisect_left
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import (
    Check,
    check_grouped_no_duplicates,
    check_join_coverage,
    check_no_duplicate_key,
    check_table_exists,
    check_table_has_rows,
    check_totals_reconcile,
)
from mlb_baseball.ingest import track_run
from mlb_baseball.sql import read_sql

SOURCE = "core"

# Kalshi's own KXMLBGAME market-ticker team-code suffixes -> Retrosheet's
# Seed data for core.team_alias (migration 0009) — only needed for
# external sources with no shared ID scheme with MLB at all (Polymarket's
# team-name strings, Kalshi's ticker codes). Anything MLB-API-sourced uses
# core.team.mlb_team_id instead — a stable numeric anchor, not a name to
# string-match (see _backfill_mlb_team_id) — so this list stays small and
# only covers the handful of names/codes these two market platforms
# actually use, not an attempt to reconstruct every source's naming.
#
# (retro_team_id, alias, source) — every alias here was confirmed present
# in real production data before being added, not guessed:
# - Kalshi ticker codes: `SELECT DISTINCT` against raw.kalshi_market's
#   tickers ("AL"/"NL", also seen in that query, are a different
#   non-team market type sharing the KXMLBGAME series, deliberately
#   excluded).
# - "rebrand" aliases: confirmed by reading raw.mlb_team_history directly
#   — Retrosheet's own TEAMABR.TXT still lists these 3 teams under their
#   OLDER recorded nickname (Tampa Bay "Devil Rays", Anaheim "Angels",
#   Cleveland "Indians") even for the current (last_year=9999) era row,
#   and the Athletics' 2025 relocation means MLB's own schedule data now
#   lists them as bare "Athletics" with no city at all — confirmed both
#   Polymarket and Kalshi use these current/bare forms, not core.team's
#   stored (stale) name.
_TEAM_ALIAS_SEED: list[tuple[str, str, str]] = [
    ("OAK", "ATH", "kalshi_ticker"),
    ("ATL", "ATL", "kalshi_ticker"),
    ("ARI", "AZ", "kalshi_ticker"),
    ("BAL", "BAL", "kalshi_ticker"),
    ("BOS", "BOS", "kalshi_ticker"),
    ("CHN", "CHC", "kalshi_ticker"),
    ("CIN", "CIN", "kalshi_ticker"),
    ("CLE", "CLE", "kalshi_ticker"),
    ("COL", "COL", "kalshi_ticker"),
    ("CHA", "CWS", "kalshi_ticker"),
    ("DET", "DET", "kalshi_ticker"),
    ("HOU", "HOU", "kalshi_ticker"),
    ("KCA", "KC", "kalshi_ticker"),
    ("ANA", "LAA", "kalshi_ticker"),
    ("LAN", "LAD", "kalshi_ticker"),
    ("MIA", "MIA", "kalshi_ticker"),
    ("MIL", "MIL", "kalshi_ticker"),
    ("MIN", "MIN", "kalshi_ticker"),
    ("NYN", "NYM", "kalshi_ticker"),
    ("NYA", "NYY", "kalshi_ticker"),
    ("PHI", "PHI", "kalshi_ticker"),
    ("PIT", "PIT", "kalshi_ticker"),
    ("SDN", "SD", "kalshi_ticker"),
    ("SEA", "SEA", "kalshi_ticker"),
    ("SFN", "SF", "kalshi_ticker"),
    ("SLN", "STL", "kalshi_ticker"),
    ("TBA", "TB", "kalshi_ticker"),
    ("TEX", "TEX", "kalshi_ticker"),
    ("TOR", "TOR", "kalshi_ticker"),
    ("WAS", "WSH", "kalshi_ticker"),
    ("TBA", "Rays", "rebrand"),
    ("TBA", "Tampa Bay Rays", "rebrand"),
    ("ANA", "Los Angeles Angels", "rebrand"),
    ("CLE", "Cleveland Guardians", "rebrand"),
    ("OAK", "Athletics", "rebrand"),
]

_MONTH_ABBR = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

# Polymarket's own daily-game slug format, confirmed directly:
# "mlb-tb-nyy-2026-05-23" -> game date 2026-05-23.
_POLYMARKET_SLUG_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})$")
# Kalshi's own event-ticker format, confirmed directly:
# "KXMLBGAME-26JUL281840AZPIT" -> yy=26, mon=JUL, dd=28 (time/teams follow,
# not needed here since each market's own ticker suffix already gives its
# team unambiguously).
_KALSHI_TICKER_DATE_RE = re.compile(r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})")
_KALSHI_TICKER_TEAM_RE = re.compile(r"-([A-Z]{2,4})$")

_AMBIGUOUS_FINAL_GAME_IDS_SQL = """
    SELECT game_id FROM raw.mlb_schedule
    WHERE status = 'Final'
    GROUP BY game_id
    HAVING count(*) > 1
"""

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
            (count,) = fetch_one(cur)
            if count == 0:
                missing.append(f"{table} is empty — run `{fix_command}` first")
    if missing:
        raise RuntimeError("core requires raw data that isn't loaded yet: " + "; ".join(missing))


def _build_teams(conn: psycopg.Connection) -> int:
    # core.team itself is truncated centrally by run()'s single consolidated
    # TRUNCATE, not here — see run()'s comment for why (avoids redundant
    # per-relation fsync passes over the same ~330 pitch/play partitions).
    with conn.cursor() as cur:
        cur.execute(read_sql("conform_team_insert.sql"))
        primary_count = cur.rowcount
    try:
        # run() already owns the outer transaction.  This savepoint keeps an
        # absent optional raw table from aborting that whole rebuild.
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(read_sql("conform_team_supplemental_insert.sql"))
            return primary_count + cur.rowcount
    except psycopg.errors.UndefinedTable:
        # TEAM{year}.TXT is an optional Retrosheet reference supplement.
        # Its absence must not stop a normal affiliated-major-league rebuild.
        print(
            "conform: raw.retrosheet_team0 not present yet — "
            "skipping supplemental team identities"
        )
        return primary_count


def _build_venues(conn: psycopg.Connection) -> int:
    # Retrosheet's own parkid is the primary key here, not MLB's numeric
    # venue_id -- it's the one with an exact, already-stored join key back
    # to core.game (raw.retrosheet_gameinfo.site), where MLB's venue
    # catalog has no shared ID with Retrosheet at all. mlb_venue_id and the
    # richer lat/long/capacity/turf/roof/dimension columns are a
    # best-effort enrichment: an exact case-insensitive name match against
    # raw.mlb_venue, left NULL where nothing matches exactly rather than
    # guessed -- same "leave it NULL, don't guess" precedent as
    # core.game.game_pk's own backfill. raw.mlb_venue is optional (a fresh
    # clone may not have bootstrapped mlb_api yet), so the enrichment is a
    # separate best-effort UPDATE after the base INSERT, not a JOIN inside
    # it -- same reasoning as _backfill_win_probability.
    # raw.retrosheet_park is optional, same as every other non-hard-
    # prerequisite raw table here — a fresh clone that's only bootstrapped
    # register/lahman/retrosheet's CSV product so far (the three hard
    # PREREQUISITES) won't have it yet.
    # core.venue itself is truncated centrally by run()'s single consolidated
    # TRUNCATE, not here — see run()'s comment for why.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(read_sql("conform_venue_insert.sql"))
            count = cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.retrosheet_park not present yet — core.venue left empty")
        return 0
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(read_sql("conform_venue_enrich.sql"))
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_venue not present yet — core.venue enrichment columns left NULL")
    return count


def _build_team_aliases(conn: psycopg.Connection) -> int:
    # core.team_alias itself is truncated centrally by run()'s single
    # consolidated TRUNCATE, not here — see run()'s comment for why.
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO core.team_alias (team_id, alias, source)
            SELECT id, %s, %s FROM core.team WHERE retro_team_id = %s AND last_year = 9999
            """,
            [(alias, source, retro_id) for retro_id, alias, source in _TEAM_ALIAS_SEED],
        )
        cur.execute("SELECT count(*) FROM core.team_alias")
        return fetch_one(cur)[0]


def _build_players(conn: psycopg.Connection) -> int:
    # core.player itself is truncated centrally by run()'s single
    # consolidated TRUNCATE, not here — see run()'s comment for why.
    with conn.cursor() as cur:
        cur.execute(read_sql("conform_player_insert.sql"))
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
                winning_pitcher_id, losing_pitcher_id, save_pitcher_id,
                venue_id, temp_f, wind_dir, wind_speed_mph, sky, precip, field_cond
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
                -- lower(): raw.retrosheet_gameinfo has one real casing
                -- inconsistency (HOM193508100, a 1935 Homestead Grays game,
                -- "Regular" vs "regular" everywhere else) -- confirmed via
                -- doctor's _check_gametype_casing. Raw stays source-faithful
                -- (uncorrected), but core is exactly where this project's
                -- own convention says relational correctness belongs, so a
                -- case-sensitive `WHERE game_type = 'regular'` downstream
                -- doesn't silently miss this one game.
                lower(gi.gametype),
                gi.site,
                CASE WHEN gi.attendance ~ '^[0-9]+(\.[0-9]+)?$'
                     THEN gi.attendance::numeric::integer END,
                CASE WHEN gi.timeofgame ~ '^[0-9]+(\.[0-9]+)?$'
                     THEN gi.timeofgame::numeric::integer END,
                gi.daynight,
                wp.id,
                lp.id,
                sv.id,
                venue.id,
                -- Retrosheet's own per-game weather columns -- confirmed
                -- present and well-filled (97%+ for wind/sky/precip, 71%
                -- for temp, 1900-2025) but sat entirely unused in raw
                -- until this change. "unknown" and the -1/-1.0 sentinel
                -- (windspeed's own unknown-value marker, same pattern as
                -- duration_minutes above) both fall through to NULL via
                -- the same digits-only regex guard used for attendance/
                -- timeofgame -- confirmed directly against real data, not
                -- assumed clean.
                CASE WHEN gi.temp ~ '^[0-9]+(\.[0-9]+)?$' THEN gi.temp::numeric::integer END,
                NULLIF(gi.winddir, 'unknown'),
                CASE WHEN gi.windspeed ~ '^[0-9]+(\.[0-9]+)?$'
                     THEN gi.windspeed::numeric::integer END,
                NULLIF(gi.sky, 'unknown'),
                NULLIF(gi.precip, 'unknown'),
                NULLIF(gi.fieldcond, 'unknown')
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
            LEFT JOIN core.venue venue ON venue.retro_park_id = gi.site
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
    # doesn't have yet from raw.mlb_schedule instead.  These rows have no
    # Retrosheet identifier, so retro_game_id stays NULL rather than carrying
    # a manufactured string. Pitcher FKs stay NULL: raw.mlb_schedule's
    # winning/losing/save pitcher fields are free
    # text names, not IDs, and matching those reliably to core.player isn't
    # attempted here — nullable is the honest answer, not a guessed match.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                r"""
                INSERT INTO core.game (
                    game_pk, season, game_date, game_number,
                    away_team_id, home_team_id, away_score, home_score,
                    game_type, site, venue_id
                )
                SELECT
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
                    -- MLB API's game_type is a single letter, not
                    -- Retrosheet's full word, in the exact same column —
                    -- confirmed by cross-checking against real dated games
                    -- (e.g. F=2025-09-30 Tigers@Guardians was the Wild Card
                    -- game), not guessed. Left unmapped (lower(), passed
                    -- through) is the honest fallback for anything not
                    -- confirmed, rather than a wrong guess.
                    CASE ms.game_type
                        WHEN 'R' THEN 'regular'
                        WHEN 'A' THEN 'allstar'
                        WHEN 'S' THEN 'spring'
                        WHEN 'E' THEN 'exhibition'
                        WHEN 'F' THEN 'wildcard'
                        WHEN 'D' THEN 'divisionseries'
                        WHEN 'L' THEN 'lcs'
                        WHEN 'W' THEN 'worldseries'
                        ELSE lower(ms.game_type)
                    END,
                    ms.venue_name,
                    venue.id
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
                -- core.venue.mlb_venue_id is an exact-name-match
                -- enrichment against raw.mlb_venue (see _build_venues) --
                -- confirmed directly this misses any venue renamed since
                -- Retrosheet's own park file was last updated (e.g. Daikin
                -- Park/ex-Minute Maid, Rate Field/ex-Guaranteed Rate
                -- Field, American Family Field/ex-Miller Park all fail to
                -- resolve this way even though raw.mlb_schedule's own
                -- numeric venue_id is correct) -- a real, separate,
                -- narrower gap than "no venue resolution at all", left as
                -- NULL rather than guessed via fuzzy name matching.
                -- MLB venue IDs are not a unique historical-park key: the
                -- API's "Wrigley Field" id 17 matches both Chicago's active
                -- park and Los Angeles' former park in raw.retrosheet_park.
                -- Restrict to the game season and pick a deterministic
                -- candidate so that one schedule game can never fan out into
                -- duplicate synthetic retro_game_id rows. No era-valid match
                -- stays NULL rather than attaching a game to the wrong park.
                LEFT JOIN LATERAL (
                    SELECT id
                    FROM core.venue
                    WHERE mlb_venue_id = NULLIF(ms.venue_id, '')::integer
                      AND (first_year IS NULL OR first_year <= ms._season::integer)
                      AND (last_year IS NULL OR last_year >= ms._season::integer)
                    ORDER BY first_year DESC NULLS LAST, id
                    LIMIT 1
                ) venue ON TRUE
                -- core.game holds completed facts only. A positive list is
                -- safer than excluding today's known unfinished statuses:
                -- new upstream status values cannot silently become facts.
                WHERE ms.status IN ('Final', 'Completed Early', 'Forfeit')
                    AND NOT EXISTS (
                        SELECT 1 FROM raw.retrosheet_gameinfo gi WHERE gi._season = ms._season
                    )
                """
            )
            return retro_count + cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_schedule not present yet — core.game has no current-season rows")
        return retro_count


def _build_completed_spring_games(conn: psycopg.Connection) -> int:
    """Add completed MLB Spring Training games absent from Retrosheet.

    Historical Retrosheet seasons contain regular/postseason game facts but
    not this complete MLB schedule population.  Each admitted row is anchored
    by the distinct MLB provider key; scheduled, live, cancelled, and
    postponed-only observations stay in raw schedule history.
    """
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                r"""
                INSERT INTO core.game (
                    game_pk, season, game_date, game_number,
                    away_team_id, home_team_id, away_score, home_score,
                    game_type, site
                )
                SELECT
                    ms.game_id,
                    ms._season::integer,
                    ms.game_date::date,
                    NULLIF(ms.game_num, '')::integer,
                    away.id,
                    home.id,
                    CASE WHEN ms.away_score ~ '^[0-9]+(\.[0-9]+)?$'
                         THEN ms.away_score::numeric::integer END,
                    CASE WHEN ms.home_score ~ '^[0-9]+(\.[0-9]+)?$'
                         THEN ms.home_score::numeric::integer END,
                    'spring',
                    ms.venue_name
                FROM (
                    SELECT DISTINCT ON (game_id) *
                    FROM raw.mlb_schedule
                    WHERE game_type = 'S'
                      AND status IN ('Final', 'Completed Early', 'Forfeit')
                    ORDER BY game_id, game_date DESC
                ) ms
                -- A stable MLB team ID can span multiple historical
                -- core.team eras.  Select one source-season-valid era per
                -- side so a schedule row cannot fan out into duplicate
                -- canonical game_pk attempts.
                LEFT JOIN LATERAL (
                    SELECT id
                    FROM core.team
                    WHERE mlb_team_id = NULLIF(ms.away_id, '')::integer
                      AND ms._season::integer BETWEEN first_year AND last_year
                    ORDER BY first_year DESC, id
                    LIMIT 1
                ) away ON TRUE
                LEFT JOIN LATERAL (
                    SELECT id
                    FROM core.team
                    WHERE mlb_team_id = NULLIF(ms.home_id, '')::integer
                      AND ms._season::integer BETWEEN first_year AND last_year
                    ORDER BY first_year DESC, id
                    LIMIT 1
                ) home ON TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM core.game existing WHERE existing.game_pk = ms.game_id
                )
                """
            )
            return cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        print("conform: MLB schedule team IDs not present yet — skipping Spring Training games")
        return 0


def _backfill_game_pk(conn: psycopg.Connection) -> int:
    # Uses conn.transaction() (a SAVEPOINT, since run() already has an open
    # transaction) rather than conn.rollback() on failure — plain rollback()
    # would undo the *whole* transaction, including the teams/players/games
    # _build_games already inserted earlier in this same run(). A SAVEPOINT
    # scopes the rollback to just this optional step. Found by a real test
    # failure: core.game.game_pk backfill being skipped (raw.mlb_schedule
    # not loaded yet) was silently wiping out core.game entirely.
    #
    # Real bug found in a later review, not hypothetical: matching on
    # (game_date, away team, home team) alone can't distinguish the two
    # games of a doubleheader — raw.mlb_schedule correctly carries two
    # separate rows (confirmed directly: 1925-07-07 Cardinals@Braves is
    # game_id 100003/game_num 1 and game_id 100004/game_num 2), but without
    # game_num in the match, both core.game rows collided onto the same
    # game_pk. Confirmed in production: 12,662 distinct game_pk values were
    # shared by 2 core.game rows each (25,347 rows total) — every one a
    # doubleheader — corrupting every downstream game_pk-keyed join
    # (mlb_playbyplay, statcast_pitch) for those games.
    #
    # A later production audit found that the two sources do NOT encode an
    # ordinary single game the same way: Retrosheet uses 0 while MLB's
    # schedule uses 1. The old COALESCE(..., 0) equality therefore matched
    # only a few dozen games per modern season and left roughly 98% of
    # 2008-2025 Statcast pitches without a core.game. Normalize 0/NULL to 1
    # on both sides; true doubleheaders retain their explicit 1/2 numbering.
    #
    # A second, distinct source-data quirk found later (mlb doctor's
    # check_no_duplicate_key flagged game_pk 123347 shared by two real,
    # distinct 1944 games a month apart — not a doubleheader, not the
    # suspended-and-resumed case below): raw.mlb_schedule itself sometimes
    # lists the *same* game_id under two different game_dates with *both*
    # rows marked status='Final' (confirmed directly: 216 distinct game_id
    # values in production have 2+ 'Final' rows — a genuine MLB Stats API
    # data quirk, likely a postponement/makeup-game bookkeeping artifact
    # from decades before the API existed, not something this pipeline can
    # correct at the source). Each date's row matches its own real core.game
    # row correctly (date is already part of the join condition below), but
    # both happen to carry the identical game_id, so both core.game rows
    # would get set to the same, now-ambiguous, game_pk. Excluded from the
    # backfill entirely — same "leave it NULL, don't guess" precedent as
    # core.play's statcast join above — rather than guessing which of the
    # two real games the id "really" belongs to.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                -- Build this mapping once, set-wise.  The old correlated
                -- candidate count was correct for a single schedule row but
                -- expensive at production scale and missed a key reused by
                -- a postponed observation that coincided with another real
                -- game.  A provider key is assignable only when *all* of
                -- its terminal schedule observations map to one core game.
                WITH terminal_schedule AS (
                    SELECT
                        ms.game_id,
                        ms.game_date::date AS game_date,
                        ms.away_name,
                        ms.home_name,
                        CASE
                            WHEN COALESCE(NULLIF(ms.game_num, '')::integer, 0) = 0 THEN 1
                            ELSE NULLIF(ms.game_num, '')::integer
                        END AS game_number
                    FROM raw.mlb_schedule ms
                    WHERE ms.status IN ('Final', 'Completed Early', 'Forfeit')
                ), candidates AS (
                    SELECT ms.game_id, g.id AS core_game_id
                    FROM terminal_schedule ms
                    JOIN core.team away
                      ON ms.away_name = away.city || ' ' || away.nickname
                    JOIN core.team home
                      ON ms.home_name = home.city || ' ' || home.nickname
                    JOIN core.game g
                      ON g.game_date = ms.game_date
                     AND g.away_team_id = away.id
                     AND g.home_team_id = home.id
                     AND CASE
                            WHEN COALESCE(g.game_number, 0) = 0 THEN 1
                            ELSE g.game_number
                         END = ms.game_number
                ), unambiguous AS (
                    SELECT game_id, min(core_game_id) AS core_game_id
                    FROM candidates
                    GROUP BY game_id
                    HAVING count(DISTINCT core_game_id) = 1
                )
                UPDATE core.game g
                SET game_pk = u.game_id
                FROM unambiguous u
                WHERE g.id = u.core_game_id
                  AND g.game_pk IS NULL
                """
            )
            return cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_schedule not present yet — skipping core.game.game_pk backfill")
        return 0


def _backfill_mlb_team_id(conn: psycopg.Connection) -> int:
    # Derives core.team.mlb_team_id — the team equivalent of
    # core.player.mlbam_id, a stable external numeric anchor rather than a
    # name to string-match — without any NEW string matching. For every
    # core.game row that already has a resolved game_pk (_backfill_game_pk
    # above) and a resolved away/home_team_id (_build_games' own string
    # match, which works fine for the many years a team's display name did
    # match), cross-reference raw.mlb_schedule's away_id/home_id for that
    # exact game_pk and take the majority vote per team. Confirmed directly
    # against production this is robust: of the top 15 teams by linked game
    # count, all but one showed a single distinct mlb_id across thousands
    # of games; the one exception (Cubs: 17,824 votes for 112 vs. 2 votes
    # for 146) traced to a real 2004 Hurricane Frances relocation (Marlins
    # "home" games moved to Wrigley, Marlins kept home-record credit in
    # raw.mlb_schedule while Retrosheet's retro_game_id reflects the actual
    # venue) — a genuine historical anomaly the majority vote correctly
    # treats as noise, not a bug to fix.
    # These are deliberately separate optional enrichments.  In particular,
    # a partial or older ``raw.mlb_team_history`` landing must never undo the
    # independently valid schedule-majority crosswalk.  Each savepoint also
    # keeps a failed optional statement from leaving the caller's transaction
    # aborted.
    schedule_count = 0
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                WITH votes AS (
                    SELECT
                        t.id AS team_id,
                        CASE WHEN g.away_team_id = t.id
                             THEN ms.away_id ELSE ms.home_id END AS mlb_id,
                        count(*) AS n
                    FROM core.team t
                    JOIN core.game g ON g.away_team_id = t.id OR g.home_team_id = t.id
                    JOIN raw.mlb_schedule ms ON ms.game_id = g.game_pk
                    WHERE g.game_pk IS NOT NULL
                    GROUP BY t.id, mlb_id
                ),
                ranked AS (
                    SELECT
                        team_id, mlb_id,
                        row_number() OVER (PARTITION BY team_id ORDER BY n DESC) AS rnk
                    FROM votes
                )
                UPDATE core.team t
                SET mlb_team_id = r.mlb_id::integer
                FROM ranked r
                WHERE r.team_id = t.id AND r.rnk = 1
                """
            )
            schedule_count = cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        # Schedule coverage is optional during an incremental bootstrap.
        print("conform: MLB schedule team IDs not present yet — skipping schedule backfill")

    history_count = 0
    try:
        with conn.transaction(), conn.cursor() as cur:
            # Some current MLB display names cannot safely string-match
            # Retrosheet's deliberately historical names (Rays/Devil Rays,
            # Angels/Anaheim, Athletics/Oakland). MLB's own team-history
            # payload provides the exact stable numeric anchor: team_code is
            # Retrosheet's code, team_id is MLB's ID. Require one distinct
            # ID across the applicable team era; leave any future ambiguity
            # unresolved instead of choosing a value.
            cur.execute(
                """
                WITH candidate AS (
                    SELECT t.id, min(h.team_id::integer) AS mlb_team_id
                    FROM core.team t
                    JOIN raw.mlb_team_history h
                      ON lower(h.team_code) = lower(t.retro_team_id)
                     AND h.team_id ~ '^[0-9]+$'
                     AND h.season ~ '^[0-9]{4}$'
                     -- MLB's historical team payload can lag one season
                     -- behind a relocation.  Retrosheet's official ATH
                     -- record starts in 2025 while the retained MLB record
                     -- carries the same exact code/id in 2024.  One adjacent
                     -- season is an explicit, bounded source-history bridge,
                     -- not a display-name guess.
                     AND h.season::integer BETWEEN t.first_year - 1 AND t.last_year + 1
                    WHERE t.mlb_team_id IS NULL
                    GROUP BY t.id
                    HAVING count(DISTINCT h.team_id) = 1
                )
                UPDATE core.team t
                SET mlb_team_id = candidate.mlb_team_id
                FROM candidate
                WHERE t.id = candidate.id
                """
            )
            history_count = cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        # Team history is an optional supplement to schedule evidence.
        print("conform: MLB team history not present yet — skipping history backfill")

    return schedule_count + history_count


def _backfill_game_pk_via_mlb_team_id(conn: psycopg.Connection) -> int:
    """Resolve games left unmatched by historical/display team-name drift.

    The first name-based game matches provide enough evidence for
    `_backfill_mlb_team_id` to build a stable numeric team crosswalk. This
    second pass then uses that crosswalk to resolve games MLB labels with a
    different franchise name, such as Guardians, Rays, or Angels in
    historical schedule rows. Ambiguous source IDs remain NULL.
    """
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE core.game g
                SET game_pk = ms.game_id
                FROM raw.mlb_schedule ms, core.team away, core.team home
                WHERE ms.game_date::date = g.game_date
                    AND ms.status IN ('Final', 'Completed Early', 'Forfeit')
                    AND away.id = g.away_team_id
                    AND home.id = g.home_team_id
                    AND away.mlb_team_id = NULLIF(ms.away_id, '')::integer
                    AND home.mlb_team_id = NULLIF(ms.home_id, '')::integer
                    AND CASE
                            WHEN COALESCE(NULLIF(ms.game_num, '')::integer, 0) = 0 THEN 1
                            ELSE NULLIF(ms.game_num, '')::integer
                        END
                        = CASE
                            WHEN COALESCE(g.game_number, 0) = 0 THEN 1
                            ELSE g.game_number
                        END
                    AND 1 = (
                        SELECT count(*)
                        FROM core.game candidate
                        JOIN core.team candidate_away ON candidate_away.id = candidate.away_team_id
                        JOIN core.team candidate_home ON candidate_home.id = candidate.home_team_id
                        WHERE candidate.game_date = ms.game_date::date
                          AND candidate_away.mlb_team_id = NULLIF(ms.away_id, '')::integer
                          AND candidate_home.mlb_team_id = NULLIF(ms.home_id, '')::integer
                          AND CASE
                                WHEN COALESCE(candidate.game_number, 0) = 0 THEN 1
                                ELSE candidate.game_number
                              END = CASE
                                WHEN COALESCE(NULLIF(ms.game_num, '')::integer, 0) = 0 THEN 1
                                ELSE NULLIF(ms.game_num, '')::integer
                              END
                    )
                    AND g.game_pk IS NULL
                    AND ms.game_id NOT IN ({_AMBIGUOUS_FINAL_GAME_IDS_SQL})
                """
            )
            return cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        print(
            "conform: MLB schedule team IDs not present yet — "
            "skipping second core.game.game_pk backfill"
        )
        return 0


def _backfill_game_pk_via_exact_final_score(conn: psycopg.Connection) -> int:
    """Resolve a last, narrow class of provider game-number disagreement.

    Retrosheet's zero game number normally means a single game, while the MLB
    schedule can label an otherwise identical doubleheader game as number two.
    This fallback requires one terminal schedule observation and one canonical
    candidate matching season, date, both numeric team IDs, and both final
    scores.  It therefore cannot turn a date/name similarity into a guess.
    """
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                WITH terminal_schedule AS (
                    SELECT
                        ms.game_id,
                        ms.game_date::date AS game_date,
                        NULLIF(ms.away_id, '')::integer AS away_mlb_team_id,
                        NULLIF(ms.home_id, '')::integer AS home_mlb_team_id,
                        ms.away_score::numeric::integer AS away_score,
                        ms.home_score::numeric::integer AS home_score,
                        ms._season::integer AS season
                    FROM raw.mlb_schedule ms
                    WHERE ms.game_type = 'R'
                      AND ms.status IN ('Final', 'Completed Early', 'Forfeit')
                      AND ms.away_score ~ '^[0-9]+(\\.[0-9]+)?$'
                      AND ms.home_score ~ '^[0-9]+(\\.[0-9]+)?$'
                ), singly_observed AS (
                    SELECT game_id, min(game_date) AS game_date,
                           min(away_mlb_team_id) AS away_mlb_team_id,
                           min(home_mlb_team_id) AS home_mlb_team_id,
                           min(away_score) AS away_score, min(home_score) AS home_score,
                           min(season) AS season
                    FROM terminal_schedule
                    GROUP BY game_id
                    HAVING count(*) = 1
                ), candidates AS (
                    SELECT ms.game_id, g.id AS core_game_id
                    FROM singly_observed ms
                    JOIN core.team away ON away.mlb_team_id = ms.away_mlb_team_id
                    JOIN core.team home ON home.mlb_team_id = ms.home_mlb_team_id
                    JOIN core.game g
                      ON g.season = ms.season
                     AND g.game_date = ms.game_date
                     AND g.away_team_id = away.id
                     AND g.home_team_id = home.id
                     AND g.away_score = ms.away_score
                     AND g.home_score = ms.home_score
                    WHERE g.game_pk IS NULL
                ), unambiguous AS (
                    SELECT game_id, min(core_game_id) AS core_game_id
                    FROM candidates
                    GROUP BY game_id
                    HAVING count(DISTINCT core_game_id) = 1
                )
                UPDATE core.game g
                SET game_pk = u.game_id
                FROM unambiguous u
                WHERE g.id = u.core_game_id
                  AND g.game_pk IS NULL
                """
            )
            return cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        print("conform: schedule fields unavailable — skipping exact-score game-key fallback")
        return 0


def _backfill_team_ids_via_mlb_id(conn: psycopg.Connection) -> int:
    # Uses the mlb_team_id crosswalk _backfill_mlb_team_id just built to
    # fix core.game rows _build_games' string match missed — e.g. the
    # Athletics' 2025 relocation: MLB's own schedule now lists them as
    # bare "Athletics" (no city), which no longer string-matches
    # core.team's "Oakland Athletics", leaving away/home_team_id NULL for
    # 42 real 2025+ rows confirmed directly against production.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                UPDATE core.game g
                SET away_team_id = t.id
                FROM raw.mlb_schedule ms, core.team t
                WHERE g.game_pk = ms.game_id AND g.away_team_id IS NULL
                    AND t.mlb_team_id = ms.away_id::integer
                """
            )
            n = cur.rowcount
            cur.execute(
                """
                UPDATE core.game g
                SET home_team_id = t.id
                FROM raw.mlb_schedule ms, core.team t
                WHERE g.game_pk = ms.game_id AND g.home_team_id IS NULL
                    AND t.mlb_team_id = ms.home_id::integer
                """
            )
            return n + cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        print("conform: raw.mlb_schedule not present yet — skipping core.game team_id backfill")
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


def _backfill_win_probability(conn: psycopg.Connection) -> int:
    """A separate UPDATE, not a LEFT JOIN inside _build_plays' own INSERT —
    a LEFT JOIN still requires the joined table to exist for Postgres to
    plan the query at all, which would make raw.mlb_win_prob's mere
    existence a hard requirement for landing ANY mlb_api-sourced play, not
    the optional, best-effort enrichment it's meant to be. Found by a real
    test failure, not anticipated: a fresh raw.mlb_playbyplay with no
    raw.mlb_win_prob yet made the whole mlb_api half of core.play silently
    disappear. Same conn.transaction() SAVEPOINT reasoning as
    _backfill_game_pk — this must not roll back core.play rows already
    inserted this run if raw.mlb_win_prob doesn't exist yet."""
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                UPDATE core.play p
                SET home_win_probability = NULLIF(wp.home_win_probability, '')::numeric,
                    away_win_probability = NULLIF(wp.away_win_probability, '')::numeric
                FROM raw.mlb_win_prob wp, core.game g
                WHERE p.source = 'mlb_api'
                    AND p.game_id = g.id
                    AND g.game_pk = wp.game_pk
                    AND wp.at_bat_index::integer = p.play_index
                """
            )
            return cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.mlb_win_prob not present yet — core.play's win probability left NULL")
        return 0


def _build_pitches(conn: psycopg.Connection) -> int:
    # Not self-truncating — see _build_plays. Uses conn.transaction() (a
    # SAVEPOINT) rather than conn.rollback() on failure — see
    # _backfill_game_pk for why plain rollback() is wrong here.
    #
    # LEFT JOIN core.game, not an inner JOIN — a real bug found in a later
    # review: an inner join here silently dropped every raw.statcast_pitch
    # row whose game_pk didn't resolve to a core.game row (2,535,802 of
    # 13,396,090 real production rows, 18.9%, confirmed directly), with no
    # trace and no health-check signal. Same class of bug as
    # core.player_war's inner join (fixed earlier this session) — land the
    # row with an honest NULL game_id instead of vanishing it, consistent
    # with core.game.game_pk's own "leave it NULL, don't guess" precedent.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.pitch (
                    game_id, source_game_pk, season, at_bat_number, pitch_number, inning,
                    batter_id, pitcher_id, pitch_type, pitch_name,
                    release_speed, release_spin_rate, launch_speed,
                    launch_angle, hit_distance, description, event
                )
                SELECT
                    g.id,
                    NULLIF(sp.game_pk, ''),
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
                LEFT JOIN core.game g ON g.game_pk = sp.game_pk
                LEFT JOIN core.player bat ON bat.mlbam_id = sp.batter
                LEFT JOIN core.player pit ON pit.mlbam_id = sp.pitcher
                """
            )
            return cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.statcast_pitch not present yet — core.pitch left empty")
        return 0


def _team_lookup(conn: psycopg.Connection) -> dict[str, int]:
    # One unified alias -> team_id dict, not the old by_name/by_retro_id
    # pair: core.team's own "city nickname" string plus every seeded
    # core.team_alias row (Kalshi ticker codes, rebrand names) all resolve
    # the same way now, since aliases are just more strings that mean the
    # same team. Doesn't need core.team.mlb_team_id at all — that's for
    # resolving core.game.away/home_team_id from MLB-sourced data, a
    # different join (see _backfill_team_ids_via_mlb_id); Polymarket/Kalshi
    # have no MLB numeric ID to key off of, hence this table.
    with conn.cursor() as cur:
        cur.execute("SELECT id, city, nickname FROM core.team")
        by_alias = {f"{city} {nickname}": team_id for team_id, city, nickname in cur.fetchall()}
        cur.execute("SELECT team_id, alias FROM core.team_alias")
        by_alias.update({alias: team_id for team_id, alias in cur.fetchall()})
    return by_alias


def _game_lookup(
    conn: psycopg.Connection,
) -> tuple[dict[tuple, int], dict[tuple, tuple[int, int]]]:
    """Two lookups built from one pass over core.game: `exact` keys on
    (date, away_team_id, home_team_id) for Polymarket (which gives both
    teams unambiguously); `fuzzy` keys on (date, one_team_id) -> (game_id,
    other_team_id) for Kalshi (whose ticker only reliably gives one team
    per market, see _kalshi_market_rows). Both drop any key matching more
    than one game (almost always a doubleheader) rather than guessing which
    game a market refers to — same "leave it NULL, don't guess" precedent
    as core.game.game_pk's own backfill."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, game_date, away_team_id, home_team_id FROM core.game")
        rows = cur.fetchall()
    by_teams: dict[tuple, list[int]] = {}
    by_date_team: dict[tuple, list[tuple[int, int]]] = {}
    for game_id, game_date, away_id, home_id in rows:
        if away_id is None or home_id is None:
            continue
        by_teams.setdefault((game_date, away_id, home_id), []).append(game_id)
        by_date_team.setdefault((game_date, away_id), []).append((game_id, home_id))
        by_date_team.setdefault((game_date, home_id), []).append((game_id, away_id))
    exact = {key: ids[0] for key, ids in by_teams.items() if len(ids) == 1}
    fuzzy = {key: matches[0] for key, matches in by_date_team.items() if len(matches) == 1}
    return exact, fuzzy


# ADR-052 (issue #1): core.market.implied_probability used to be whatever
# the most recently ingested raw.polymarket_outcome/raw.kalshi_market row
# said -- for a closed market, that's the *settled* price, which already
# reflects the actual outcome. Using it as a Phase 2 model feature would be
# straightforward leakage, not just missing data (confirmed directly with a
# real example while building this fix: market 3155100, the 2026-08-02
# PHI@BAL moneyline, moved from 0.555/0.445 on the morning of the game to
# 0.9995/0.0005 the very next day -- unmistakably a settled/near-settled
# price, not anything usable pre-game).
#
# raw.polymarket_snapshot/raw.kalshi_snapshot (ADR-049) capture a
# timestamped price for every open/active MLB market on each bootstrap()/
# update() run -- real pre-game data points, unlike the single current-state
# row _polymarket_market_rows/_kalshi_market_rows used to read from. This
# resolves each market's implied_probability to the latest snapshot
# strictly before that specific game's real start time (raw.mlb_schedule.
# game_datetime, joined via core.game.game_pk) instead -- honestly NULL,
# not the settled price, for any market with no qualifying snapshot (a game
# from before ADR-049 started capturing snapshots, a market that never
# matched a game at all, or a market whose only price history predates this
# codebase entirely -- raw.polymarket_price/raw.kalshi_candle, the *full*
# historical intraday backfill ADR-049 also built, haven't been
# owner-triggered yet; see issue #1's own "Revisit if"). Same "leave it
# NULL, don't guess" precedent as core.game.game_pk's own backfill.
def _market_game_start_times(conn: psycopg.Connection) -> dict[int, datetime]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.id, ms.game_datetime
            FROM core.game g
            JOIN raw.mlb_schedule ms ON ms.game_id = g.game_pk
            WHERE g.game_pk IS NOT NULL AND ms.game_datetime IS NOT NULL
            """
        )
        starts: dict[int, datetime] = {}
        for game_id, game_datetime in cur.fetchall():
            try:
                starts[game_id] = datetime.fromisoformat(game_datetime)
            except ValueError:
                continue
        return starts


def _latest_before(entries: list[tuple[datetime, Decimal]], cutoff: datetime) -> Decimal | None:
    """entries must be sorted ascending by timestamp (both snapshot lookups
    below build them via ORDER BY captured_at). bisect_left finds the first
    entry NOT strictly before cutoff; the qualifying value, if any, is
    immediately before that index."""
    idx = bisect_left(entries, (cutoff, Decimal(0))) if entries else 0
    if idx == 0:
        return None
    return entries[idx - 1][1]


def _polymarket_snapshot_lookup(conn: psycopg.Connection) -> dict[tuple[str, str], list]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT market_id, outcome, price, captured_at FROM raw.polymarket_snapshot "
            "WHERE price IS NOT NULL AND captured_at IS NOT NULL ORDER BY captured_at"
        )
        by_market_outcome: dict[tuple[str, str], list] = {}
        for market_id, outcome, price, captured_at in cur.fetchall():
            try:
                ts = datetime.fromisoformat(captured_at)
                value = Decimal(price)
            except (ValueError, InvalidOperation):
                continue
            by_market_outcome.setdefault((market_id, outcome), []).append((ts, value))
        return by_market_outcome


def _kalshi_snapshot_lookup(conn: psycopg.Connection) -> dict[str, list]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker, yes_bid_dollars, yes_ask_dollars, last_price_dollars, captured_at "
            "FROM raw.kalshi_snapshot WHERE captured_at IS NOT NULL ORDER BY captured_at"
        )
        by_ticker: dict[str, list] = {}
        for ticker, yes_bid, yes_ask, last_price, captured_at in cur.fetchall():
            price = _kalshi_implied_probability(last_price, yes_bid, yes_ask)
            if price is None:
                continue
            try:
                ts = datetime.fromisoformat(captured_at)
            except ValueError:
                continue
            by_ticker.setdefault(ticker, []).append((ts, price))
        return by_ticker


def _polymarket_market_rows(
    conn: psycopg.Connection,
    by_alias: dict[str, int],
    game_exact: dict[tuple, int],
    game_starts: dict[int, datetime],
    snapshots: dict[tuple[str, str], list],
) -> list[tuple]:
    rows: list[tuple] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.slug, e.teams, e.closed, m.id, m.volume, o.outcome
            FROM raw.polymarket_event e
            JOIN raw.polymarket_market m ON m.event_id = e.id
            JOIN raw.polymarket_outcome o ON o.market_id = m.id
            WHERE e.sport IS NOT NULL
            """
        )
        for slug, teams_text, closed, market_id, volume, outcome in cur.fetchall():
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
            game_date = date.fromisoformat(date_match.group(1))
            game_id = game_exact.get((game_date, away_id, home_id))
            if outcome == away.get("name"):
                team_id = away_id
            elif outcome == home.get("name"):
                team_id = home_id
            else:
                continue
            status = "closed" if str(closed).lower() == "true" else "open"
            # market_ref must be unique per row, not just per Polymarket
            # market — one market has two outcome rows (away/home), both
            # sharing the same market_id, and core.market has a UNIQUE
            # (source, market_ref) constraint. Kalshi doesn't need this:
            # it already issues a separate ticker per side.
            market_ref = f"{market_id}:{team_id}"
            start_time = game_starts.get(game_id) if game_id is not None else None
            implied_probability = (
                _latest_before(snapshots.get((market_id, outcome), []), start_time)
                if start_time is not None
                else None
            )
            rows.append(
                (game_id, "polymarket", market_ref, team_id, implied_probability, volume, status)
            )
    return rows


def _kalshi_implied_probability(
    last_price: str | None, yes_bid: str | None, yes_ask: str | None
) -> Decimal | None:
    # Prefer the last traded price; fall back to the yes-bid/ask midpoint
    # for a market that's never traded yet (a real production case: a
    # newly-listed market with real quotes but no trades).
    if last_price not in (None, "", "0.0000"):
        try:
            return Decimal(last_price)
        except InvalidOperation:
            return None
    try:
        return (Decimal(yes_bid or 0) + Decimal(yes_ask or 0)) / 2
    except InvalidOperation:
        return None


def _kalshi_market_rows(
    conn: psycopg.Connection,
    by_alias: dict[str, int],
    game_fuzzy: dict[tuple, tuple],
    game_starts: dict[int, datetime],
    snapshots: dict[str, list],
) -> list[tuple]:
    rows: list[tuple] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ticker, event_ticker, status, volume_fp
            FROM raw.kalshi_market
            WHERE event_ticker LIKE 'KXMLBGAME%'
            """
        )
        for ticker, event_ticker, status, volume in cur.fetchall():
            date_match = _KALSHI_TICKER_DATE_RE.match(event_ticker or "")
            team_match = _KALSHI_TICKER_TEAM_RE.search(ticker or "")
            if not date_match or not team_match:
                continue
            yy, mon_abbr, dd = date_match.groups()
            month = _MONTH_ABBR.get(mon_abbr)
            if month is None:
                continue
            game_date = date(2000 + int(yy), month, int(dd))
            team_id = by_alias.get(team_match.group(1))
            if team_id is None:
                continue
            match = game_fuzzy.get((game_date, team_id))
            game_id = match[0] if match else None
            start_time = game_starts.get(game_id) if game_id is not None else None
            implied_probability = (
                _latest_before(snapshots.get(ticker, []), start_time)
                if start_time is not None
                else None
            )
            rows.append((game_id, "kalshi", ticker, team_id, implied_probability, volume, status))
    return rows


def _build_market(conn: psycopg.Connection) -> int:
    by_alias = _team_lookup(conn)
    game_exact, game_fuzzy = _game_lookup(conn)
    try:
        with conn.transaction():
            game_starts = _market_game_start_times(conn)
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        # UndefinedColumn as well as UndefinedTable: raw.mlb_schedule can
        # exist without game_datetime (an older snapshot, or a test/partial
        # deployment -- same degrade-gracefully tolerance
        # _backfill_mlb_team_id already established for that table's
        # away_id/home_id columns). Either way, every implied_probability
        # below resolves NULL (no start time to compare a snapshot
        # against), same precedent as the snapshot lookups below.
        game_starts = {}

    # conn.transaction() (a SAVEPOINT), not a plain conn.rollback() on
    # failure — see _backfill_game_pk's comment for why: run() already has
    # an open transaction by the time this runs, and a plain rollback()
    # would undo everything _build_teams/_build_games already inserted
    # this same run, not just this optional step. Found the hard way, not
    # designed in from the start: an early version of this function used
    # conn.rollback() directly and silently wiped core.team/core.game
    # whenever raw.polymarket_event or raw.kalshi_market didn't exist yet.
    rows: list[tuple] = []
    try:
        with conn.transaction():
            polymarket_snapshots = _polymarket_snapshot_lookup(conn)
    except psycopg.errors.UndefinedTable:
        # raw.polymarket_snapshot didn't exist before ADR-049 -- every
        # Polymarket implied_probability below just resolves NULL instead
        # of a leaky settled price, not a crash.
        polymarket_snapshots = {}
    try:
        with conn.transaction():
            rows.extend(
                _polymarket_market_rows(
                    conn, by_alias, game_exact, game_starts, polymarket_snapshots
                )
            )
    except psycopg.errors.UndefinedTable:
        print("conform: raw.polymarket_event not present yet — skipping its core.market rows")
    try:
        with conn.transaction():
            kalshi_snapshots = _kalshi_snapshot_lookup(conn)
    except psycopg.errors.UndefinedTable:
        kalshi_snapshots = {}
    try:
        with conn.transaction():
            rows.extend(
                _kalshi_market_rows(conn, by_alias, game_fuzzy, game_starts, kalshi_snapshots)
            )
    except psycopg.errors.UndefinedTable:
        print("conform: raw.kalshi_market not present yet — skipping its core.market rows")

    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO core.market
                (game_id, source, market_ref, team_id, implied_probability, volume, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        return cur.rowcount


def _build_player_war(conn: psycopg.Connection) -> int:
    total = 0
    # Two separate statements, not one shared template — bref's own schema
    # genuinely differs between the two tables (confirmed by reading both
    # directly before writing this): batting has runs_above_avg/_off/_def,
    # pitching doesn't (its own WAR components are era_plus/ra/xra/bip
    # instead, a different stat vocabulary for pitchers, not an omission).
    #
    # LEFT JOIN core.player, not an inner JOIN — a real bug found in this
    # review: an inner join here silently drops any bref row whose
    # bbref_id doesn't resolve to a core.player row (517 of 126,418
    # batting rows, 368 distinct players, confirmed directly), with no
    # trace and no health-check signal. Every other optional resolution in
    # this file leaves an honest NULL instead of vanishing the row
    # (core.game.game_pk, core.market.game_id, etc.) — this brings
    # core.player_war in line with that same convention.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.player_war (
                    player_id, season, is_pitcher, team_code, war, waa,
                    war_replacement, runs_above_avg, runs_above_avg_offense,
                    runs_above_avg_defense
                )
                SELECT
                    p.id,
                    w.year_id::integer,
                    false,
                    w.team_id,
                    NULLIF(w.war, '')::numeric,
                    NULLIF(w.waa, '')::numeric,
                    NULLIF(w.war_rep, '')::numeric,
                    NULLIF(w.runs_above_avg, '')::numeric,
                    NULLIF(w.runs_above_avg_off, '')::numeric,
                    NULLIF(w.runs_above_avg_def, '')::numeric
                FROM raw.bref_war_batting w
                LEFT JOIN core.player p ON p.bbref_id = w.player_id
                """
            )
            total += cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.bref_war_batting not present yet — skipping")

    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.player_war (
                    player_id, season, is_pitcher, team_code, war, waa, war_replacement
                )
                SELECT
                    p.id,
                    w.year_id::integer,
                    true,
                    w.team_id,
                    NULLIF(w.war, '')::numeric,
                    NULLIF(w.waa, '')::numeric,
                    NULLIF(w.war_rep, '')::numeric
                FROM raw.bref_war_pitching w
                LEFT JOIN core.player p ON p.bbref_id = w.player_id
                """
            )
            total += cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.bref_war_pitching not present yet — skipping")
    return total


def _build_standings(conn: psycopg.Connection) -> int:
    # team_id resolves via core.team.mlb_team_id, not a second round of
    # string matching -- raw.mlb_standing.team_id is already MLB's own
    # numeric scheme, the same anchor ADR-029 built. Must run after
    # _backfill_mlb_team_id (see run()'s call order) or every row's
    # team_id would be NULL. 1969+ only -- MLB Stats API's own
    # standings_data() has no earlier coverage (confirmed in ADR-015);
    # pre-1969 win-loss is already available via raw.lahman_teams and
    # raw.retrosheet_gamelog, so this isn't a real coverage loss.
    # core.standing itself is truncated centrally by run()'s single
    # consolidated TRUNCATE, not here — see run()'s comment for why. That
    # also sidesteps what used to need a workaround: a per-source SAVEPOINT
    # rollback below (raw.mlb_standing not present) can no longer undo the
    # truncate, since it now happens before any per-source try/except runs.
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.standing (
                    team_id, season, division, div_rank, wins, losses,
                    games_back, wildcard_rank, wildcard_games_back,
                    league_rank, sport_rank
                )
                SELECT
                    t.id,
                    s._season::integer,
                    s.div_name,
                    CASE WHEN s.div_rank ~ '^[0-9]+$' THEN s.div_rank::integer END,
                    NULLIF(s.w, '')::integer,
                    NULLIF(s.l, '')::integer,
                    -- '-' is the division leader's own "0 games back"
                    -- marker (confirmed directly against real data,
                    -- alongside signed values like '-3.0'/'+16.0' for a
                    -- team ahead of its division/wildcard cutoff) --
                    -- a plain unsigned-digits regex would silently NULL
                    -- out exactly the leader rows, the ones most likely
                    -- to matter.
                    CASE WHEN s.gb = '-' THEN 0
                         WHEN s.gb ~ '^[+-]?[0-9]+(\\.[0-9]+)?$' THEN s.gb::numeric END,
                    -- Real bug found running this against production, not
                    -- hypothetical: wc_rank uses '-' too, but as "not
                    -- ranked" (a team completely out of wildcard
                    -- contention), not "rank 0" the way gb's '-' means
                    -- "0 games back" -- an honest NULL is the correct
                    -- reading here, not a guessed 0. div_rank/league_rank/
                    -- sport_rank confirmed clean (no '-' or other
                    -- non-digit values in production) but given the same
                    -- digits-only guard anyway rather than a bare NULLIF,
                    -- so a future source quirk fails safe (NULL) instead
                    -- of crashing the whole conform run the way this one
                    -- did.
                    CASE WHEN s.wc_rank ~ '^[0-9]+$' THEN s.wc_rank::integer END,
                    CASE WHEN s.wc_gb = '-' THEN 0
                         WHEN s.wc_gb ~ '^[+-]?[0-9]+(\\.[0-9]+)?$' THEN s.wc_gb::numeric END,
                    CASE WHEN s.league_rank ~ '^[0-9]+$' THEN s.league_rank::integer END,
                    CASE WHEN s.sport_rank ~ '^[0-9]+$' THEN s.sport_rank::integer END
                FROM raw.mlb_standing s
                LEFT JOIN core.team t
                    ON t.mlb_team_id = s.team_id::integer
                    AND s._season::integer BETWEEN t.first_year AND t.last_year
                """
            )
            return cur.rowcount
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        # A raw standing table can be absent on a partial bootstrap or come
        # from an older source shape. It is optional enrichment, so keep the
        # completed game rebuild usable and make the omission visible.
        print("conform: raw.mlb_standing not ready — skipping core.standing")
        return 0


def run() -> dict[str, int]:
    with (
        get_connection() as conn,
        track_run(conn, SOURCE, "bootstrap", workflow="exclusive") as result,
    ):
        _check_prerequisites(conn)
        # Every table in core/gold that anything else FKs into gets
        # truncated together, here, in one statement — not per-table via
        # separate `TRUNCATE ... CASCADE` calls in each _build_* function
        # (the shape this used to have). Two real reasons, not just
        # tidiness:
        #   1. Postgres requires truncating a table together with
        #      everything that references it in the same statement (a
        #      separate `TRUNCATE core.game` afterward raises
        #      FeatureNotSupported regardless of whether the referencing
        #      table has any rows — it's the FK's mere existence that
        #      blocks it, not row counts). CASCADE sidesteps that check by
        #      finding the referencing tables itself instead of them being
        #      named explicitly.
        #   2. CASCADE finding them itself is exactly the problem: TRUNCATE
        #      does a synchronous fsync per relation (confirmed via
        #      pg_stat_activity showing `DataFileImmediateSync` waits, not
        #      lock waits, while this was still three separate CASCADE
        #      statements). core.team/core.player/core.venue's old
        #      `TRUNCATE ... CASCADE` calls each walk the FK graph out to
        #      every one of core.play/core.pitch's ~330 season partitions
        #      (confirmed via pg_constraint — both batter_id and
        #      pitcher_id FK straight to core.player, not through
        #      core.game), and did so *in addition to* this statement
        #      already having emptied them moments earlier — three
        #      redundant full fsync passes over the same partitions,
        #      confirmed directly responsible for `mlb conform` spending
        #      tens of seconds to minutes in TRUNCATE alone. Naming every
        #      table once, here, means Postgres only fsyncs each relation
        #      once per run, not up to four times.
        # The full table list is exactly the transitive FK closure of
        # core.team/core.player/core.venue/core.game (confirmed via
        # pg_constraint, not guessed): core.game, core.market, core.play,
        # core.pitch, gold.game_feature reference core.game/team/player/
        # venue; core.standing/core.team_alias reference core.team;
        # core.player_war references core.player.
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE core.play, core.pitch, core.market, "
                "gold.game_feature, core.game, core.team, core.player, "
                "core.venue, core.standing, core.team_alias, "
                "core.player_war"
            )
        counts = {
            "core.team": _build_teams(conn),
            "core.player": _build_players(conn),
        }
        # Must run before _build_games — its LEFT JOIN needs core.venue
        # already populated to resolve venue_id.
        counts["core.venue"] = _build_venues(conn)
        counts["core.team_alias"] = _build_team_aliases(conn)
        counts["core.game"] = _build_games(conn)
        _backfill_game_pk(conn)
        # Order matters: mlb_team_id is derived from already-resolved
        # game_pk + away/home_team_id (majority vote), then immediately
        # used to fix the away/home_team_id rows the original string match
        # missed (e.g. the Athletics' bare "Athletics" name) — before
        # _build_market runs, so Polymarket/Kalshi matching sees the
        # corrected team_id on those games too. The game_pk resolution is
        # intentionally two-pass: exact historical names first establish
        # the numeric MLB team crosswalk, then that crosswalk resolves
        # display-name drift and the remaining team IDs.
        _backfill_mlb_team_id(conn)
        _backfill_game_pk_via_mlb_team_id(conn)
        _backfill_game_pk_via_exact_final_score(conn)
        _backfill_team_ids_via_mlb_id(conn)
        counts["core.game"] += _build_completed_spring_games(conn)
        # core.standing resolves team_id via mlb_team_id, so it must run
        # after both backfills above, not before.
        counts["core.standing"] = _build_standings(conn)
        counts["core.play"] = _build_plays(conn)
        _backfill_win_probability(conn)
        counts["core.pitch"] = _build_pitches(conn)
        counts["core.market"] = _build_market(conn)
        counts["core.player_war"] = _build_player_war(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows("core.player"),
        check_table_has_rows("core.team"),
        check_table_has_rows("core.team_alias"),
        check_table_has_rows("core.game"),
        check_table_exists("core.play"),
        check_table_exists("core.pitch"),
        check_table_exists("core.market"),
        check_table_exists("core.player_war"),
        # core.venue depends only on raw.retrosheet_park (optional, not a
        # hard PREREQUISITE) — check_table_exists, not _has_rows, since a
        # fresh clone that hasn't run retrosheet_reference yet leaves this
        # legitimately empty.
        check_table_exists("core.venue"),
        # core.standing depends on raw.mlb_standing (optional) — same
        # reasoning.
        check_table_exists("core.standing"),
        # Join-integrity safeguard added after a research-database review
        # found two real, silent bugs this way: a non-unique join key
        # (core.game.game_pk) letting two doubleheader games collide onto
        # one value, and an inner join silently dropping ~19% of
        # raw.statcast_pitch. These checks catch that whole bug class
        # automatically going forward, not just when someone happens to
        # ask the right question — see docs/DECISIONS.md ADR-030 follow-up.
        # Reports "table does not exist" (a FAIL) on a fresh clone that
        # hasn't run the relevant optional connector yet — consistent with
        # how every other check above already treats "never bootstrapped."
        check_no_duplicate_key("core.game", "game_pk"),
        check_join_coverage(
            "core.play retrosheet coverage",
            "SELECT count(*) FROM core.play WHERE source = 'retrosheet'",
            "SELECT count(*) FROM "
            "(SELECT DISTINCT ON (game_id, event_id) 1 FROM raw.retrosheet_event "
            "ORDER BY game_id, event_id, _scope) x",
        ),
        check_join_coverage(
            "core.play mlb_api coverage",
            "SELECT count(*) FROM core.play WHERE source = 'mlb_api'",
            "SELECT count(*) FROM raw.mlb_playbyplay",
        ),
        check_join_coverage(
            "core.pitch coverage",
            "SELECT count(*) FROM core.pitch",
            "SELECT count(*) FROM raw.statcast_pitch",
        ),
        check_join_coverage(
            "core.player_war batting coverage",
            "SELECT count(*) FROM core.player_war WHERE is_pitcher = false",
            "SELECT count(*) FROM raw.bref_war_batting",
        ),
        check_join_coverage(
            "core.player_war pitching coverage",
            "SELECT count(*) FROM core.player_war WHERE is_pitcher = true",
            "SELECT count(*) FROM raw.bref_war_pitching",
        ),
        # Cross-source reconciliation: core.game-derived team-season win
        # totals against Lahman's own, independently-compiled totals
        # (raw.lahman_teams, joined via retro_team_id — a completely
        # separate raw table from anything conform.py otherwise builds
        # from). tolerance=3 calibrated directly against real production
        # data: ~2,753 AL/NL team-seasons checked, the largest genuine
        # mismatch found was exactly 3 (1951/1962's famous NL pennant-
        # tiebreaker playoffs — Lahman's official standings count those
        # games, Retrosheet classifies them game_type='playoff', both
        # correct in their own convention, not a bug).
        #
        # Filtered to Lahman's own lgid IN ('AL', 'NL'), matching the team-
        # count check right below (added 2026-08-14, found via `mlb doctor`
        # while validating the production enrichment rollout: this check
        # was originally calibrated before core.game's real, extensive
        # Negro League coverage was reconciled here, and was missing the
        # filter its sibling check already documents needing -- without
        # it, this joins core.game's Retrosheet-sourced Negro League win
        # counts against raw.lahman_teams' OWN, separately and incompletely
        # compiled Negro League win totals (e.g. CAG-1920: Lahman's own row
        # says lgid='NNL', w=45; core.game's Retrosheet-sourced game log
        # for that team-season only covers a handful of games). Both
        # sources' Negro League coverage is real but independently
        # incomplete for this era -- comparing them isn't a meaningful
        # reconciliation of either source's correctness, the same reason
        # the team-count check already excludes them.
        check_totals_reconcile(
            "core.game team-season wins vs Lahman",
            """
            WITH core_totals AS (
                SELECT t.retro_team_id, cg.season,
                    count(*) FILTER (
                        WHERE cg.home_team_id = t.id AND cg.home_score > cg.away_score
                    ) + count(*) FILTER (
                        WHERE cg.away_team_id = t.id AND cg.away_score > cg.home_score
                    ) AS core_w
                FROM core.game cg
                JOIN core.team t ON cg.home_team_id = t.id OR cg.away_team_id = t.id
                WHERE cg.game_type = 'regular'
                    AND cg.home_score IS NOT NULL AND cg.away_score IS NOT NULL
                GROUP BY t.retro_team_id, cg.season
            )
            SELECT lt.teamidretro || '-' || lt.yearid, ct.core_w, lt.w::integer
            FROM raw.lahman_teams lt
            JOIN core_totals ct
                ON ct.retro_team_id = lt.teamidretro AND ct.season = lt.yearid::integer
            WHERE lt.lgid IN ('AL', 'NL')
            """,
            tolerance=3,
        ),
        # Doubleheader integrity, checked explicitly at the grouping level
        # the real bug (ADR-030's follow-up, migration 0011's game_pk-
        # overwrite guard) happened at: any (season, home team, away team,
        # date) with more than one core.game row must not have fewer
        # distinct game_pk values than rows that actually have one set —
        # that would mean two different games sharing one identity.
        check_grouped_no_duplicates(
            "core.game doubleheader identity",
            """
            SELECT season::text || '-' || home_team_id::text || '-'
                    || away_team_id::text || '-' || game_date::text,
                count(DISTINCT game_pk) FILTER (WHERE game_pk IS NOT NULL),
                count(*) FILTER (WHERE game_pk IS NOT NULL)
            FROM core.game
            WHERE home_team_id IS NOT NULL AND away_team_id IS NOT NULL
            GROUP BY season, home_team_id, away_team_id, game_date
            HAVING count(*) > 1
            """,
        ),
        # core.play's own natural key (game_id, source, play_index) can no
        # longer be a real UNIQUE constraint on its own — migration 0011
        # partitioned core.play by season, and Postgres requires the
        # partition key in every unique constraint on a partitioned table,
        # so the constraint became UNIQUE (season, game_id, source,
        # play_index). That's required for partitioning to work at all,
        # but it means the DB no longer rejects two rows with the same
        # (game_id, source, play_index) if a future bug ever landed them
        # in different season partitions. This check catches that
        # scenario directly, independent of the partition key.
        check_grouped_no_duplicates(
            "core.play natural-key uniqueness (partition-key-independent)",
            """
            SELECT game_id::text || '-' || source || '-' || play_index::text,
                1,
                count(*)
            FROM core.play
            GROUP BY game_id, source, play_index
            HAVING count(*) > 1
            """,
        ),
        # Second half of the same reconciliation the win-totals check
        # above covers: does core.game agree with Lahman on how *many*
        # teams played a given season, not just how many games each one
        # won. Filtered to Lahman's own lgid IN ('AL','NL') because
        # raw.lahman_teams also carries Negro League team-seasons
        # (confirmed directly: 1932 alone has 38 distinct teamidretro
        # values, 22 of them Negro League clubs like the Homestead Grays
        # and Kansas City Monarchs) which core.game's game_type='regular'
        # scope was never meant to include. Two real, understood
        # exceptions found checking every season in the dataset, not
        # guessed: 1914-1915 (the Federal League, a genuine third major
        # league those two seasons only — Retrosheet correctly counts it
        # as game_type='regular', Lahman's AL/NL filter naturally excludes
        # it, an 8-team gap both ways agree is real) is excluded outright;
        # tolerance=1 absorbs the one remaining case (2025's Athletics —
        # Lahman's own crosswalk already uses their new bare "ATH" code,
        # core.team keeps "OAK" as the primary retro_team_id, matching
        # Retrosheet's own historical continuity — see ADR-029).
        check_totals_reconcile(
            "core.game team count vs Lahman",
            """
            WITH core_teams AS (
                SELECT cg.season, count(DISTINCT t.retro_team_id) AS core_team_count
                FROM core.game cg
                JOIN core.team t ON cg.home_team_id = t.id OR cg.away_team_id = t.id
                WHERE cg.game_type = 'regular'
                GROUP BY cg.season
            ),
            lahman_teams AS (
                SELECT yearid::integer AS season, count(DISTINCT teamidretro) AS lahman_team_count
                FROM raw.lahman_teams
                WHERE lgid IN ('AL', 'NL')
                GROUP BY yearid
            )
            SELECT lt.season::text, ct.core_team_count, lt.lahman_team_count
            FROM lahman_teams lt
            JOIN core_teams ct ON ct.season = lt.season
            WHERE lt.season NOT IN (1914, 1915)
            """,
            tolerance=1,
        ),
    ]
