-- feat.player_form -- one row per (player_id, event_ts, feature_version).
-- DuckDB dialect. Run by mlb_baseball/feat.py against a Postgres database
-- ATTACHed READ_ONLY as `pg`. Build-time parameters come from DuckDB session
-- variables feat.py sets before running this file:
--   getvariable('feat_version')    -- the feature_version tag ('v1')
--   getvariable('feat_lag_hours')  -- hours from first pitch to box-score
--                                     availability (feat.AVAILABLE_LAG_HOURS)
--
-- Clock (design D5, and the progress note in tasks.md):
--   event_ts     = game_date::TIMESTAMP + game_number * INTERVAL 3 HOUR
--                  (fictional absolute time, real ordering: a single game ->
--                   midnight, doubleheader game 1 -> 03:00, game 2 -> 06:00)
--   available_ts = event_ts  -- the row's value is entering form (prior
--                  games only); it is knowable at first pitch. The
--                  feat_lag_hours lag lives ONLY in the window frame below.
--   created_ts   = now() at build time -- audit metadata, uniform across a
--                  full rebuild, not a retrieval gate (see feat.py)
--   visible_ts   = event_ts  -- retrieval ASOF key
--
-- Windows are COLUMNS, never rows: 7d, 30d, std (season-to-date). Each rate
-- ships with its numerator(s) and its exposure (pa_<w>) so a PA-based window
-- is re-derivable. Every window frame ends at `feat_lag_hours HOUR PRECEDING`
-- rather than CURRENT ROW: that single bound excludes the entering game AND
-- any earlier same-day line whose box score is not yet available (the
-- doubleheader case -- game 1 is invisible to game 2). Rates are computed
-- from summed numerators / summed denominators, never averaged from per-game
-- rates. A rate is NULL when its denominator is 0.
--
-- EB shrink (k% and bb% only): (num + m*prior) / (denom + m), m = 100, stored
-- in shrink_m. `prior` is the season-to-date league rate as of event_ts (all
-- games whose box score is available by then); if fewer than 5 league games
-- have been played that season, it falls back to the prior season's full
-- league rate; if that is also absent the shrunk column is NULL.
--
-- Append-only: DELETE the current feature_version then re-INSERT it; a
-- different feature_version leaves earlier rows byte-identical.

CREATE SCHEMA IF NOT EXISTS feat;

CREATE TABLE IF NOT EXISTS feat.player_form (
    player_id       BIGINT      NOT NULL,
    retro_game_id   VARCHAR,
    season          INTEGER,
    team_id         BIGINT,
    event_ts        TIMESTAMP   NOT NULL,
    available_ts    TIMESTAMP   NOT NULL,
    created_ts      TIMESTAMP   NOT NULL,
    visible_ts      TIMESTAMP   NOT NULL,
    feature_version VARCHAR     NOT NULL,
    shrink_m        INTEGER     NOT NULL,

    pa_7d INTEGER, so_num_7d INTEGER, bb_num_7d INTEGER, h_num_7d INTEGER,
    ab_num_7d INTEGER, tb_num_7d INTEGER, hbp_num_7d INTEGER, sf_num_7d INTEGER,
    hr_num_7d INTEGER, b1b2b3_num_7d INTEGER,
    k_pct_7d DOUBLE, bb_pct_7d DOUBLE, obp_7d DOUBLE, slg_7d DOUBLE,
    iso_7d DOUBLE, babip_7d DOUBLE,
    k_pct_shrunk_7d DOUBLE, bb_pct_shrunk_7d DOUBLE,
    league_k_pct_prior_7d DOUBLE, league_bb_pct_prior_7d DOUBLE,

    pa_30d INTEGER, so_num_30d INTEGER, bb_num_30d INTEGER, h_num_30d INTEGER,
    ab_num_30d INTEGER, tb_num_30d INTEGER, hbp_num_30d INTEGER, sf_num_30d INTEGER,
    hr_num_30d INTEGER, b1b2b3_num_30d INTEGER,
    k_pct_30d DOUBLE, bb_pct_30d DOUBLE, obp_30d DOUBLE, slg_30d DOUBLE,
    iso_30d DOUBLE, babip_30d DOUBLE,
    k_pct_shrunk_30d DOUBLE, bb_pct_shrunk_30d DOUBLE,
    league_k_pct_prior_30d DOUBLE, league_bb_pct_prior_30d DOUBLE,

    pa_std INTEGER, so_num_std INTEGER, bb_num_std INTEGER, h_num_std INTEGER,
    ab_num_std INTEGER, tb_num_std INTEGER, hbp_num_std INTEGER, sf_num_std INTEGER,
    hr_num_std INTEGER, b1b2b3_num_std INTEGER,
    k_pct_std DOUBLE, bb_pct_std DOUBLE, obp_std DOUBLE, slg_std DOUBLE,
    iso_std DOUBLE, babip_std DOUBLE,
    k_pct_shrunk_std DOUBLE, bb_pct_shrunk_std DOUBLE,
    league_k_pct_prior_std DOUBLE, league_bb_pct_prior_std DOUBLE,

    PRIMARY KEY (player_id, event_ts, feature_version)
);

