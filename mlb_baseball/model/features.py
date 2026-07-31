"""Builds gold.game_feature -- point-in-time-correct pre-game features for
every core.game row (see ADR-032, docs/RESEARCH.md).

Scoped to game_type = 'regular': the win/loss target is regular-season
games, and postseason is a small, structurally different context (short
series, no meaningful "season-to-date" window) not worth folding into the
same rolling-stat computation.

Only the columns computable directly from core.game's own row-level
results are built here: season-to-date win%, last-10 win%, run
differential, and Pythagenpat expectation. Starter stats (needs core.play),
rest days, prior-season WAR (needs core.player_war), and weather passthrough
are deliberately not built yet -- each needs a different source query, and
this is the first complete, testable slice, not a stub of the rest.

Self-truncating and TRUNCATE + full rebuild, same as conform.py's core
tables -- idempotent by construction, and cheap enough (227K games) that
there's no reason to chase incremental rebuilds yet.
"""

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.ingest import track_run

SOURCE = "model_features"

# Point-in-time win%/run-diff per team, computed via window functions over
# a two-rows-per-game view (one row per team per game) ordered by date --
# each game's feature values come only from strictly earlier games in the
# same season (ROWS BETWEEN ... AND 1 PRECEDING), never itself. win/runs_for/
# runs_against are NULL for games with no final score (future/unplayed) --
# AVG/SUM ignore NULLs, so those rows can't leak into anyone's rolling stats
# without an explicit score to leak.
_BUILD_SQL = """
WITH team_games AS (
    SELECT id AS game_id, season, game_date, game_number, home_team_id AS team_id,
        CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL
             THEN (home_score > away_score)::int END AS win,
        home_score AS runs_for, away_score AS runs_against
    FROM core.game WHERE game_type = 'regular'
    UNION ALL
    SELECT id AS game_id, season, game_date, game_number, away_team_id AS team_id,
        CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL
             THEN (away_score > home_score)::int END AS win,
        away_score AS runs_for, home_score AS runs_against
    FROM core.game WHERE game_type = 'regular'
),
running AS (
    SELECT game_id, team_id,
        AVG(win) OVER w_season AS win_pct,
        AVG(win) OVER w_last10 AS win_pct_10,
        SUM(runs_for) OVER w_season AS runs_for_sum,
        SUM(runs_against) OVER w_season AS runs_against_sum,
        COUNT(win) OVER w_season AS games_played
    FROM team_games
    WINDOW
        w_season AS (
            PARTITION BY team_id, season ORDER BY game_date, game_number, game_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ),
        w_last10 AS (
            PARTITION BY team_id, season ORDER BY game_date, game_number, game_id
            ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
        )
),
-- Pythagenpat (David Smyth): exponent adapts to scoring environment instead
-- of a fixed 2 -- see docs/RESEARCH.md. NULLIF(games_played, 0) leaves a
-- team's first game of the season NULL rather than dividing by zero.
exponent AS (
    SELECT game_id, team_id, win_pct, win_pct_10, runs_for_sum, runs_against_sum,
        power(
            (runs_for_sum + runs_against_sum)::numeric / NULLIF(games_played, 0),
            0.287
        ) AS pyt_exp
    FROM running
),
pyth AS (
    SELECT game_id, team_id, win_pct, win_pct_10,
        runs_for_sum - runs_against_sum AS run_diff,
        CASE WHEN pyt_exp IS NOT NULL AND (runs_for_sum + runs_against_sum) > 0 THEN
            power(runs_for_sum::numeric, pyt_exp) / NULLIF(
                power(runs_for_sum::numeric, pyt_exp) + power(runs_against_sum::numeric, pyt_exp), 0
            )
        END AS pyth_wpct
    FROM exponent
)
INSERT INTO gold.game_feature (
    game_id, season, game_date, home_team_id, away_team_id,
    home_win_pct, away_win_pct, home_win_pct_10, away_win_pct_10,
    home_run_diff, away_run_diff, home_pyth_wpct, away_pyth_wpct, home_win
)
SELECT
    g.id, g.season, g.game_date, g.home_team_id, g.away_team_id,
    ph.win_pct, pa.win_pct, ph.win_pct_10, pa.win_pct_10,
    ph.run_diff, pa.run_diff, ph.pyth_wpct, pa.pyth_wpct,
    CASE WHEN g.home_score IS NOT NULL AND g.away_score IS NOT NULL
         THEN g.home_score > g.away_score END
FROM core.game g
JOIN pyth ph ON ph.game_id = g.id AND ph.team_id = g.home_team_id
JOIN pyth pa ON pa.game_id = g.id AND pa.team_id = g.away_team_id
WHERE g.game_type = 'regular'
"""


def build(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE gold.game_feature")
        cur.execute(_BUILD_SQL)
        return cur.rowcount


def run() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        count = build(conn)
        conn.commit()
        result["rows"] = count
    return {"gold.game_feature": count}


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
