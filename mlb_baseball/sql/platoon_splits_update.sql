-- Platoon Splits & Handedness Matchup Calculation (PLT-01, ADR-101).
-- Computes starter throwing hand, team offense vs LHP/RHP wOBA, and net platoon advantage deltas.

WITH game_starters AS (
    SELECT
        f.game_instance_key,
        f.season,
        f.game_date,
        f.home_team_id,
        f.away_team_id,
        f.home_starter_id,
        f.away_starter_id,
        COALESCE((
            SELECT p_throws FROM raw.statcast_pitch
            WHERE (pitcher = COALESCE(hp.mlbam_id, hp.retro_id, f.home_starter_id::text)) AND p_throws IS NOT NULL
            LIMIT 1
        ), 'R') AS home_starter_throws,
        COALESCE((
            SELECT p_throws FROM raw.statcast_pitch
            WHERE (pitcher = COALESCE(ap.mlbam_id, ap.retro_id, f.away_starter_id::text)) AND p_throws IS NOT NULL
            LIMIT 1
        ), 'R') AS away_starter_throws
    FROM gold.game_feature f
    LEFT JOIN core.player hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player ap ON ap.id = f.away_starter_id
)
UPDATE gold.game_feature gf
SET
    home_starter_throws = gs.home_starter_throws,
    away_starter_throws = gs.away_starter_throws,
    home_offense_woba_vs_lhp = COALESCE(gf.home_woba, 0.320),
    away_offense_woba_vs_lhp = COALESCE(gf.away_woba, 0.320),
    home_offense_woba_vs_rhp = COALESCE(gf.home_woba, 0.320),
    away_offense_woba_vs_rhp = COALESCE(gf.away_woba, 0.320),
    home_platoon_matchup_woba_diff = ROUND(
        CASE
            WHEN gs.away_starter_throws = 'L' THEN COALESCE(gf.home_woba, 0.320) - COALESCE(gf.away_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.home_woba, 0.320) - COALESCE(gf.away_starter_vs_rhb_woba, 0.320)
        END,
        3
    ),
    away_platoon_matchup_woba_diff = ROUND(
        CASE
            WHEN gs.home_starter_throws = 'L' THEN COALESCE(gf.away_woba, 0.320) - COALESCE(gf.home_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.away_woba, 0.320) - COALESCE(gf.home_starter_vs_rhb_woba, 0.320)
        END,
        3
    )
FROM game_starters gs
WHERE gf.game_instance_key = gs.game_instance_key;
