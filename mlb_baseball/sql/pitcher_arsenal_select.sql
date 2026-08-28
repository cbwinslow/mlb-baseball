-- Fetch pitcher arsenal statistics for a given pitcher and season.
SELECT
    player_id,
    pitch_type,
    NULLIF(pitch_usage, '')::numeric / 100.0 AS pitch_usage_ratio,
    NULLIF(run_value_per_100, '')::numeric AS run_value_per_100,
    NULLIF(woba, '')::numeric AS woba_against,
    NULLIF(whiff_percent, '')::numeric / 100.0 AS whiff_ratio
FROM raw.statcast_pitcher_arsenal_stat
WHERE player_id = %(player_id)s AND _season = %(season)s;
