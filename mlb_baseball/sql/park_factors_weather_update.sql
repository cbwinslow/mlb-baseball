-- Update gold.game_feature with point-in-time multi-year component park factors
-- (1yr, 3yr, 5yr, HR, 2B, 3B, LHB/RHB HR) and environmental weather features (PARK-01, WEA-01).
--
-- Strictly zero lookahead: all park factors use trailing windows strictly prior to target season.

WITH home_splits AS (
    SELECT
        g.home_team_id AS team_id,
        g.season,
        g.venue_id,
        count(*) AS games,
        sum(g.home_score + g.away_score) AS runs
    FROM core.game g
    WHERE lower(g.game_type) = 'regular'
      AND g.home_score IS NOT NULL
      AND g.away_score IS NOT NULL
      AND g.venue_id IS NOT NULL
    GROUP BY g.home_team_id, g.season, g.venue_id
),

road_splits AS (
    SELECT
        g.away_team_id AS team_id,
        g.season,
        count(*) AS games,
        sum(g.home_score + g.away_score) AS runs
    FROM core.game g
    WHERE lower(g.game_type) = 'regular'
      AND g.home_score IS NOT NULL
      AND g.away_score IS NOT NULL
    GROUP BY g.away_team_id, g.season
),

team_season_pf AS (
    SELECT
        h.team_id,
        h.season,
        h.venue_id,
        (h.runs::numeric / NULLIF(h.games, 0)) AS home_rate,
        (r.runs::numeric / NULLIF(r.games, 0)) AS road_rate
    FROM home_splits h
    JOIN road_splits r ON r.team_id = h.team_id AND r.season = h.season
),

venue_seasons_needed AS (
    SELECT DISTINCT venue_id, season FROM gold.game_feature WHERE venue_id IS NOT NULL
),

venue_multi_year AS (
    SELECT
        n.venue_id,
        n.season AS target_season,
        -- 1-Year Park Factor
        ROUND(avg(CASE WHEN b.season = n.season - 1 THEN 100.0 * b.home_rate / NULLIF(b.road_rate, 0) ELSE NULL END), 2) AS park_factor_1yr,
        -- 3-Year Park Factor (default trailing window)
        ROUND(avg(CASE WHEN b.season BETWEEN n.season - 3 AND n.season - 1 THEN 100.0 * b.home_rate / NULLIF(b.road_rate, 0) ELSE NULL END), 2) AS park_factor_3yr,
        -- 5-Year Park Factor
        ROUND(avg(CASE WHEN b.season BETWEEN n.season - 5 AND n.season - 1 THEN 100.0 * b.home_rate / NULLIF(b.road_rate, 0) ELSE NULL END), 2) AS park_factor_5yr
    FROM venue_seasons_needed n
    JOIN team_season_pf b ON b.venue_id = n.venue_id AND b.season BETWEEN n.season - 5 AND n.season - 1
    GROUP BY n.venue_id, n.season
),

-- Component factors derived from 3-year run environment (defaulting components to regressed park ratios)
venue_components AS (
    SELECT
        v.venue_id,
        v.target_season,
        v.park_factor_1yr,
        v.park_factor_3yr,
        v.park_factor_5yr,
        -- Component estimates regressed to 3-year park factor
        v.park_factor_3yr AS park_hr_factor_3yr,
        ROUND(100.0 + (v.park_factor_3yr - 100.0) * 0.85, 2) AS park_2b_factor_3yr,
        ROUND(100.0 + (v.park_factor_3yr - 100.0) * 0.70, 2) AS park_3b_factor_3yr,
        v.park_factor_3yr AS park_lhb_hr_factor_3yr,
        v.park_factor_3yr AS park_rhb_hr_factor_3yr
    FROM venue_multi_year v
)

UPDATE gold.game_feature f
SET
    park_factor = COALESCE(vc.park_factor_3yr, f.park_factor),
    park_factor_1yr = vc.park_factor_1yr,
    park_factor_3yr = vc.park_factor_3yr,
    park_factor_5yr = vc.park_factor_5yr,
    park_hr_factor_3yr = vc.park_hr_factor_3yr,
    park_2b_factor_3yr = vc.park_2b_factor_3yr,
    park_3b_factor_3yr = vc.park_3b_factor_3yr,
    park_lhb_hr_factor_3yr = vc.park_lhb_hr_factor_3yr,
    park_rhb_hr_factor_3yr = vc.park_rhb_hr_factor_3yr,

    -- Weather & Environmental physics
    air_density_index = CASE
        WHEN f.temp_f IS NOT NULL THEN
            ROUND(100.0 * (530.0 / (460.0 + f.temp_f)) * (CASE WHEN v.name ILIKE '%Coors%' OR v.city = 'Denver' THEN 0.83 ELSE 1.0 END), 2)
        ELSE NULL
    END,

    effective_wind_speed = CASE
        WHEN f.wind_speed_mph IS NOT NULL THEN
            CASE
                WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%to cf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%to lf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%to rf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%out%' THEN f.wind_speed_mph
                WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%from cf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%from lf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%from rf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%in%' THEN -f.wind_speed_mph
                WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%dome%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%indoor%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%calm%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%none%' THEN 0.0
                ELSE 0.0
            END
        ELSE NULL
    END,

    wind_direction_label = CASE
        WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%to cf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%to lf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%to rf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%out%' THEN 'outfield'
        WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%from cf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%from lf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%from rf%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%in%' THEN 'infield'
        WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%l to r%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%r to l%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%cross%' THEN 'crosswind'
        WHEN lower(COALESCE(f.wind_dir, '')) LIKE '%dome%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%indoor%' OR (v.roof_type IN ('dome', 'retractable') AND (lower(COALESCE(f.sky, '')) LIKE '%dome%' OR lower(COALESCE(f.sky, '')) LIKE '%indoor%')) THEN 'dome'
        WHEN f.wind_speed_mph = 0 OR lower(COALESCE(f.wind_dir, '')) LIKE '%calm%' OR lower(COALESCE(f.wind_dir, '')) LIKE '%none%' THEN 'calm'
        WHEN f.wind_dir IS NOT NULL AND f.wind_dir != '' THEN 'other'
        ELSE NULL
    END
FROM gold.game_feature gf
JOIN core.venue v ON v.id = gf.venue_id
LEFT JOIN venue_components vc ON vc.venue_id = gf.venue_id AND vc.target_season = gf.season
WHERE f.game_id = gf.game_id;
