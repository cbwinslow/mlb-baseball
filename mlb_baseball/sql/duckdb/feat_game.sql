-- feat.game -- one row per regular-season game, at first pitch.
-- DuckDB dialect. Run by mlb_baseball/feat.py AFTER feat_player_form.sql and
-- feat_pitcher_form.sql (it reads feat.pitcher_form). Clock and session
-- variables: see feat_player_form.sql.
--
-- This is the curated wide assembly the first notebook loads and Elo v2
-- (slice 3) consumes. Its form columns MUST equal what a point-in-time
-- retrieval at this game's event_ts would return from the form relations --
-- task 4.1's test enforces that once mlb_research.get_historical_features
-- lands (NOT this file's job / not this slice's agent's job).
--
-- Slice-1 simplifications, both deliberate and documented:
--   * No lineup table exists, so the home/away offensive form is the TEAM's
--     entering form -- that team's players' prior-game batting rolled up at
--     team grain over the same 30d availability-aware window -- not a
--     lineup-weighted mean.
--   * No probable-starter feed is wired to Retrosheet keys, so the starter
--     columns use the ACTUAL starting pitcher (gold.pitching_game.gs = 1) and
--     starter_is_actual is TRUE. Slice 3 / Elo v2 swaps in the probable
--     starter and flips that flag.
--
-- home_win is the outcome label (home_score > away_score), NULL when scores
-- are missing. It is not a feature and is not availability-guarded.

CREATE SCHEMA IF NOT EXISTS feat;

CREATE TABLE IF NOT EXISTS feat.game (
    game_pk         VARCHAR     NOT NULL,
    season          INTEGER,
    game_date       DATE,
    home_team_id    BIGINT,
    away_team_id    BIGINT,
    event_ts        TIMESTAMP   NOT NULL,
    available_ts    TIMESTAMP   NOT NULL,
    created_ts      TIMESTAMP   NOT NULL,
    visible_ts      TIMESTAMP   NOT NULL,
    feature_version VARCHAR     NOT NULL,

    home_k_pct_30d  DOUBLE, away_k_pct_30d  DOUBLE,
    home_bb_pct_30d DOUBLE, away_bb_pct_30d DOUBLE,
    home_obp_30d    DOUBLE, away_obp_30d    DOUBLE,
    home_slg_30d    DOUBLE, away_slg_30d    DOUBLE,

    home_starter_k_minus_bb_pct_30d DOUBLE,
    home_starter_fip_like_30d       DOUBLE,
    home_starter_bf_30d             INTEGER,
    away_starter_k_minus_bb_pct_30d DOUBLE,
    away_starter_fip_like_30d       DOUBLE,
    away_starter_bf_30d             INTEGER,

    starter_is_actual BOOLEAN,
    home_win          BOOLEAN,

    PRIMARY KEY (game_pk, feature_version)
);

DELETE FROM feat.game WHERE feature_version = getvariable('feat_version');

INSERT INTO feat.game
WITH team_game AS (
    SELECT
        bg.team_id,
        g.id AS game_id,
        (g.game_date::TIMESTAMP + coalesce(g.game_number, 0) * INTERVAL 3 HOUR) AS event_ts,
        sum(bg.pa)  AS pa,
        sum(bg.so)  AS so,
        sum(bg.bb)  AS bb,
        sum(bg.h)   AS h,
        sum(bg.ab)  AS ab,
        sum(bg.hbp) AS hbp,
        sum(bg.sf)  AS sf,
        sum(bg.tb)  AS tb
    FROM pg.gold.batting_game AS bg
    INNER JOIN pg.core.game AS g
        ON bg.game_id = g.id AND g.game_type = 'regular'
    GROUP BY bg.team_id, g.id, g.game_date, g.game_number
),

team_roll AS (
    SELECT
        team_id,
        game_id,
        coalesce(sum(pa)  OVER w, 0) AS pa_30d,
        coalesce(sum(so)  OVER w, 0) AS so_30d,
        coalesce(sum(bb)  OVER w, 0) AS bb_30d,
        coalesce(sum(h)   OVER w, 0) AS h_30d,
        coalesce(sum(ab)  OVER w, 0) AS ab_30d,
        coalesce(sum(hbp) OVER w, 0) AS hbp_30d,
        coalesce(sum(sf)  OVER w, 0) AS sf_30d,
        coalesce(sum(tb)  OVER w, 0) AS tb_30d
    FROM team_game
    WINDOW w AS (
        PARTITION BY team_id
        ORDER BY event_ts
        RANGE BETWEEN INTERVAL 30 DAY PRECEDING
            AND getvariable('feat_lag_hours') * INTERVAL 1 HOUR PRECEDING
    )
),

team_form AS (
    SELECT
        team_id,
        game_id,
        CASE WHEN pa_30d > 0 THEN so_30d::DOUBLE / pa_30d END AS k_pct_30d,
        CASE WHEN pa_30d > 0 THEN bb_30d::DOUBLE / pa_30d END AS bb_pct_30d,
        CASE WHEN (ab_30d + bb_30d + hbp_30d + sf_30d) > 0
            THEN (h_30d + bb_30d + hbp_30d)::DOUBLE
                / (ab_30d + bb_30d + hbp_30d + sf_30d) END AS obp_30d,
        CASE WHEN ab_30d > 0 THEN tb_30d::DOUBLE / ab_30d END AS slg_30d
    FROM team_roll
),

starters AS (
    SELECT game_id, team_id, max(player_id) AS player_id
    FROM pg.gold.pitching_game
    WHERE gs = 1
    GROUP BY game_id, team_id
),

games AS (
    SELECT
        g.id AS game_id,
        g.retro_game_id,
        g.season,
        g.game_date,
        g.home_team_id,
        g.away_team_id,
        g.home_score,
        g.away_score,
        (g.game_date::TIMESTAMP + coalesce(g.game_number, 0) * INTERVAL 3 HOUR) AS event_ts
    FROM pg.core.game AS g
    WHERE g.game_type = 'regular'
)

SELECT
    gm.retro_game_id AS game_pk,
    gm.season,
    gm.game_date,
    gm.home_team_id,
    gm.away_team_id,
    gm.event_ts,
    gm.event_ts AS available_ts,
    now()::TIMESTAMP AS created_ts,
    greatest(gm.event_ts, now()::TIMESTAMP) AS visible_ts,
    getvariable('feat_version') AS feature_version,

    th.k_pct_30d  AS home_k_pct_30d,
    ta.k_pct_30d  AS away_k_pct_30d,
    th.bb_pct_30d AS home_bb_pct_30d,
    ta.bb_pct_30d AS away_bb_pct_30d,
    th.obp_30d    AS home_obp_30d,
    ta.obp_30d    AS away_obp_30d,
    th.slg_30d    AS home_slg_30d,
    ta.slg_30d    AS away_slg_30d,

    pfh.k_minus_bb_pct_30d AS home_starter_k_minus_bb_pct_30d,
    pfh.fip_like_30d       AS home_starter_fip_like_30d,
    pfh.bf_30d             AS home_starter_bf_30d,
    pfa.k_minus_bb_pct_30d AS away_starter_k_minus_bb_pct_30d,
    pfa.fip_like_30d       AS away_starter_fip_like_30d,
    pfa.bf_30d             AS away_starter_bf_30d,

    TRUE AS starter_is_actual,
    CASE WHEN gm.home_score IS NOT NULL AND gm.away_score IS NOT NULL
        THEN gm.home_score > gm.away_score END AS home_win
FROM games AS gm
LEFT JOIN team_form AS th
    ON th.team_id = gm.home_team_id AND th.game_id = gm.game_id
LEFT JOIN team_form AS ta
    ON ta.team_id = gm.away_team_id AND ta.game_id = gm.game_id
LEFT JOIN starters AS sh
    ON sh.game_id = gm.game_id AND sh.team_id = gm.home_team_id
LEFT JOIN starters AS sa
    ON sa.game_id = gm.game_id AND sa.team_id = gm.away_team_id
LEFT JOIN feat.pitcher_form AS pfh
    ON pfh.player_id = sh.player_id
    AND pfh.retro_game_id = gm.retro_game_id
    AND pfh.feature_version = getvariable('feat_version')
LEFT JOIN feat.pitcher_form AS pfa
    ON pfa.player_id = sa.player_id
    AND pfa.retro_game_id = gm.retro_game_id
    AND pfa.feature_version = getvariable('feat_version');
