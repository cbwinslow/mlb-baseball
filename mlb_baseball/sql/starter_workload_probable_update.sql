WITH latest_probable AS (
    -- One row per (game_pk, side): the most recently captured probable --
    -- raw.mlb_probable is append-only specifically so a later snapshot (a
    -- scratch, a rotation swap) always wins over an earlier one.
    SELECT DISTINCT ON (game_pk, side) game_pk, side, pitcher_id
    FROM raw.mlb_probable
    WHERE pitcher_id IS NOT NULL
    ORDER BY game_pk, side, _loaded_at DESC
),
targets AS (
    -- Every still-upcoming game_feature row with an announced probable on
    -- at least one side. Dated via gold.game_feature (populated from
    -- raw.mlb_schedule).
    SELECT f.id AS feature_id, f.game_date,
        hp.pitcher_id AS home_pitcher_id, ap.pitcher_id AS away_pitcher_id
    FROM gold.game_feature f
    LEFT JOIN latest_probable hp ON hp.game_pk = f.mlb_game_pk AND hp.side = 'home'
    LEFT JOIN latest_probable ap ON ap.game_pk = f.mlb_game_pk AND ap.side = 'away'
    WHERE f.home_win IS NULL AND (hp.pitcher_id IS NOT NULL OR ap.pitcher_id IS NOT NULL)
),
first_pitcher AS (
    -- Starters for each side in 2026 completed games
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay
    ORDER BY game_pk, half_inning, at_bat_index::int
),
play_outs AS (
    -- Per-play outs diff across 2026 regular games, dated via raw.mlb_schedule
    SELECT pbp.game_pk, pbp.pitcher_id, ms.game_date::date AS game_date,
        pbp.outs::int - LAG(pbp.outs::int, 1, 0) OVER (
            PARTITION BY pbp.game_pk, pbp.inning, pbp.half_inning ORDER BY pbp.at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay pbp
    JOIN raw.mlb_schedule ms ON ms.game_id = pbp.game_pk AND ms.game_type = 'R'
),
pitcher_game_stats AS (
    -- Aggregated outs per (pitcher, game_date, game_pk) and whether this appearance was a start
    SELECT
        po.pitcher_id,
        po.game_date,
        po.game_pk,
        sum(po.outs_this_play) AS outs,
        bool_or(fp.pitcher_id IS NOT NULL) AS is_start
    FROM play_outs po
    LEFT JOIN first_pitcher fp ON fp.game_pk = po.game_pk AND fp.pitcher_id = po.pitcher_id
    GROUP BY po.pitcher_id, po.game_date, po.game_pk
),
-- Entering-this-(not-yet-played)-start workload and rest:
-- Must look ONLY at appearances strictly before the target game's own date
-- (s.game_date < t.game_date).
home_workload AS (
    SELECT
        t.feature_id,
        t.game_date - MAX(s.game_date) FILTER (WHERE s.is_start) AS rest_days,
        SUM(s.outs) FILTER (
            WHERE s.game_date >= t.game_date - (%(workload_days)s * INTERVAL '1 day')
        ) AS workload_outs
    FROM targets t
    JOIN pitcher_game_stats s ON s.pitcher_id = t.home_pitcher_id AND s.game_date < t.game_date
    GROUP BY t.feature_id, t.game_date
),
away_workload AS (
    SELECT
        t.feature_id,
        t.game_date - MAX(s.game_date) FILTER (WHERE s.is_start) AS rest_days,
        SUM(s.outs) FILTER (
            WHERE s.game_date >= t.game_date - (%(workload_days)s * INTERVAL '1 day')
        ) AS workload_outs
    FROM targets t
    JOIN pitcher_game_stats s ON s.pitcher_id = t.away_pitcher_id AND s.game_date < t.game_date
    GROUP BY t.feature_id, t.game_date
)
UPDATE gold.game_feature f
SET
    home_starter_rest_days = hw.rest_days,
    home_starter_outs_7d = hw.workload_outs,
    away_starter_rest_days = aw.rest_days,
    away_starter_outs_7d = aw.workload_outs
FROM targets t
LEFT JOIN home_workload hw ON hw.feature_id = t.feature_id
LEFT JOIN away_workload aw ON aw.feature_id = t.feature_id
WHERE f.id = t.feature_id
