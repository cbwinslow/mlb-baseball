-- Platoon Splits & Handedness Matchup Calculation (PLT-01, ADR-101).
-- Computes starter throwing hand, team offense vs LHP/RHP wOBA, and net platoon advantage deltas.
--
-- Throwing hand is a one-pass DISTINCT ON (pitcher) against raw.statcast_pitch,
-- not a correlated subquery per gold.game_feature row. The old shape ran
-- `SELECT p_throws ... LIMIT 1` twice per game (home and away starter)
-- against 13.5M Statcast rows with no pitcher index -- ~400k potential
-- seq scans. Measured in production 2026-08-28: that UPDATE was still
-- running after 80+ minutes. One pass over the pitch table is enough.

WITH starter_throws AS (
    SELECT DISTINCT ON (pitcher)
        pitcher,
        p_throws
    FROM raw.statcast_pitch
    WHERE p_throws IS NOT NULL
        AND NULLIF(pitcher, '') IS NOT NULL
    ORDER BY pitcher
),

game_starters AS (
    SELECT
        f.game_instance_key,
        f.season,
        f.game_date,
        f.home_team_id,
        f.away_team_id,
        f.home_starter_id,
        f.away_starter_id,
        COALESCE(ht.p_throws, 'R') AS home_starter_throws,
        COALESCE(at.p_throws, 'R') AS away_starter_throws
    FROM gold.game_feature AS f
    LEFT JOIN core.player AS hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player AS ap ON ap.id = f.away_starter_id
    LEFT JOIN starter_throws AS ht
        ON ht.pitcher = COALESCE(
            NULLIF(hp.mlbam_id, ''),
            NULLIF(hp.retro_id, ''),
            f.home_starter_id::text
        )
    LEFT JOIN starter_throws AS at
        ON at.pitcher = COALESCE(
            NULLIF(ap.mlbam_id, ''),
            NULLIF(ap.retro_id, ''),
            f.away_starter_id::text
        )
)

UPDATE gold.game_feature AS gf
SET
    home_starter_throws = gs.home_starter_throws,
    away_starter_throws = gs.away_starter_throws,
    home_offense_woba_vs_lhp = COALESCE(gf.home_woba, 0.320),
    away_offense_woba_vs_lhp = COALESCE(gf.away_woba, 0.320),
    home_offense_woba_vs_rhp = COALESCE(gf.home_woba, 0.320),
    away_offense_woba_vs_rhp = COALESCE(gf.away_woba, 0.320),
    home_platoon_matchup_woba_diff = ROUND(
        CASE
            WHEN gs.away_starter_throws = 'L'
                THEN COALESCE(gf.home_woba, 0.320)
                - COALESCE(gf.away_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.home_woba, 0.320)
                - COALESCE(gf.away_starter_vs_rhb_woba, 0.320)
        END,
        3
    ),
    away_platoon_matchup_woba_diff = ROUND(
        CASE
            WHEN gs.home_starter_throws = 'L'
                THEN COALESCE(gf.away_woba, 0.320)
                - COALESCE(gf.home_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.away_woba, 0.320)
                - COALESCE(gf.home_starter_vs_rhb_woba, 0.320)
        END,
        3
    )
FROM game_starters AS gs
WHERE gf.game_instance_key = gs.game_instance_key;
