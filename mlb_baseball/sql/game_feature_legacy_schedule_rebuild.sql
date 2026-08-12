-- Compatibility-only scheduled-game fixture build. Public ``mlb features``
-- uses the strict cutoff-safe resource instead.
WITH games AS (
    SELECT 'g' || g.id::text AS key, g.id AS game_id, g.game_pk AS mlb_game_pk,
        g.season, g.game_date, g.game_number, g.home_team_id, g.away_team_id,
        g.home_score, g.away_score, g.venue_id,
        COALESCE('mlb:' || g.game_pk, 'retro:' || g.retro_game_id) AS game_instance_key
    FROM core.game g JOIN core.team home ON home.id = g.home_team_id
    JOIN core.team away ON away.id = g.away_team_id WHERE g.game_type = 'regular'
    UNION ALL
    SELECT 's' || ms.game_id || ':' || ms.game_date || ':' || COALESCE(NULLIF(ms.game_num, ''), '1'),
        NULL::bigint, ms.game_id, ms._season::integer, ms.game_date::date,
        CASE WHEN ms.game_num ~ '^[0-9]+$' THEN ms.game_num::integer END,
        home.id, away.id, NULL::integer, NULL::integer, venue.id, 'mlb:' || ms.game_id
    FROM raw.mlb_schedule ms
    JOIN core.team home ON home.mlb_team_id = ms.home_id::integer
        AND ms._season::integer BETWEEN home.first_year AND home.last_year
    JOIN core.team away ON away.mlb_team_id = ms.away_id::integer
        AND ms._season::integer BETWEEN away.first_year AND away.last_year
    LEFT JOIN LATERAL (
        SELECT id FROM core.venue WHERE mlb_venue_id = NULLIF(ms.venue_id, '')::integer
        ORDER BY id LIMIT 1
    ) venue ON TRUE
    WHERE ms.status = 'Scheduled' AND ms.game_type = 'R'
), team_games AS (
    SELECT key, season, game_date, game_number, home_team_id AS team_id,
        CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL THEN (home_score > away_score)::int END AS win,
        home_score AS runs_for, away_score AS runs_against FROM games
    UNION ALL
    SELECT key, season, game_date, game_number, away_team_id,
        CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL THEN (away_score > home_score)::int END,
        away_score, home_score FROM games
), running AS (
    SELECT key, team_id, AVG(win) OVER w_season AS win_pct, AVG(win) OVER w_last10 AS win_pct_10,
        SUM(runs_for) OVER w_season AS runs_for_sum, SUM(runs_against) OVER w_season AS runs_against_sum,
        COUNT(win) OVER w_season AS games_played, game_date - LAG(game_date) OVER w_career AS rest
    FROM team_games WINDOW
        w_season AS (PARTITION BY team_id, season ORDER BY game_date, game_number, key ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        w_last10 AS (PARTITION BY team_id, season ORDER BY game_date, game_number, key ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING),
        w_career AS (PARTITION BY team_id ORDER BY game_date, game_number, key)
), pyth AS (
    SELECT key, team_id, win_pct, win_pct_10, rest, runs_for_sum - runs_against_sum AS run_diff,
        CASE WHEN games_played > 0 AND runs_for_sum + runs_against_sum > 0 THEN
            power(runs_for_sum::numeric, power(((runs_for_sum + runs_against_sum)::numeric / games_played), 0.287))
            / NULLIF(power(runs_for_sum::numeric, power(((runs_for_sum + runs_against_sum)::numeric / games_played), 0.287))
                + power(runs_against_sum::numeric, power(((runs_for_sum + runs_against_sum)::numeric / games_played), 0.287)), 0)
        END AS pyth_wpct FROM running
)
INSERT INTO gold.game_feature (game_id, mlb_game_pk, game_instance_key, season, game_date, home_team_id, away_team_id,
    home_win_pct, away_win_pct, home_win_pct_10, away_win_pct_10, home_run_diff, away_run_diff,
    home_pyth_wpct, away_pyth_wpct, home_rest, away_rest, venue_id, home_win)
SELECT g.game_id, g.mlb_game_pk, g.game_instance_key, g.season, g.game_date, g.home_team_id, g.away_team_id,
    ph.win_pct, pa.win_pct, ph.win_pct_10, pa.win_pct_10, ph.run_diff, pa.run_diff,
    ph.pyth_wpct, pa.pyth_wpct, ph.rest, pa.rest, g.venue_id,
    CASE WHEN g.home_score IS NOT NULL AND g.away_score IS NOT NULL THEN g.home_score > g.away_score END
FROM games g JOIN pyth ph ON ph.key = g.key AND ph.team_id = g.home_team_id
JOIN pyth pa ON pa.key = g.key AND pa.team_id = g.away_team_id;
