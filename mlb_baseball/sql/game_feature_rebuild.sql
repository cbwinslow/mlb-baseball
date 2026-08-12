-- First game-feature family. Cutoff is the MLB schedule's declared first
-- pitch. Doubleheaders sort by cutoff, declared game number, then provider key.
WITH schedule AS (
    SELECT DISTINCT ON (ms.game_id)
        ms.game_id, ms._season::integer AS season, ms.game_date::date AS game_date,
        CASE WHEN ms.game_num ~ '^[0-9]+$' THEN ms.game_num::integer END AS game_number,
        ms.game_datetime::timestamptz AS feature_cutoff_at,
        ms.status, ms.home_id, ms.away_id, ms.venue_id
    FROM raw.mlb_schedule ms
    WHERE ms.game_type = 'R' AND ms.game_id IS NOT NULL
      AND ms._season ~ '^[0-9]{4}$'
      AND ms.game_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      AND NULLIF(ms.game_datetime, '') IS NOT NULL
    ORDER BY ms.game_id, ms._loaded_at DESC NULLS LAST,
        ms.game_datetime DESC, ms.game_num DESC NULLS LAST
),
completed AS (
    SELECT 'g' || g.id::text AS key, g.id AS game_id, g.game_pk AS mlb_game_pk,
        g.season, g.game_date, COALESCE(g.game_number, s.game_number) AS game_number,
        s.feature_cutoff_at, g.home_team_id, g.away_team_id,
        g.home_score, g.away_score, g.venue_id, 'mlb:' || g.game_pk AS game_instance_key
    FROM core.game g
    JOIN schedule s ON s.game_id = g.game_pk AND s.game_date = g.game_date
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
      AND g.home_team_id IS NOT NULL AND g.away_team_id IS NOT NULL
      AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
),
scheduled AS (
    SELECT 's' || s.game_id AS key, NULL::bigint AS game_id, s.game_id AS mlb_game_pk,
        s.season, s.game_date, s.game_number, s.feature_cutoff_at,
        home.id AS home_team_id, away.id AS away_team_id,
        NULL::integer AS home_score, NULL::integer AS away_score, venue.id AS venue_id,
        'mlb:' || s.game_id AS game_instance_key
    FROM schedule s
    JOIN core.team home ON s.home_id ~ '^[0-9]+$'
        AND home.mlb_team_id = s.home_id::integer
        AND s.season BETWEEN home.first_year AND home.last_year
    JOIN core.team away ON s.away_id ~ '^[0-9]+$'
        AND away.mlb_team_id = s.away_id::integer
        AND s.season BETWEEN away.first_year AND away.last_year
    LEFT JOIN LATERAL (
        SELECT id FROM core.venue
        WHERE s.venue_id ~ '^[0-9]+$' AND mlb_venue_id = s.venue_id::integer
          AND (first_year IS NULL OR first_year <= s.season)
          AND (last_year IS NULL OR last_year >= s.season)
        ORDER BY first_year DESC NULLS LAST, id LIMIT 1
    ) venue ON TRUE
    WHERE s.status = 'Scheduled'
      AND NOT EXISTS (SELECT 1 FROM completed c WHERE c.mlb_game_pk = s.game_id)
),
games AS (
    SELECT * FROM completed UNION ALL SELECT * FROM scheduled
),
team_games AS (
    SELECT key, season, game_number, feature_cutoff_at, mlb_game_pk, home_team_id AS team_id,
        (home_score > away_score)::integer AS win, home_score AS runs_for, away_score AS runs_against
    FROM completed
    UNION ALL
    SELECT key, season, game_number, feature_cutoff_at, mlb_game_pk, away_team_id,
        (away_score > home_score)::integer, away_score, home_score FROM completed
    UNION ALL
    SELECT key, season, game_number, feature_cutoff_at, mlb_game_pk, home_team_id,
        NULL::integer, NULL::integer, NULL::integer FROM scheduled
    UNION ALL
    SELECT key, season, game_number, feature_cutoff_at, mlb_game_pk, away_team_id,
        NULL::integer, NULL::integer, NULL::integer FROM scheduled
),
running AS (
    SELECT key, team_id,
        CASE WHEN count(win) OVER w_season = 0 THEN NULL
             ELSE count(win) FILTER (WHERE win = 1) OVER w_season END AS wins,
        CASE WHEN count(win) OVER w_season = 0 THEN NULL
             ELSE count(win) FILTER (WHERE win = 0) OVER w_season END AS losses,
        avg(win) OVER w_season AS win_pct, avg(win) OVER w_last10 AS win_pct_10,
        sum(runs_for) OVER w_season AS runs_for_sum,
        sum(runs_against) OVER w_season AS runs_against_sum,
        count(win) OVER w_season AS games_played,
        feature_cutoff_at::date - lag(feature_cutoff_at::date) OVER w_career AS rest
    FROM team_games
    WINDOW
        w_season AS (PARTITION BY team_id, season
            ORDER BY feature_cutoff_at, game_number NULLS LAST, mlb_game_pk
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        w_last10 AS (PARTITION BY team_id, season
            ORDER BY feature_cutoff_at, game_number NULLS LAST, mlb_game_pk
            ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING),
        w_career AS (PARTITION BY team_id
            ORDER BY feature_cutoff_at, game_number NULLS LAST, mlb_game_pk)
),
pyth AS (
    SELECT key, team_id, wins, losses, win_pct, win_pct_10, rest,
        runs_for_sum, runs_against_sum, runs_for_sum - runs_against_sum AS run_diff,
        CASE WHEN games_played > 0 AND runs_for_sum + runs_against_sum > 0 THEN
            power(runs_for_sum::numeric,
                power(((runs_for_sum + runs_against_sum)::numeric / games_played), 0.287))
            / NULLIF(power(runs_for_sum::numeric,
                    power(((runs_for_sum + runs_against_sum)::numeric / games_played), 0.287))
                + power(runs_against_sum::numeric,
                    power(((runs_for_sum + runs_against_sum)::numeric / games_played), 0.287)), 0)
        END AS pyth_wpct
    FROM running
)
INSERT INTO gold.game_feature (
    game_id, mlb_game_pk, game_instance_key, season, game_date, game_number,
    feature_cutoff_at, home_team_id, away_team_id,
    home_wins, home_losses, away_wins, away_losses,
    home_win_pct, away_win_pct, home_win_pct_10, away_win_pct_10,
    home_runs_for, home_runs_allowed, away_runs_for, away_runs_allowed,
    home_run_diff, away_run_diff, home_pyth_wpct, away_pyth_wpct,
    home_rest, away_rest, home_field, venue_id, home_win
)
SELECT g.game_id, g.mlb_game_pk, g.game_instance_key, g.season, g.game_date, g.game_number,
    g.feature_cutoff_at, g.home_team_id, g.away_team_id,
    ph.wins, ph.losses, pa.wins, pa.losses,
    ph.win_pct, pa.win_pct, ph.win_pct_10, pa.win_pct_10,
    ph.runs_for_sum, ph.runs_against_sum, pa.runs_for_sum, pa.runs_against_sum,
    ph.run_diff, pa.run_diff, ph.pyth_wpct, pa.pyth_wpct,
    ph.rest, pa.rest, TRUE, g.venue_id,
    CASE WHEN g.home_score IS NOT NULL THEN g.home_score > g.away_score END
FROM games g
JOIN pyth ph ON ph.key = g.key AND ph.team_id = g.home_team_id
JOIN pyth pa ON pa.key = g.key AND pa.team_id = g.away_team_id;
