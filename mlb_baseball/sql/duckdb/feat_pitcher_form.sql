-- feat.pitcher_form -- one row per (player_id, event_ts, feature_version).
-- Pitcher-grain twin of feat_player_form.sql: identical clock, identical
-- windows (7d, 30d, std), identical availability-aware frame end
-- (feat_lag_hours HOUR PRECEDING), identical append-only semantics. See
-- feat_player_form.sql for the full contract narrative.
--
-- Ships only what a game-grain consumer (feat.game / Elo v2) needs -- this is
-- not the start of a full pitcher grain. Exposure is bf_<w> (batters faced)
-- so a start-count window stays re-derivable. Rates: k_pct (so/bf),
-- bb_pct (bb/bf), k_minus_bb_pct, ra9 (r*27/outs, NULL when outs = 0),
-- fip_like ((13*hr + 3*(bb+hbp) - 2*so)/(outs/3.0) + 3.1, a fixed FIP
-- constant of 3.1, NULL when outs = 0). EB shrink for k_pct and bb_pct only,
-- m = 100 batters faced, prior = season-to-date league rate (so/bf, bb/bf)
-- as of event_ts, falling back to the prior season's full league rate.

CREATE SCHEMA IF NOT EXISTS feat;

CREATE TABLE IF NOT EXISTS feat.pitcher_form (
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

    bf_7d INTEGER, so_num_7d INTEGER, bb_num_7d INTEGER, r_num_7d INTEGER,
    hr_num_7d INTEGER, outs_num_7d INTEGER, hbp_num_7d INTEGER,
    k_pct_7d DOUBLE, bb_pct_7d DOUBLE, k_minus_bb_pct_7d DOUBLE,
    ra9_7d DOUBLE, fip_like_7d DOUBLE,
    k_pct_shrunk_7d DOUBLE, bb_pct_shrunk_7d DOUBLE,
    league_k_pct_prior_7d DOUBLE, league_bb_pct_prior_7d DOUBLE,

    bf_30d INTEGER, so_num_30d INTEGER, bb_num_30d INTEGER, r_num_30d INTEGER,
    hr_num_30d INTEGER, outs_num_30d INTEGER, hbp_num_30d INTEGER,
    k_pct_30d DOUBLE, bb_pct_30d DOUBLE, k_minus_bb_pct_30d DOUBLE,
    ra9_30d DOUBLE, fip_like_30d DOUBLE,
    k_pct_shrunk_30d DOUBLE, bb_pct_shrunk_30d DOUBLE,
    league_k_pct_prior_30d DOUBLE, league_bb_pct_prior_30d DOUBLE,

    bf_std INTEGER, so_num_std INTEGER, bb_num_std INTEGER, r_num_std INTEGER,
    hr_num_std INTEGER, outs_num_std INTEGER, hbp_num_std INTEGER,
    k_pct_std DOUBLE, bb_pct_std DOUBLE, k_minus_bb_pct_std DOUBLE,
    ra9_std DOUBLE, fip_like_std DOUBLE,
    k_pct_shrunk_std DOUBLE, bb_pct_shrunk_std DOUBLE,
    league_k_pct_prior_std DOUBLE, league_bb_pct_prior_std DOUBLE,

    PRIMARY KEY (player_id, event_ts, feature_version)
);

DELETE FROM feat.pitcher_form WHERE feature_version = getvariable('feat_version');

INSERT INTO feat.pitcher_form
WITH src AS (
    SELECT
        pit.player_id,
        max(g.retro_game_id)                                                   AS retro_game_id,
        max(pit.season)                                                        AS season,
        max(pit.team_id)                                                       AS team_id,
        (g.game_date::TIMESTAMP + coalesce(g.game_number, 0) * INTERVAL 3 HOUR) AS event_ts,
        sum(pit.bf)   AS bf,
        sum(pit.so)   AS so,
        sum(pit.bb)   AS bb,
        sum(pit.r)    AS r,
        sum(pit.hr)   AS hr,
        sum(pit.outs) AS outs,
        sum(pit.hbp)  AS hbp
    FROM pg.gold.pitching_game AS pit
    INNER JOIN pg.core.game AS g
        ON pit.game_id = g.id AND g.game_type = 'regular'
    GROUP BY pit.player_id, g.game_date, g.game_number
),