DELETE FROM feat.player_form WHERE feature_version = getvariable('feat_version');

INSERT INTO feat.player_form
WITH src AS (
    SELECT
        bg.player_id,
        max(g.retro_game_id)                                                   AS retro_game_id,
        max(bg.season)                                                         AS season,
        max(bg.team_id)                                                        AS team_id,
        (g.game_date::TIMESTAMP + coalesce(g.game_number, 0) * INTERVAL 3 HOUR) AS event_ts,
        sum(bg.pa)  AS pa,
        sum(bg.so)  AS so,
        sum(bg.bb)  AS bb,
        sum(bg.h)   AS h,
        sum(bg.ab)  AS ab,
        sum(bg.tb)  AS tb,
        sum(bg.hbp) AS hbp,
        sum(bg.sf)  AS sf,
        sum(bg.hr)  AS hr
    FROM pg.gold.batting_game AS bg
    INNER JOIN pg.core.game AS g
        ON bg.game_id = g.id AND g.game_type = 'regular'
    GROUP BY bg.player_id, g.game_date, g.game_number
),

-- league counting lines collapsed to one row per (season, event_ts)
league_ts AS (
    SELECT
        season,
        event_ts,
        count(DISTINCT retro_game_id) AS n_games,
        sum(so)                       AS so,
        sum(bb)                       AS bb,
        sum(pa)                       AS pa
    FROM src
    GROUP BY season, event_ts
),

-- season-to-date league totals as of each event_ts (availability-aware:
-- the frame ends feat_lag_hours before the row, same rule as the player
-- windows)
league_running AS (
    SELECT
        season,
        event_ts,
        coalesce(sum(n_games) OVER w, 0) AS cum_games,
        coalesce(sum(so) OVER w, 0)      AS cum_so,
        coalesce(sum(bb) OVER w, 0)      AS cum_bb,
        coalesce(sum(pa) OVER w, 0)      AS cum_pa
    FROM league_ts
    WINDOW w AS (
        PARTITION BY season
        ORDER BY event_ts
        RANGE BETWEEN UNBOUNDED PRECEDING
            AND getvariable('feat_lag_hours') * INTERVAL 1 HOUR PRECEDING
    )
),

-- prior-season full league rate, the fallback prior
league_season AS (
    SELECT season, sum(so) AS so, sum(bb) AS bb, sum(pa) AS pa
    FROM src
    GROUP BY season
),

