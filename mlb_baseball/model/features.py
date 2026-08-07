"""Builds gold.game_feature -- point-in-time-correct pre-game features for
every completed core.game row *and* every still-upcoming game (see
ADR-032, docs/RESEARCH.md, migration 0014).

core.game only ever holds completed games by design (conform.py's
_build_games excludes status IN ('Scheduled', 'Postponed', ...) --
correct for its own historical-record scope). Upcoming games are pulled
directly from raw.mlb_schedule instead, resolving team_id via
core.team.mlb_team_id (the same robust anchor _backfill_mlb_team_id
already established) rather than name matching. Both sources are unioned
into one `games` CTE before computing anything, keyed by a synthetic
`key` ('g<core.game.id>' or 's<raw.mlb_schedule.game_id>') since an
upcoming game has no core.game.id to key on. mlb_game_pk -- MLB's own
numeric game ID, present on both sources -- is gold.game_feature's real
identity going forward (game_id is nullable, populated only once a game
has actually landed in core.game).

Scoped to regular season: core.game's game_type = 'regular', raw.mlb_
schedule's game_type = 'R' -- the win/loss target is regular-season
games, and postseason is a small, structurally different context (short
series, no meaningful "season-to-date" window) not worth folding into
the same rolling-stat computation.

Columns computable directly from game-level results are built here:
season-to-date win%, last-10 win%, run differential, Pythagenpat
expectation, and rest days (days since each team's immediately preceding
game -- not season-partitioned, unlike everything else, since rest
genuinely carries across the offseason boundary). Starter stats (needs
raw.retrosheet_event/raw.mlb_playbyplay, see mlb_baseball/model/starter.py),
prior-season WAR (needs core.player_war), and weather passthrough are
deliberately not built here -- each needs a different source query.

Self-truncating and TRUNCATE + full rebuild, same as conform.py's core
tables -- idempotent by construction, and cheap enough (227K+ games)
that there's no reason to chase incremental rebuilds yet.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.sql import read_sql

_COMPLETED_GAMES_SQL = """
    SELECT 'g' || id::text AS key, id AS game_id, game_pk AS mlb_game_pk,
        season, game_date, game_number, home_team_id, away_team_id,
        home_score, away_score, venue_id
    FROM core.game WHERE game_type = 'regular'
"""

# raw.mlb_schedule might not exist yet (mlb_api never bootstrapped) --
# checked in Python before building the query (see build()) rather than
# letting a missing table crash the whole gold.game_feature rebuild,
# including the completed-games half that doesn't depend on it at all.
# Same "degrade, don't crash" precedent as conform.py's _build_games.
# venue: LEFT JOIN, not required -- an unresolved venue shouldn't drop an
# otherwise-valid upcoming game, it just leaves park_factor NULL for it.
_UPCOMING_GAMES_SQL = """
    UNION ALL
    SELECT 's' || ms.game_id, NULL, ms.game_id,
        ms._season::integer, ms.game_date::date,
        CASE WHEN ms.game_num ~ '^[0-9]+$' THEN ms.game_num::integer END,
        home.id, away.id, NULL, NULL, venue.id
    FROM raw.mlb_schedule ms
    JOIN core.team home ON home.mlb_team_id = ms.home_id::integer
        AND ms._season::integer BETWEEN home.first_year AND home.last_year
    JOIN core.team away ON away.mlb_team_id = ms.away_id::integer
        AND ms._season::integer BETWEEN away.first_year AND away.last_year
    LEFT JOIN LATERAL (
        SELECT id
        FROM core.venue
        WHERE mlb_venue_id = NULLIF(ms.venue_id, '')::integer
          AND (first_year IS NULL OR first_year <= ms._season::integer)
          AND (last_year IS NULL OR last_year >= ms._season::integer)
        ORDER BY first_year DESC NULLS LAST, id
        LIMIT 1
    ) venue ON TRUE
    WHERE ms.status = 'Scheduled' AND ms.game_type = 'R'
"""


def build(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (schedule_exists,) = fetch_one(cur)
        games_sql = _COMPLETED_GAMES_SQL + (_UPCOMING_GAMES_SQL if schedule_exists else "")
        cur.execute("TRUNCATE gold.game_feature")
        cur.execute(read_sql("game_feature_rebuild.sql").format(games_sql=games_sql))
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
