MODEL (
  name gold.team_woba,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column game_date
  ),
  start '2021-01-01',
  cron '@monthly',
  grain (game_id, team_id),
  description '
    Port of mlb_baseball/model/offense.py::compute (ADR-036) -- point-in-
    time, no-leakage, WITHIN-SEASON rolling team wOBA, FanGraphs'' own
    published formula, reconstructed from raw.retrosheet_event''s per-play
    data. One row per (game_id, team_id) here, entering-value semantics
    identical to the original: the rolling SUM window is ROWS BETWEEN
    UNBOUNDED PRECEDING AND 1 PRECEDING, partitioned by (team_id, season)
    -- a team''s wOBA "entering" a given game never includes that game''s
    own plate appearances, so it is safe to use as a pre-game model
    feature.

    Shape difference from production, deliberate for this spike:
    gold.game_feature stores this as two columns (home_woba/away_woba) on
    one row per GAME. This model instead stores one row per (game, team)
    -- a tidy/long dimensional shape -- which the original wide shape can
    be reconstructed from with a single self-join/pivot if a downstream
    consumer needs it (see transforms/README.md). Chosen deliberately for
    this spike rather than replicating the wide shape verbatim, since the
    long shape is the more natural SQLMesh incremental grain (game, team)
    and avoids a same-game home/away self-join inside this model itself.

    Incremental by game_date: adding a new season only recomputes that
    season''s rows. The WINDOW clause still needs that season''s full game
    log to compute correctly (PARTITION BY team_id, season resets every
    season, so no cross-season history is needed) -- this model computes
    the window over the model''s FULL available season history every run
    (there is no cheaper correct way to compute a cumulative sum), then
    only EMITS rows inside the incremental date range being processed.
    That is a real, worth-flagging SQLMesh incremental limitation for
    this shape of transform, not a free win -- see transforms/README.md
    "Incremental models" for the honest accounting.
  ',
  audits (
    unique_combination_of_columns(columns := (game_id, team_id)),
    not_null(columns := (game_id, team_id)),
    team_woba_plausible_range()
  )
);

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
rolling AS (
    SELECT game_id, season, game_date, team_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum,
        SUM(b3) OVER w AS b3_sum, SUM(hr) OVER w AS hr_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
)
SELECT
    game_id,
    team_id,
    season,
    game_date,
    CASE WHEN (ab_sum + ubb_sum + sf_sum + hbp_sum) > 0 THEN
        (0.690 * ubb_sum + 0.722 * hbp_sum + 0.878 * b1_sum
            + 1.242 * b2_sum + 1.569 * b3_sum + 2.015 * hr_sum)
        / (ab_sum + ubb_sum + sf_sum + hbp_sum)
    END AS woba
FROM rolling
WHERE game_date BETWEEN @start_ds AND @end_ds