windowed AS (
    SELECT
        src.player_id,
        src.retro_game_id,
        src.season,
        src.team_id,
        src.event_ts,

        coalesce(sum(src.pa)  OVER w7, 0) AS pa_7d,
        coalesce(sum(src.so)  OVER w7, 0) AS so_num_7d,
        coalesce(sum(src.bb)  OVER w7, 0) AS bb_num_7d,
        coalesce(sum(src.h)   OVER w7, 0) AS h_num_7d,
        coalesce(sum(src.ab)  OVER w7, 0) AS ab_num_7d,
        coalesce(sum(src.tb)  OVER w7, 0) AS tb_num_7d,
        coalesce(sum(src.hbp) OVER w7, 0) AS hbp_num_7d,
        coalesce(sum(src.sf)  OVER w7, 0) AS sf_num_7d,
        coalesce(sum(src.hr)  OVER w7, 0) AS hr_num_7d,

        coalesce(sum(src.pa)  OVER w30, 0) AS pa_30d,
        coalesce(sum(src.so)  OVER w30, 0) AS so_num_30d,
        coalesce(sum(src.bb)  OVER w30, 0) AS bb_num_30d,
        coalesce(sum(src.h)   OVER w30, 0) AS h_num_30d,
        coalesce(sum(src.ab)  OVER w30, 0) AS ab_num_30d,
        coalesce(sum(src.tb)  OVER w30, 0) AS tb_num_30d,
        coalesce(sum(src.hbp) OVER w30, 0) AS hbp_num_30d,
        coalesce(sum(src.sf)  OVER w30, 0) AS sf_num_30d,
        coalesce(sum(src.hr)  OVER w30, 0) AS hr_num_30d,

        coalesce(sum(src.pa)  OVER wstd, 0) AS pa_std,
        coalesce(sum(src.so)  OVER wstd, 0) AS so_num_std,
        coalesce(sum(src.bb)  OVER wstd, 0) AS bb_num_std,
        coalesce(sum(src.h)   OVER wstd, 0) AS h_num_std,
        coalesce(sum(src.ab)  OVER wstd, 0) AS ab_num_std,
        coalesce(sum(src.tb)  OVER wstd, 0) AS tb_num_std,
        coalesce(sum(src.hbp) OVER wstd, 0) AS hbp_num_std,
        coalesce(sum(src.sf)  OVER wstd, 0) AS sf_num_std,
        coalesce(sum(src.hr)  OVER wstd, 0) AS hr_num_std
    FROM src
    WINDOW
        w7 AS (
            PARTITION BY src.player_id
            ORDER BY src.event_ts
            RANGE BETWEEN INTERVAL 7 DAY PRECEDING
                AND getvariable('feat_lag_hours') * INTERVAL 1 HOUR PRECEDING
        ),
        w30 AS (
            PARTITION BY src.player_id
            ORDER BY src.event_ts
            RANGE BETWEEN INTERVAL 30 DAY PRECEDING
                AND getvariable('feat_lag_hours') * INTERVAL 1 HOUR PRECEDING
        ),
        wstd AS (
            PARTITION BY src.player_id, src.season
            ORDER BY src.event_ts
            RANGE BETWEEN UNBOUNDED PRECEDING
                AND getvariable('feat_lag_hours') * INTERVAL 1 HOUR PRECEDING
        )
),

priced AS (
    SELECT
        w.*,
        CASE
            WHEN lr.cum_games >= 5 AND lr.cum_pa > 0 THEN lr.cum_so::DOUBLE / lr.cum_pa
            WHEN ls.pa > 0 THEN ls.so::DOUBLE / ls.pa
        END AS league_k_prior,
        CASE
            WHEN lr.cum_games >= 5 AND lr.cum_pa > 0 THEN lr.cum_bb::DOUBLE / lr.cum_pa
            WHEN ls.pa > 0 THEN ls.bb::DOUBLE / ls.pa
        END AS league_bb_prior
    FROM windowed AS w
    LEFT JOIN league_running AS lr
        ON lr.season = w.season AND lr.event_ts = w.event_ts
    LEFT JOIN league_season AS ls
        ON ls.season = w.season - 1
)

