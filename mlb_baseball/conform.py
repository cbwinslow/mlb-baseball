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
matching against repr'd dicts in SQL.
"""

import re
from ast import literal_eval
from datetime import date
from decimal import Decimal, InvalidOperation

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_table_exists, check_table_has_rows
from mlb_baseball.ingest import track_run

SOURCE = "core"

# Kalshi's own KXMLBGAME market-ticker team-code suffixes -> Retrosheet's
# retro_team_id. Every code here was confirmed present in real production
# data (`SELECT DISTINCT` against raw.kalshi_market's tickers), not
# guessed — including two, "AL"/"NL", seen in the same query and
# deliberately excluded: those are a different (non-team) market type
# sharing the KXMLBGAME series, not team codes.
_KALSHI_TEAM_CODES = {
    "ATH": "OAK",
    "ATL": "ATL",
    "AZ": "ARI",
    "BAL": "BAL",
    "BOS": "BOS",
    "CHC": "CHN",
    "CIN": "CIN",
    "CLE": "CLE",
    "COL": "COL",
    "CWS": "CHA",
    "DET": "DET",
    "HOU": "HOU",
    "KC": "KCA",
    "LAA": "ANA",
    "LAD": "LAN",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NYM": "NYN",
    "NYY": "NYA",
    "PHI": "PHI",
    "PIT": "PIT",
    "SD": "SDN",
    "SEA": "SEA",
    "SF": "SFN",
    "STL": "SLN",
    "TB": "TBA",
    "TEX": "TEX",
    "TOR": "TOR",
    "WSH": "WAS",
}

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
            SELECT
                team_id, league, city, nickname, first_year::integer,
                -- Real bug found while extending conform.py, not
                -- hypothetical: Retrosheet's own TEAMABR.TXT caps every
                -- currently-active team's last_year at the same value
                -- (confirmed: exactly 30 rows share it -- the real current
                -- MLB team count -- while 122 other team-eras have a
                -- strictly earlier, genuine end year like MON's 2004 or
                -- FLO's 2011). That's the file being stale, not those 30
                -- teams having stopped existing, so every downstream
                -- season-range join (core.game, core.market,
                -- core.player_war) was silently failing to resolve any
                -- team for 2022+ -- confirmed directly: away_team_id/
                -- home_team_id were NULL for 100% of core.game rows from
                -- 2022 on before this fix. 9999 is a clear, documented
                -- sentinel for "still active as of this file's last
                -- update," not a real year.
                CASE
                    WHEN last_year::integer = max(last_year::integer) OVER ()
                    THEN 9999
                    ELSE last_year::integer
                END
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


def _team_lookup(conn: psycopg.Connection) -> tuple[dict[str, int], dict[str, int]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, retro_team_id, city, nickname FROM core.team")
        rows = cur.fetchall()
    by_name = {f"{city} {nickname}": team_id for team_id, _, city, nickname in rows}
    by_retro_id = {retro_id: team_id for team_id, retro_id, _, _ in rows}
    return by_name, by_retro_id


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


def _polymarket_market_rows(
    conn: psycopg.Connection, team_by_name: dict[str, int], game_exact: dict[tuple, int]
) -> list[tuple]:
    rows: list[tuple] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.slug, e.teams, e.closed, m.id, m.volume, o.outcome, o.price
            FROM raw.polymarket_event e
            JOIN raw.polymarket_market m ON m.event_id = e.id
            JOIN raw.polymarket_outcome o ON o.market_id = m.id
            WHERE e.sport IS NOT NULL
            """
        )
        for slug, teams_text, closed, market_id, volume, outcome, price in cur.fetchall():
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
            away_id = team_by_name.get(away.get("name"))
            home_id = team_by_name.get(home.get("name"))
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
            rows.append((game_id, "polymarket", market_ref, team_id, price, volume, status))
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
    conn: psycopg.Connection, team_by_retro_id: dict[str, int], game_fuzzy: dict[tuple, tuple]
) -> list[tuple]:
    rows: list[tuple] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ticker, event_ticker, status, volume_fp,
                   yes_bid_dollars, yes_ask_dollars, last_price_dollars
            FROM raw.kalshi_market
            WHERE event_ticker LIKE 'KXMLBGAME%'
            """
        )
        for ticker, event_ticker, status, volume, yes_bid, yes_ask, last_price in cur.fetchall():
            date_match = _KALSHI_TICKER_DATE_RE.match(event_ticker or "")
            team_match = _KALSHI_TICKER_TEAM_RE.search(ticker or "")
            if not date_match or not team_match:
                continue
            yy, mon_abbr, dd = date_match.groups()
            month = _MONTH_ABBR.get(mon_abbr)
            if month is None:
                continue
            game_date = date(2000 + int(yy), month, int(dd))
            retro_id = _KALSHI_TEAM_CODES.get(team_match.group(1))
            team_id = team_by_retro_id.get(retro_id) if retro_id else None
            if team_id is None:
                continue
            match = game_fuzzy.get((game_date, team_id))
            game_id = match[0] if match else None
            price = _kalshi_implied_probability(last_price, yes_bid, yes_ask)
            rows.append((game_id, "kalshi", ticker, team_id, price, volume, status))
    return rows


def _build_market(conn: psycopg.Connection) -> int:
    team_by_name, team_by_retro_id = _team_lookup(conn)
    game_exact, game_fuzzy = _game_lookup(conn)

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
            rows.extend(_polymarket_market_rows(conn, team_by_name, game_exact))
    except psycopg.errors.UndefinedTable:
        print("conform: raw.polymarket_event not present yet — skipping its core.market rows")
    try:
        with conn.transaction():
            rows.extend(_kalshi_market_rows(conn, team_by_retro_id, game_fuzzy))
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
                JOIN core.player p ON p.bbref_id = w.player_id
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
                JOIN core.player p ON p.bbref_id = w.player_id
                """
            )
            total += cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("conform: raw.bref_war_pitching not present yet — skipping")
    return total


def run() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        _check_prerequisites(conn)
        # game references team/player, so it must be cleared first — CASCADE
        # on team/player's TRUNCATE would otherwise also wipe game silently.
        # play/pitch/market reference game in turn — Postgres requires
        # truncating a table together with everything that references it in
        # the same statement (a separate TRUNCATE core.game afterward raises
        # FeatureNotSupported even if play/pitch/market are already empty),
        # so all four go in one TRUNCATE, not four sequential ones.
        # core.player_war isn't listed here — it references core.player,
        # not core.game, so _build_players' own `TRUNCATE core.player
        # CASCADE` (below) already clears it.
        with conn.cursor() as cur:
            cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
        counts = {
            "core.team": _build_teams(conn),
            "core.player": _build_players(conn),
        }
        counts["core.game"] = _build_games(conn)
        _backfill_game_pk(conn)
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
        check_table_has_rows("core.game"),
        check_table_exists("core.play"),
        check_table_exists("core.pitch"),
        check_table_exists("core.market"),
        check_table_exists("core.player_war"),
    ]