league_ts AS (
    SELECT
        season,
        event_ts,
        count(DISTINCT retro_game_id) AS n_games,
        sum(so)                       AS so,
        sum(bb)                       AS bb,
        sum(bf)                       AS bf
    FROM src
    GROUP BY season, event_ts
),

league_running AS (
    SELECT
        season,
        event_ts,
        coalesce(sum(n_games) OVER w, 0) AS cum_games,
        coalesce(sum(so) OVER w, 0)      AS cum_so,
        coalesce(sum(bb) OVER w, 0)      AS cum_bb,
        coalesce(sum(bf) OVER w, 0)      AS cum_bf
    FROM league_ts
    WINDOW w AS (
        PARTITION BY season
        ORDER BY event_ts
        RANGE BETWEEN UNBOUNDED PRECEDING
            AND getvariable('feat_lag_hours') * INTERVAL 1 HOUR PRECEDING
    )
),

league_season AS (
    SELECT season, sum(so) AS so, sum(bb) AS bb, sum(bf) AS bf
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

        coalesce(sum(src.bf)   OVER w7, 0) AS bf_7d,
        coalesce(sum(src.so)   OVER w7, 0) AS so_num_7d,
        coalesce(sum(src.bb)   OVER w7, 0) AS bb_num_7d,
        coalesce(sum(src.r)    OVER w7, 0) AS r_num_7d,
        coalesce(sum(src.hr)   OVER w7, 0) AS hr_num_7d,
        coalesce(sum(src.outs) OVER w7, 0) AS outs_num_7d,
        coalesce(sum(src.hbp)  OVER w7, 0) AS hbp_num_7d,

        coalesce(sum(src.bf)   OVER w30, 0) AS bf_30d,
        coalesce(sum(src.so)   OVER w30, 0) AS so_num_30d,
        coalesce(sum(src.bb)   OVER w30, 0) AS bb_num_30d,
        coalesce(sum(src.r)    OVER w30, 0) AS r_num_30d,
        coalesce(sum(src.hr)   OVER w30, 0) AS hr_num_30d,
        coalesce(sum(src.outs) OVER w30, 0) AS outs_num_30d,
        coalesce(sum(src.hbp)  OVER w30, 0) AS hbp_num_30d,

        coalesce(sum(src.bf)   OVER wstd, 0) AS bf_std,
        coalesce(sum(src.so)   OVER wstd, 0) AS so_num_std,
        coalesce(sum(src.bb)   OVER wstd, 0) AS bb_num_std,
        coalesce(sum(src.r)    OVER wstd, 0) AS r_num_std,
        coalesce(sum(src.hr)   OVER wstd, 0) AS hr_num_std,
        coalesce(sum(src.outs) OVER wstd, 0) AS outs_num_std,
        coalesce(sum(src.hbp)  OVER wstd, 0) AS hbp_num_std
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
            WHEN lr.cum_games >= 5 AND lr.cum_bf > 0 THEN lr.cum_so::DOUBLE / lr.cum_bf
            WHEN ls.bf > 0 THEN ls.so::DOUBLE / ls.bf
        END AS league_k_prior,
        CASE
            WHEN lr.cum_games >= 5 AND lr.cum_bf > 0 THEN lr.cum_bb::DOUBLE / lr.cum_bf
            WHEN ls.bf > 0 THEN ls.bb::DOUBLE / ls.bf
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
    -- This row's VALUE is the pitcher's form *entering* this game -- prior
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

    bf_7d, so_num_7d, bb_num_7d, r_num_7d, hr_num_7d, outs_num_7d, hbp_num_7d,
    CASE WHEN bf_7d > 0 THEN so_num_7d::DOUBLE / bf_7d END AS k_pct_7d,
    CASE WHEN bf_7d > 0 THEN bb_num_7d::DOUBLE / bf_7d END AS bb_pct_7d,
    CASE WHEN bf_7d > 0
        THEN (so_num_7d - bb_num_7d)::DOUBLE / bf_7d END AS k_minus_bb_pct_7d,
    CASE WHEN outs_num_7d > 0
        THEN r_num_7d * 27.0 / outs_num_7d END AS ra9_7d,
    CASE WHEN outs_num_7d > 0
        THEN (13 * hr_num_7d + 3 * (bb_num_7d + hbp_num_7d) - 2 * so_num_7d)
            / (outs_num_7d / 3.0) + 3.1 END AS fip_like_7d,
    (so_num_7d + 100 * league_k_prior) / (bf_7d + 100) AS k_pct_shrunk_7d,
    (bb_num_7d + 100 * league_bb_prior) / (bf_7d + 100) AS bb_pct_shrunk_7d,
    league_k_prior AS league_k_pct_prior_7d,
    league_bb_prior AS league_bb_pct_prior_7d,

    bf_30d, so_num_30d, bb_num_30d, r_num_30d, hr_num_30d, outs_num_30d, hbp_num_30d,
    CASE WHEN bf_30d > 0 THEN so_num_30d::DOUBLE / bf_30d END AS k_pct_30d,
    CASE WHEN bf_30d > 0 THEN bb_num_30d::DOUBLE / bf_30d END AS bb_pct_30d,
    CASE WHEN bf_30d > 0
        THEN (so_num_30d - bb_num_30d)::DOUBLE / bf_30d END AS k_minus_bb_pct_30d,
    CASE WHEN outs_num_30d > 0
        THEN r_num_30d * 27.0 / outs_num_30d END AS ra9_30d,
    CASE WHEN outs_num_30d > 0
        THEN (13 * hr_num_30d + 3 * (bb_num_30d + hbp_num_30d) - 2 * so_num_30d)
            / (outs_num_30d / 3.0) + 3.1 END AS fip_like_30d,
    (so_num_30d + 100 * league_k_prior) / (bf_30d + 100) AS k_pct_shrunk_30d,
    (bb_num_30d + 100 * league_bb_prior) / (bf_30d + 100) AS bb_pct_shrunk_30d,
    league_k_prior AS league_k_pct_prior_30d,
    league_bb_prior AS league_bb_pct_prior_30d,

    bf_std, so_num_std, bb_num_std, r_num_std, hr_num_std, outs_num_std, hbp_num_std,
    CASE WHEN bf_std > 0 THEN so_num_std::DOUBLE / bf_std END AS k_pct_std,
    CASE WHEN bf_std > 0 THEN bb_num_std::DOUBLE / bf_std END AS bb_pct_std,
    CASE WHEN bf_std > 0
        THEN (so_num_std - bb_num_std)::DOUBLE / bf_std END AS k_minus_bb_pct_std,
    CASE WHEN outs_num_std > 0
        THEN r_num_std * 27.0 / outs_num_std END AS ra9_std,
    CASE WHEN outs_num_std > 0
        THEN (13 * hr_num_std + 3 * (bb_num_std + hbp_num_std) - 2 * so_num_std)
            / (outs_num_std / 3.0) + 3.1 END AS fip_like_std,
    (so_num_std + 100 * league_k_prior) / (bf_std + 100) AS k_pct_shrunk_std,
    (bb_num_std + 100 * league_bb_prior) / (bf_std + 100) AS bb_pct_shrunk_std,
    league_k_prior AS league_k_pct_prior_std,
    league_bb_prior AS league_bb_pct_prior_std
FROM priced;