SELECT
    player_id,
    retro_game_id,
    season,
    team_id,
    event_ts,
    -- This row's VALUE is the batter's form *entering* this game -- prior
    -- completed games only, and the window frame below already excludes any
    -- game less than feat_lag_hours old. So the value is knowable at first
    -- pitch: available_ts = event_ts. The feat_lag_hours lag lives only in the
    -- window frame (which inputs are eligible), not here.
    event_ts AS available_ts,
    -- Audit metadata: when THIS build wrote the row. mlb build is a full
    -- rebuild, so it is uniform across a build and does not gate retrieval.
    -- Incremental builds (a later slice) will fold it into visible_ts.
    now()::TIMESTAMP AS created_ts,
    event_ts AS visible_ts,
    getvariable('feat_version') AS feature_version,
    100 AS shrink_m,

    pa_7d, so_num_7d, bb_num_7d, h_num_7d, ab_num_7d, tb_num_7d, hbp_num_7d,
    sf_num_7d, hr_num_7d,
    (h_num_7d - hr_num_7d) AS b1b2b3_num_7d,
    CASE WHEN pa_7d > 0 THEN so_num_7d::DOUBLE / pa_7d END AS k_pct_7d,
    CASE WHEN pa_7d > 0 THEN bb_num_7d::DOUBLE / pa_7d END AS bb_pct_7d,
    CASE WHEN (ab_num_7d + bb_num_7d + hbp_num_7d + sf_num_7d) > 0
        THEN (h_num_7d + bb_num_7d + hbp_num_7d)::DOUBLE
            / (ab_num_7d + bb_num_7d + hbp_num_7d + sf_num_7d) END AS obp_7d,
    CASE WHEN ab_num_7d > 0 THEN tb_num_7d::DOUBLE / ab_num_7d END AS slg_7d,
    CASE WHEN ab_num_7d > 0
        THEN (tb_num_7d - h_num_7d)::DOUBLE / ab_num_7d END AS iso_7d,
    CASE WHEN (ab_num_7d - so_num_7d - hr_num_7d + sf_num_7d) > 0
        THEN (h_num_7d - hr_num_7d)::DOUBLE
            / (ab_num_7d - so_num_7d - hr_num_7d + sf_num_7d) END AS babip_7d,
    (so_num_7d + 100 * league_k_prior) / (pa_7d + 100) AS k_pct_shrunk_7d,
    (bb_num_7d + 100 * league_bb_prior) / (pa_7d + 100) AS bb_pct_shrunk_7d,
    league_k_prior AS league_k_pct_prior_7d,
    league_bb_prior AS league_bb_pct_prior_7d,

    pa_30d, so_num_30d, bb_num_30d, h_num_30d, ab_num_30d, tb_num_30d, hbp_num_30d,
    sf_num_30d, hr_num_30d,
    (h_num_30d - hr_num_30d) AS b1b2b3_num_30d,
    CASE WHEN pa_30d > 0 THEN so_num_30d::DOUBLE / pa_30d END AS k_pct_30d,
    CASE WHEN pa_30d > 0 THEN bb_num_30d::DOUBLE / pa_30d END AS bb_pct_30d,
    CASE WHEN (ab_num_30d + bb_num_30d + hbp_num_30d + sf_num_30d) > 0
        THEN (h_num_30d + bb_num_30d + hbp_num_30d)::DOUBLE
            / (ab_num_30d + bb_num_30d + hbp_num_30d + sf_num_30d) END AS obp_30d,
    CASE WHEN ab_num_30d > 0 THEN tb_num_30d::DOUBLE / ab_num_30d END AS slg_30d,
    CASE WHEN ab_num_30d > 0
        THEN (tb_num_30d - h_num_30d)::DOUBLE / ab_num_30d END AS iso_30d,
    CASE WHEN (ab_num_30d - so_num_30d - hr_num_30d + sf_num_30d) > 0
        THEN (h_num_30d - hr_num_30d)::DOUBLE
            / (ab_num_30d - so_num_30d - hr_num_30d + sf_num_30d) END AS babip_30d,
    (so_num_30d + 100 * league_k_prior) / (pa_30d + 100) AS k_pct_shrunk_30d,
    (bb_num_30d + 100 * league_bb_prior) / (pa_30d + 100) AS bb_pct_shrunk_30d,
    league_k_prior AS league_k_pct_prior_30d,
    league_bb_prior AS league_bb_pct_prior_30d,

    pa_std, so_num_std, bb_num_std, h_num_std, ab_num_std, tb_num_std, hbp_num_std,
    sf_num_std, hr_num_std,
    (h_num_std - hr_num_std) AS b1b2b3_num_std,
    CASE WHEN pa_std > 0 THEN so_num_std::DOUBLE / pa_std END AS k_pct_std,
    CASE WHEN pa_std > 0 THEN bb_num_std::DOUBLE / pa_std END AS bb_pct_std,
    CASE WHEN (ab_num_std + bb_num_std + hbp_num_std + sf_num_std) > 0
        THEN (h_num_std + bb_num_std + hbp_num_std)::DOUBLE
            / (ab_num_std + bb_num_std + hbp_num_std + sf_num_std) END AS obp_std,
    CASE WHEN ab_num_std > 0 THEN tb_num_std::DOUBLE / ab_num_std END AS slg_std,
    CASE WHEN ab_num_std > 0
        THEN (tb_num_std - h_num_std)::DOUBLE / ab_num_std END AS iso_std,
    CASE WHEN (ab_num_std - so_num_std - hr_num_std + sf_num_std) > 0
        THEN (h_num_std - hr_num_std)::DOUBLE
            / (ab_num_std - so_num_std - hr_num_std + sf_num_std) END AS babip_std,
    (so_num_std + 100 * league_k_prior) / (pa_std + 100) AS k_pct_shrunk_std,
    (bb_num_std + 100 * league_bb_prior) / (pa_std + 100) AS bb_pct_shrunk_std,
    league_k_prior AS league_k_pct_prior_std,
    league_bb_prior AS league_bb_pct_prior_std
FROM priced;
