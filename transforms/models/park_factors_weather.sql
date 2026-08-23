MODEL (
    name gold.park_factors_weather,
    kind FULL,
    cron '@daily',
    grain [game_id]
);

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
        ROUND(avg(CASE WHEN b.season = n.season - 1 THEN 100.0 * b.home_rate / NULLIF(b.road_rate, 0) ELSE NULL END), 2) AS park_factor_1yr,
        ROUND(avg(CASE WHEN b.season BETWEEN n.season - 3 AND n.season - 1 THEN 100.0 * b.home_rate / NULLIF(b.road_rate, 0) ELSE NULL END), 2) AS park_factor_3yr,
        ROUND(avg(CASE WHEN b.season BETWEEN n.season - 5 AND n.season - 1 THEN 100.0 * b.home_rate / NULLIF(b.road_rate, 0) ELSE NULL END), 2) AS park_factor_5yr
    FROM venue_seasons_needed n
    JOIN team_season_pf b ON b.venue_id = n.venue_id AND b.season BETWEEN n.season - 5 AND n.season - 1
    GROUP BY n.venue_id, n.season
),

venue_components AS (
    SELECT
        v.venue_id,
        v.target_season,
        v.park_factor_1yr,
        v.park_factor_3yr,
        v.park_factor_5yr,
        v.park_factor_3yr AS park_hr_factor_3yr,
        ROUND(100.0 + (v.park_factor_3yr - 100.0) * 0.85, 2) AS park_2b_factor_3yr,
        ROUND(100.0 + (v.park_factor_3yr - 100.0) * 0.70, 2) AS park_3b_factor_3yr,
        v.park_factor_3yr AS park_lhb_hr_factor_3yr,
        v.park_factor_3yr AS park_rhb_hr_factor_3yr
    FROM venue_multi_year v
)

SELECT
    gf.game_id,
    COALESCE(vc.park_factor_3yr, gf.park_factor) AS park_factor,
    vc.park_factor_1yr,
    vc.park_factor_3yr,
    vc.park_factor_5yr,
    vc.park_hr_factor_3yr,
    vc.park_2b_factor_3yr,
    vc.park_3b_factor_3yr,
    vc.park_lhb_hr_factor_3yr,
    vc.park_rhb_hr_factor_3yr,
    CASE
        WHEN gf.temp_f IS NOT NULL THEN
            ROUND(100.0 * (530.0 / (460.0 + gf.temp_f)) * (CASE WHEN v.name ILIKE '%Coors%' OR v.city = 'Denver' THEN 0.83 ELSE 1.0 END), 2)
        ELSE NULL
    END AS air_density_index,
    CASE
        WHEN gf.wind_speed_mph IS NOT NULL THEN
            CASE
                WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%to cf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%to lf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%to rf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%out%' THEN gf.wind_speed_mph
                WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%from cf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%from lf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%from rf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%in%' THEN -gf.wind_speed_mph
                WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%dome%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%indoor%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%calm%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%none%' THEN 0.0
                ELSE 0.0
            END
        ELSE NULL
    END AS effective_wind_speed,
    CASE
        WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%to cf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%to lf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%to rf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%out%' THEN 'outfield'
        WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%from cf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%from lf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%from rf%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%in%' THEN 'infield'
        WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%l to r%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%r to l%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%cross%' THEN 'crosswind'
        WHEN lower(COALESCE(gf.wind_dir, '')) LIKE '%dome%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%indoor%' OR (v.roof_type IN ('dome', 'retractable') AND (lower(COALESCE(gf.sky, '')) LIKE '%dome%' OR lower(COALESCE(gf.sky, '')) LIKE '%indoor%')) THEN 'dome'
        WHEN gf.wind_speed_mph = 0 OR lower(COALESCE(gf.wind_dir, '')) LIKE '%calm%' OR lower(COALESCE(gf.wind_dir, '')) LIKE '%none%' THEN 'calm'
        WHEN gf.wind_dir IS NOT NULL AND gf.wind_dir != '' THEN 'other'
        ELSE NULL
    END AS wind_direction_label
FROM gold.game_feature gf
JOIN core.venue v ON v.id = gf.venue_id
LEFT JOIN venue_components vc ON vc.venue_id = gf.venue_id AND vc.target_season = gf.season;
