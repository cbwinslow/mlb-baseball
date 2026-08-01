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
    LEFT JOIN core.venue venue ON venue.mlb_venue_id = NULLIF(ms.venue_id, '')::integer
    WHERE ms.status = 'Scheduled' AND ms.game_type = 'R'
"""

_BUILD_SQL_TEMPLATE = """
WITH games AS (
    {games_sql}
),
-- Point-in-time win%/run-diff per team, computed via window functions over
-- a two-rows-per-game view (one row per team per game) ordered by date --
-- each game's feature values come only from strictly earlier games in the
-- same season (ROWS BETWEEN ... AND 1 PRECEDING), never itself. win/runs_for/
-- runs_against are NULL for games with no final score (future/unplayed) --
-- AVG/SUM ignore NULLs, so those rows can't leak into anyone's rolling stats
-- without an explicit score to leak.
team_games AS (
    SELECT key, season, game_date, game_number, home_team_id AS team_id,
        CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL
             THEN (home_score > away_score)::int END AS win,
        home_score AS runs_for, away_score AS runs_against
    FROM games
    UNION ALL
    SELECT key, season, game_date, game_number, away_team_id,
        CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL
             THEN (away_score > home_score)::int END,
        away_score, home_score
    FROM games
),
running AS (
    SELECT key, team_id,
        AVG(win) OVER w_season AS win_pct,
        AVG(win) OVER w_last10 AS win_pct_10,
        SUM(runs_for) OVER w_season AS runs_for_sum,
        SUM(runs_against) OVER w_season AS runs_against_sum,
        COUNT(win) OVER w_season AS games_played,
        -- Rest: days since this team's immediately preceding game -- NOT
        -- partitioned by season, unlike everything else here. Rest
        -- genuinely carries across the season boundary (a team's rest
        -- entering Opening Day is real, if huge); the win%/run-diff
        -- stats above are deliberately season-scoped instead because
        -- carrying THOSE across an offseason would mix two different
        -- team-strength eras together.
        game_date - LAG(game_date) OVER w_career AS rest
    FROM team_games
    WINDOW
        w_season AS (
            PARTITION BY team_id, season ORDER BY game_date, game_number, key
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ),
        w_last10 AS (
            PARTITION BY team_id, season ORDER BY game_date, game_number, key
            ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
        ),
        w_career AS (PARTITION BY team_id ORDER BY game_date, game_number, key)
),
-- Pythagenpat (David Smyth): exponent adapts to scoring environment instead
-- of a fixed 2 -- see docs/RESEARCH.md. NULLIF(games_played, 0) leaves a
-- team's first game of the season NULL rather than dividing by zero.
exponent AS (
    SELECT key, team_id, win_pct, win_pct_10, rest, runs_for_sum, runs_against_sum,
        power(
            (runs_for_sum + runs_against_sum)::numeric / NULLIF(games_played, 0),
            0.287
        ) AS pyt_exp
    FROM running
),
pyth AS (
    SELECT key, team_id, win_pct, win_pct_10, rest,
        runs_for_sum - runs_against_sum AS run_diff,
        CASE WHEN pyt_exp IS NOT NULL AND (runs_for_sum + runs_against_sum) > 0 THEN
            power(runs_for_sum::numeric, pyt_exp) / NULLIF(
                power(runs_for_sum::numeric, pyt_exp) + power(runs_against_sum::numeric, pyt_exp), 0
            )
        END AS pyth_wpct
    FROM exponent
)
INSERT INTO gold.game_feature (
    game_id, mlb_game_pk, season, game_date, home_team_id, away_team_id,
    home_win_pct, away_win_pct, home_win_pct_10, away_win_pct_10,
    home_run_diff, away_run_diff, home_pyth_wpct, away_pyth_wpct,
    home_rest, away_rest, venue_id, home_win
)
SELECT
    g.game_id, g.mlb_game_pk, g.season, g.game_date, g.home_team_id, g.away_team_id,
    ph.win_pct, pa.win_pct, ph.win_pct_10, pa.win_pct_10,
    ph.run_diff, pa.run_diff, ph.pyth_wpct, pa.pyth_wpct,
    ph.rest, pa.rest, g.venue_id,
    CASE WHEN g.home_score IS NOT NULL AND g.away_score IS NOT NULL
         THEN g.home_score > g.away_score END
FROM games g
JOIN pyth ph ON ph.key = g.key AND ph.team_id = g.home_team_id
JOIN pyth pa ON pa.key = g.key AND pa.team_id = g.away_team_id
"""


def build(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (schedule_exists,) = fetch_one(cur)
        games_sql = _COMPLETED_GAMES_SQL + (_UPCOMING_GAMES_SQL if schedule_exists else "")
        cur.execute("TRUNCATE gold.game_feature")
        cur.execute(_BUILD_SQL_TEMPLATE.format(games_sql=games_sql))
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
