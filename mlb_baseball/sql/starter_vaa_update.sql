-- Entering four-seam Vertical Approach Angle (degrees) for listed starters.
-- Chamberlain / Pavlidis, FanGraphs 2022-02-01 (Statcast 9-param kinematics):
--   vy_f = -sqrt(vy0^2 - 2*ay*(50 - 17/12))
--   t    = (vy_f - vy0) / ay
--   vz_f = vz0 + az*t
--   VAA  = degrees(-atan(vz_f / vy_f))
-- Point-in-time: window ends at the prior game.

WITH regular_games AS (
    SELECT
        g.id AS game_id,
        g.season,
        g.game_date,
        g.game_number,
        g.game_pk
    FROM core.game AS g
    WHERE lower(g.game_type) = 'regular'
        AND g.game_pk IS NOT NULL
),

kinematics AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        sp.pitcher AS pitcher_mlbam_id,
        NULLIF(sp.vy0, '')::double precision AS vy0,
        NULLIF(sp.ay, '')::double precision AS ay,
        NULLIF(sp.vz0, '')::double precision AS vz0,
        NULLIF(sp.az, '')::double precision AS az
    FROM regular_games AS rg
    INNER JOIN raw.statcast_pitch AS sp ON sp.game_pk = rg.game_pk
    WHERE sp.pitch_type = 'FF'
        AND NULLIF(sp.pitcher, '') IS NOT NULL
        AND NULLIF(sp.vy0, '') IS NOT NULL
        AND NULLIF(sp.ay, '') IS NOT NULL
        AND NULLIF(sp.vz0, '') IS NOT NULL
        AND NULLIF(sp.az, '') IS NOT NULL
        AND NULLIF(sp.ay, '')::double precision <> 0
),

pitch_vaa AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_mlbam_id,
        degrees(-atan(vz_f / vy_f)) AS vaa_deg
    FROM (
        SELECT
            game_id,
            season,
            game_date,
            game_number,
            pitcher_mlbam_id,
            -sqrt(vy0 * vy0 - 2.0 * ay * (50.0 - 17.0 / 12.0)) AS vy_f,
            vz0 + az * (
                (
                    -sqrt(vy0 * vy0 - 2.0 * ay * (50.0 - 17.0 / 12.0))
                    - vy0
                ) / ay
            ) AS vz_f
        FROM kinematics
        WHERE vy0 * vy0 - 2.0 * ay * (50.0 - 17.0 / 12.0) > 0
    ) AS plate
    WHERE vy_f <> 0
),

daily AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_mlbam_id,
        avg(vaa_deg) AS vaa_mean,
        count(*) AS ff_n
    FROM pitch_vaa
    GROUP BY game_id, season, game_date, game_number, pitcher_mlbam_id
),

-- Every listed start, even a day with zero four-seamers, so entering VAA
-- still comes from prior games (the window is 1 PRECEDING).
target_starts AS (
    SELECT
        f.game_id,
        f.season,
        f.game_date,
        f.game_number,
        hp.mlbam_id::text AS pitcher_mlbam_id
    FROM gold.game_feature AS f
    INNER JOIN core.player AS hp ON hp.id = f.home_starter_id
    WHERE f.game_id IS NOT NULL AND hp.mlbam_id IS NOT NULL
    UNION
    SELECT
        f.game_id,
        f.season,
        f.game_date,
        f.game_number,
        ap.mlbam_id::text
    FROM gold.game_feature AS f
    INNER JOIN core.player AS ap ON ap.id = f.away_starter_id
    WHERE f.game_id IS NOT NULL AND ap.mlbam_id IS NOT NULL
),

combined AS (
    SELECT
        t.game_id,
        t.pitcher_mlbam_id,
        t.season,
        t.game_date,
        t.game_number,
        coalesce(d.vaa_mean, 0) AS vaa_mean,
        coalesce(d.ff_n, 0) AS ff_n
    FROM target_starts AS t
    LEFT JOIN daily AS d
        ON d.game_id = t.game_id
        AND d.pitcher_mlbam_id = t.pitcher_mlbam_id
),

rolling AS (
    SELECT
        game_id,
        pitcher_mlbam_id,
        sum(vaa_mean * ff_n) OVER w AS vaa_weighted,
        sum(ff_n) OVER w AS ff_total
    FROM combined
    WINDOW w AS (
        PARTITION BY pitcher_mlbam_id, season
        ORDER BY game_date, coalesce(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

starter_vaa AS (
    SELECT
        game_id,
        pitcher_mlbam_id,
        CASE
            WHEN ff_total >= %(min_ff)s
                THEN round((vaa_weighted / ff_total)::numeric, 3)
        END AS ff_vaa
    FROM rolling
),

joined AS (
    SELECT
        f.game_instance_key,
        hs.ff_vaa AS home_vaa,
        aws.ff_vaa AS away_vaa
    FROM gold.game_feature AS f
    LEFT JOIN core.player AS hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player AS ap ON ap.id = f.away_starter_id
    LEFT JOIN starter_vaa AS hs
        ON hs.game_id = f.game_id
        AND hs.pitcher_mlbam_id = hp.mlbam_id::text
    LEFT JOIN starter_vaa AS aws
        ON aws.game_id = f.game_id
        AND aws.pitcher_mlbam_id = ap.mlbam_id::text
)

UPDATE gold.game_feature AS gf
SET
    home_starter_ff_vaa = j.home_vaa,
    away_starter_ff_vaa = j.away_vaa
FROM joined AS j
WHERE gf.game_instance_key = j.game_instance_key;
