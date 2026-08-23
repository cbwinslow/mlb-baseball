-- Fetch batter arsenal profile for a given batter and season.
SELECT
    player_id,
    pitch_type,
    NULLIF(pitches, '')::integer AS pitches_seen,
    NULLIF(run_value_per_100, '')::numeric AS run_value_per_100,
    NULLIF(woba, '')::numeric AS woba,
    NULLIF(whiff_percent, '')::numeric / 100.0 AS whiff_ratio
FROM raw.statcast_batter_arsenal
WHERE player_id = %(player_id)s AND _season = %(season)s;
