-- Update gold.game_feature with point-in-time entering Statcast quality of contact
-- and expected metrics (HardHit%, Barrel%, xwOBA, xBA, xSLG) (STA-03).
--
-- Reads Baseball Savant's own pre-computed per-batted-ball expected-stat columns
-- from raw.statcast_pitch (estimated_ba_using_speedangle / estimated_slg_using_
-- speedangle / estimated_woba_using_speedangle, launch_speed, launch_speed_angle)
-- rather than reimplementing a "Statcast" quantity from Retrosheet's coarse
-- batted-ball-type codes and an uncited constant table (2026-09-19 fix -- this
-- file used to join raw.retrosheet_event/raw.retrosheet_gameinfo instead; see
-- mlb_baseball/metrics/statcast_expected_quality_of_contact.yaml for the finding
-- and docs/reference/statcast_glossary.md's own guidance: "Pitch-level: do not
-- invent a second x-model; use Savant's values when landed"). Confirmed directly
-- against production that raw.statcast_pitch actually carries these columns,
-- populated 2015-present (0 rows in the pre-2015 PITCHf/x era, consistent with
-- mlb_baseball/connectors/statcast.py's documented era boundary).
--
-- Hard-Hit% is exit velocity >= 95 mph (MLB glossary: "Hard-Hit Rate").
-- Barrel% uses Savant's own launch_speed_angle = 6 classification (MLB glossary:
-- "Barrel"; confirmed against production data that category 6 has avg EV ~105mph/
-- LA ~26 deg, matching the published Barrel definition), not a reimplemented EV/LA
-- window formula.
-- xwOBA's non-contact linear weights (uBB=0.69, HBP=0.72) are this project's
-- existing fixed wOBA weight set (docs/RESEARCH.md; also used identically in
-- mlb_baseball/sql/team_pitcher_estimators_retrosheet_update.sql), not a new
-- invented constant.
--
-- Strictly zero lookahead: every rolling rate uses ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
-- partitioned by entity and season, with doubleheader chronological tie-breaking.

WITH regular_games AS (
    SELECT
        g.id AS game_id,
        g.game_pk,
        g.season,
        g.game_date,
        g.game_number,
        g.home_team_id,
        g.away_team_id,
        NULLIF(hp.mlbam_id, '') AS home_starter_mlbam_id,
        NULLIF(ap.mlbam_id, '') AS away_starter_mlbam_id
    FROM core.game g
    JOIN gold.game_feature f ON f.game_id = g.id
    LEFT JOIN core.player hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player ap ON ap.id = f.away_starter_id
    WHERE lower(g.game_type) = 'regular'
      AND NULLIF(g.game_pk, '') IS NOT NULL
),

-- One row per plate appearance: Statcast populates `events` only on a PA's
-- terminal pitch (same convention platoon_splits_update.sql relies on via
-- woba_denom). `bb_type IS NOT NULL` is Savant's own batted-ball-event marker
-- (confirmed directly against production: matches real batted-ball outcome
-- events almost exactly, off by <0.01%).
pa_terminal AS (
    SELECT
        sp.game_pk,
        sp.inning_topbot,
        NULLIF(sp.pitcher, '') AS pitcher_mlbam_id,
        sp.events,
        NULLIF(sp.bb_type, '') AS bb_type,
        NULLIF(sp.launch_speed, '')::numeric AS launch_speed,
        NULLIF(sp.launch_speed_angle, '') AS launch_speed_angle,
        COALESCE(NULLIF(sp.estimated_ba_using_speedangle, '')::numeric, 0) AS xba_val,
        COALESCE(NULLIF(sp.estimated_slg_using_speedangle, '')::numeric, 0) AS xslg_val,
        COALESCE(NULLIF(sp.estimated_woba_using_speedangle, '')::numeric, 0) AS xwoba_val
    FROM raw.statcast_pitch sp
    WHERE NULLIF(sp.events, '') IS NOT NULL
),

event_parsed AS (
    SELECT
        pt.game_pk,
        pt.inning_topbot,
        pt.pitcher_mlbam_id,
        CASE WHEN pt.bb_type IS NOT NULL THEN 1 ELSE 0 END AS is_bip,
        CASE WHEN pt.bb_type IS NOT NULL AND pt.launch_speed >= 95 THEN 1 ELSE 0 END AS is_hard_hit,
        CASE WHEN pt.bb_type IS NOT NULL AND pt.launch_speed_angle = '6' THEN 1 ELSE 0 END AS is_barrel,
        CASE
            WHEN pt.bb_type IS NOT NULL OR pt.events IN ('strikeout', 'strikeout_double_play')
            THEN 1 ELSE 0
        END AS is_ab,
        CASE WHEN pt.events IN ('walk', 'intent_walk') THEN 1 ELSE 0 END AS is_bb,
        CASE WHEN pt.events = 'hit_by_pitch' THEN 1 ELSE 0 END AS is_hbp,
        pt.xba_val,
        pt.xslg_val,
        pt.xwoba_val
    FROM pa_terminal pt
),

-- 1. Starting Pitcher game aggregates (only PA where the pitcher on the mound
-- is that game's starter, matched by MLBAM id).
starter_game_agg AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        ep.pitcher_mlbam_id,
        COUNT(*) AS pa_cnt,
        SUM(ep.is_ab) AS ab_cnt,
        SUM(ep.is_bip) AS bip_cnt,
        SUM(ep.is_hard_hit) AS hard_hit_cnt,
        SUM(ep.is_barrel) AS barrel_cnt,
        SUM(ep.xba_val) FILTER (WHERE ep.is_ab = 1) AS xba_sum,
        SUM(ep.xslg_val) FILTER (WHERE ep.is_ab = 1) AS xslg_sum,
        SUM(ep.xwoba_val) AS xwoba_contact_sum,
        SUM(ep.is_bb) AS bb_cnt,
        SUM(ep.is_hbp) AS hbp_cnt
    FROM regular_games rg
    JOIN event_parsed ep
        ON ep.game_pk = rg.game_pk
        AND ep.pitcher_mlbam_id IN (rg.home_starter_mlbam_id, rg.away_starter_mlbam_id)
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number, ep.pitcher_mlbam_id
),

starter_rolling AS (
    SELECT
        game_id,
        pitcher_mlbam_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(ab_cnt) OVER w AS prior_ab,
        SUM(bip_cnt) OVER w AS prior_bip,
        SUM(hard_hit_cnt) OVER w AS prior_hard_hit,
        SUM(barrel_cnt) OVER w AS prior_barrel,
        SUM(xba_sum) OVER w AS prior_xba_sum,
        SUM(xslg_sum) OVER w AS prior_xslg_sum,
        SUM(xwoba_contact_sum) OVER w AS prior_xwoba_contact_sum,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
    FROM starter_game_agg
    WINDOW w AS (
        PARTITION BY pitcher_mlbam_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

starter_rates AS (
    SELECT
        game_id,
        pitcher_mlbam_id,
        CASE
            WHEN prior_bip >= 5 THEN ROUND(prior_hard_hit::numeric / prior_bip, 4)
            ELSE NULL
        END AS starter_hard_hit_pct,
        CASE
            WHEN prior_bip >= 5 THEN ROUND(prior_barrel::numeric / prior_bip, 4)
            ELSE NULL
        END AS starter_barrel_pct,
        CASE
            WHEN prior_ab >= 10 THEN ROUND(prior_xba_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS starter_xba,
        CASE
            WHEN prior_ab >= 10 THEN ROUND(prior_xslg_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS starter_xslg,
        CASE
            WHEN prior_pa >= 10 THEN
                ROUND((prior_xwoba_contact_sum + 0.69 * prior_bb + 0.72 * prior_hbp)::numeric / prior_pa, 4)
            ELSE NULL
        END AS starter_xwoba
    FROM starter_rolling
),

-- 2. Bullpen game aggregates: every PA where the pitcher on the mound is NOT
-- that game's starter, grouped by the fielding team.
bullpen_game_agg AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        CASE WHEN ep.inning_topbot = 'Top' THEN rg.home_team_id ELSE rg.away_team_id END AS pit_team_id,
        COUNT(*) AS pa_cnt,
        SUM(ep.is_ab) AS ab_cnt,
        SUM(ep.is_bip) AS bip_cnt,
        SUM(ep.is_hard_hit) AS hard_hit_cnt,
        SUM(ep.is_barrel) AS barrel_cnt,
        SUM(ep.xba_val) FILTER (WHERE ep.is_ab = 1) AS xba_sum,
        SUM(ep.xslg_val) FILTER (WHERE ep.is_ab = 1) AS xslg_sum,
        SUM(ep.xwoba_val) AS xwoba_contact_sum,
        SUM(ep.is_bb) AS bb_cnt,
        SUM(ep.is_hbp) AS hbp_cnt
    FROM regular_games rg
    JOIN event_parsed ep ON ep.game_pk = rg.game_pk
    WHERE (ep.inning_topbot = 'Top' AND ep.pitcher_mlbam_id IS DISTINCT FROM rg.home_starter_mlbam_id)
       OR (ep.inning_topbot = 'Bot' AND ep.pitcher_mlbam_id IS DISTINCT FROM rg.away_starter_mlbam_id)
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number,
             CASE WHEN ep.inning_topbot = 'Top' THEN rg.home_team_id ELSE rg.away_team_id END
),

bullpen_rolling AS (
    SELECT
        game_id,
        pit_team_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(ab_cnt) OVER w AS prior_ab,
        SUM(bip_cnt) OVER w AS prior_bip,
        SUM(hard_hit_cnt) OVER w AS prior_hard_hit,
        SUM(barrel_cnt) OVER w AS prior_barrel,
        SUM(xba_sum) OVER w AS prior_xba_sum,
        SUM(xslg_sum) OVER w AS prior_xslg_sum,
        SUM(xwoba_contact_sum) OVER w AS prior_xwoba_contact_sum,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
    FROM bullpen_game_agg
    WINDOW w AS (
        PARTITION BY pit_team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

bullpen_rates AS (
    SELECT
        game_id,
        pit_team_id,
        CASE
            WHEN prior_bip >= 5 THEN ROUND(prior_hard_hit::numeric / prior_bip, 4)
            ELSE NULL
        END AS bullpen_hard_hit_pct,
        CASE
            WHEN prior_bip >= 5 THEN ROUND(prior_barrel::numeric / prior_bip, 4)
            ELSE NULL
        END AS bullpen_barrel_pct,
        CASE
            WHEN prior_ab >= 10 THEN ROUND(prior_xba_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS bullpen_xba,
        CASE
            WHEN prior_ab >= 10 THEN ROUND(prior_xslg_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS bullpen_xslg,
        CASE
            WHEN prior_pa >= 10 THEN
                ROUND((prior_xwoba_contact_sum + 0.69 * prior_bb + 0.72 * prior_hbp)::numeric / prior_pa, 4)
            ELSE NULL
        END AS bullpen_xwoba
    FROM bullpen_rolling
),

-- 3. Offense (Batting) game aggregates. Anchored on every game the team
-- actually played (team_game_spine), not just games with a qualifying
-- Statcast PA -- otherwise a per-game ingestion gap silently drops that
-- game's "current" position in the rolling window and can null out a later
-- game's otherwise-valid season-to-date rate (same bug class fixed in
-- platoon_splits_update.sql on 2026-09-18; applied here proactively since
-- this is the identical per-team-per-game rolling shape).
batting_pa AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        CASE WHEN ep.inning_topbot = 'Top' THEN rg.away_team_id ELSE rg.home_team_id END AS bat_team_id,
        ep.is_ab,
        ep.is_bip,
        ep.is_hard_hit,
        ep.is_barrel,
        ep.xba_val,
        ep.xslg_val,
        ep.xwoba_val,
        ep.is_bb,
        ep.is_hbp
    FROM regular_games rg
    JOIN event_parsed ep ON ep.game_pk = rg.game_pk
),

team_game_spine AS (
    SELECT game_id, season, game_date, game_number, home_team_id AS bat_team_id
    FROM regular_games
    WHERE home_team_id IS NOT NULL
    UNION ALL
    SELECT game_id, season, game_date, game_number, away_team_id AS bat_team_id
    FROM regular_games
    WHERE away_team_id IS NOT NULL
),

batting_game_agg AS (
    SELECT
        s.game_id,
        s.season,
        s.game_date,
        s.game_number,
        s.bat_team_id,
        COUNT(bp.bat_team_id) AS pa_cnt,
        SUM(bp.is_ab) AS ab_cnt,
        SUM(bp.is_bip) AS bip_cnt,
        SUM(bp.is_hard_hit) AS hard_hit_cnt,
        SUM(bp.is_barrel) AS barrel_cnt,
        SUM(bp.xba_val) FILTER (WHERE bp.is_ab = 1) AS xba_sum,
        SUM(bp.xslg_val) FILTER (WHERE bp.is_ab = 1) AS xslg_sum,
        SUM(bp.xwoba_val) AS xwoba_contact_sum,
        SUM(bp.is_bb) AS bb_cnt,
        SUM(bp.is_hbp) AS hbp_cnt
    FROM team_game_spine s
    LEFT JOIN batting_pa bp ON bp.game_id = s.game_id AND bp.bat_team_id = s.bat_team_id
    GROUP BY s.game_id, s.season, s.game_date, s.game_number, s.bat_team_id
),

batting_rolling AS (
    SELECT
        game_id,
        bat_team_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(ab_cnt) OVER w AS prior_ab,
        SUM(bip_cnt) OVER w AS prior_bip,
        SUM(hard_hit_cnt) OVER w AS prior_hard_hit,
        SUM(barrel_cnt) OVER w AS prior_barrel,
        SUM(xba_sum) OVER w AS prior_xba_sum,
        SUM(xslg_sum) OVER w AS prior_xslg_sum,
        SUM(xwoba_contact_sum) OVER w AS prior_xwoba_contact_sum,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
    FROM batting_game_agg
    WINDOW w AS (
        PARTITION BY bat_team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

batting_rates AS (
    SELECT
        game_id,
        bat_team_id,
        CASE
            WHEN prior_bip >= 5 THEN ROUND(prior_hard_hit::numeric / prior_bip, 4)
            ELSE NULL
        END AS offense_hard_hit_pct,
        CASE
            WHEN prior_bip >= 5 THEN ROUND(prior_barrel::numeric / prior_bip, 4)
            ELSE NULL
        END AS offense_barrel_pct,
        CASE
            WHEN prior_ab >= 10 THEN ROUND(prior_xba_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS offense_xba,
        CASE
            WHEN prior_ab >= 10 THEN ROUND(prior_xslg_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS offense_xslg,
        CASE
            WHEN prior_pa >= 10 THEN
                ROUND((prior_xwoba_contact_sum + 0.69 * prior_bb + 0.72 * prior_hbp)::numeric / prior_pa, 4)
            ELSE NULL
        END AS offense_xwoba
    FROM batting_rolling
)

UPDATE gold.game_feature f
SET
    home_starter_hard_hit_pct = h_sr.starter_hard_hit_pct,
    away_starter_hard_hit_pct = a_sr.starter_hard_hit_pct,
    home_starter_barrel_pct = h_sr.starter_barrel_pct,
    away_starter_barrel_pct = a_sr.starter_barrel_pct,
    home_starter_xwoba = h_sr.starter_xwoba,
    away_starter_xwoba = a_sr.starter_xwoba,
    home_starter_xba = h_sr.starter_xba,
    away_starter_xba = a_sr.starter_xba,
    home_starter_xslg = h_sr.starter_xslg,
    away_starter_xslg = a_sr.starter_xslg,

    home_bullpen_hard_hit_pct = h_br.bullpen_hard_hit_pct,
    away_bullpen_hard_hit_pct = a_br.bullpen_hard_hit_pct,
    home_bullpen_barrel_pct = h_br.bullpen_barrel_pct,
    away_bullpen_barrel_pct = a_br.bullpen_barrel_pct,
    home_bullpen_xwoba = h_br.bullpen_xwoba,
    away_bullpen_xwoba = a_br.bullpen_xwoba,
    home_bullpen_xba = h_br.bullpen_xba,
    away_bullpen_xba = a_br.bullpen_xba,
    home_bullpen_xslg = h_br.bullpen_xslg,
    away_bullpen_xslg = a_br.bullpen_xslg,

    home_offense_hard_hit_pct = h_otr.offense_hard_hit_pct,
    away_offense_hard_hit_pct = a_otr.offense_hard_hit_pct,
    home_offense_barrel_pct = h_otr.offense_barrel_pct,
    away_offense_barrel_pct = a_otr.offense_barrel_pct,
    home_offense_xwoba = h_otr.offense_xwoba,
    away_offense_xwoba = a_otr.offense_xwoba,
    home_offense_xba = h_otr.offense_xba,
    away_offense_xba = a_otr.offense_xba,
    home_offense_xslg = h_otr.offense_xslg,
    away_offense_xslg = a_otr.offense_xslg
FROM regular_games g
LEFT JOIN starter_rates h_sr ON h_sr.game_id = g.game_id AND h_sr.pitcher_mlbam_id = g.home_starter_mlbam_id
LEFT JOIN starter_rates a_sr ON a_sr.game_id = g.game_id AND a_sr.pitcher_mlbam_id = g.away_starter_mlbam_id
LEFT JOIN bullpen_rates h_br ON h_br.game_id = g.game_id AND h_br.pit_team_id = g.home_team_id
LEFT JOIN bullpen_rates a_br ON a_br.game_id = g.game_id AND a_br.pit_team_id = g.away_team_id
LEFT JOIN batting_rates h_otr ON h_otr.game_id = g.game_id AND h_otr.bat_team_id = g.home_team_id
LEFT JOIN batting_rates a_otr ON a_otr.game_id = g.game_id AND a_otr.bat_team_id = g.away_team_id
WHERE f.game_id = g.game_id;
